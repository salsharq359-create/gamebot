"""
اختبار شامل: يشغّل Django وخادم الروبوت (python-socketio) فعلاً، ثم يتصل كما يتصل تطبيق Flet.
"""
import asyncio
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
import socketio

ROOT = Path(__file__).resolve().parents[2]
KEY = "e2e-internal-key"


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def wait_http(url: str, timeout: float = 20) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            if httpx.get(url, timeout=1).status_code < 500:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise RuntimeError(f"server at {url} did not start")


@pytest.fixture(scope="module")
def servers(tmp_path_factory):
    db = tmp_path_factory.mktemp("db") / "e2e.sqlite3"
    api_port, rt_port = free_port(), free_port()
    # TM354 (عزل الاختبارات): نتجاهل DATABASE_* حتى لا يكتب الاختبار في قاعدة PostgreSQL مشتركة.
    # قبل ذلك كان التشغيل الثاني مع DATABASE_HOST يفشل لأن المستخدم e2euser موجود من التشغيل الأول.
    env = {**{k: v for k, v in os.environ.items() if not k.startswith("DATABASE_")},
           "SQLITE_PATH": str(db), "INTERNAL_API_KEY": KEY, "DJANGO_DEBUG": "1"}
    subprocess.run([sys.executable, "manage.py", "migrate", "-v", "0"], cwd=ROOT / "backend", env=env, check=True)
    django = subprocess.Popen([sys.executable, "manage.py", "runserver", f"127.0.0.1:{api_port}", "--noreload"],
                              cwd=ROOT / "backend", env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rt_env = {**env, "DJANGO_URL": f"http://127.0.0.1:{api_port}", "MOVE_DELAY_MS": "0", "EVENT_DELAY_MS": "0"}
    realtime = subprocess.Popen([sys.executable, "-m", "uvicorn", "realtime.server:app", "--port", str(rt_port),
                                 "--log-level", "warning"], cwd=ROOT / "realtime", env=rt_env)
    try:
        wait_http(f"http://127.0.0.1:{api_port}/api/health/")
        wait_http(f"http://127.0.0.1:{rt_port}/health")
        yield f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{rt_port}"
    finally:
        realtime.terminate()
        django.terminate()


def test_full_session(servers):
    api, rt = servers

    async def scenario():
        async with httpx.AsyncClient(base_url=api) as http:
            r = await http.post("/api/auth/register/", json={"username": "e2euser", "password": "correct horse battery"})
            assert r.status_code == 201, r.text
            token = r.json()["token"]

            bad = socketio.AsyncClient()
            with pytest.raises(socketio.exceptions.ConnectionError):
                await bad.connect(rt, auth={"token": "forged"}, wait_timeout=5)

            sio = socketio.AsyncClient()
            done = asyncio.get_running_loop().create_future()
            counts = {"move": 0, "earning": 0}

            @sio.on("bot_event")
            async def on_event(e):
                counts["move"] += e["type"] == "move"

            @sio.on("earning")
            async def on_earning(e):
                counts["earning"] += 1

            @sio.on("bot_done")
            async def on_done(e):
                if not done.done():
                    done.set_result(e)

            await sio.connect(rt, auth={"token": token}, wait_timeout=5)
            plan = await sio.call("request_bot_suggestion", {"minutes": 10}, timeout=10)
            assert plan["plan"] and plan["minutes_budget"] == 10

            started = await sio.call("start_bot", {"rounds": 2}, timeout=10)
            assert started["ok"] and started["games"] == ["coins", "guess"]
            assert (await sio.call("start_bot", {"rounds": 2}, timeout=10))["ok"] is False

            result = await asyncio.wait_for(done, 60)
            # لعبتان × جولتان = 4 ألعاب × 1$ + مكافأتان يوميتان × 0.50$ = 5$
            assert result["session_cents"] == 500
            assert counts["move"] > 0 and counts["earning"] == 6

            earnings = (await http.get("/api/earnings/", headers={"Authorization": f"Bearer {token}"})).json()
            assert earnings["balance_cents"] == 500
            await sio.disconnect()

    asyncio.run(scenario())


def test_delta_frames_session(servers):
    """TM355: إطارات الفروق تُفك في التطبيق إلى نفس الخرائط، وحجمها أصغر كثيراً."""
    from realtime.framecodec import Decoder

    api, rt = servers

    async def scenario():
        async with httpx.AsyncClient(base_url=api) as http:
            r = await http.post("/api/auth/register/", json={"username": "deltauser", "password": "correct horse battery"})
            token = r.json()["token"]
            sio = socketio.AsyncClient()
            done = asyncio.get_running_loop().create_future()
            dec = Decoder()
            boards = []

            @sio.on("bot_event")
            async def on_event(e):
                if e["type"] == "game":
                    dec.board = None
                if e["type"] == "move":
                    assert "frame" in e and "board" not in e
                    boards.append(dec.decode(e["frame"]))

            @sio.on("bot_done")
            async def on_done(e):
                if not done.done():
                    done.set_result(e)

            await sio.connect(rt, auth={"token": token}, wait_timeout=5)
            assert (await sio.call("start_bot", {"rounds": 2, "delta": True}, timeout=10))["delta"] is True
            result = await asyncio.wait_for(done, 60)
            st = result["frames"]
            assert boards and all(b is not None for b in boards)
            assert st["delta"] and st["frames"] == len(boards)
            assert st["sent_bytes"] < st["full_bytes"] / 2
            await sio.disconnect()

    asyncio.run(scenario())
