"""
خادم الربط الفوري بلغة بايثون (python-socketio) — بديل خادم Node.js في خطة Copilot:
  - يتحقق من هوية المستخدم عبر Django (رمز الدخول)
  - يشغّل الروبوت ويبث كل حركة مباشرة للتطبيق
  - يبلّغ Django بكل مهمة مكتملة (Django يحدد المبلغ ويمنع التكرار)
  - يجلب اقتراحات المستشار من Django

نفس أسماء الأحداث القديمة، لذلك يعمل معه تطبيق Flet وتطبيق Flutter أيضاً.

التشغيل:  uvicorn realtime.server:app --port 3001
"""
from __future__ import annotations

import asyncio
import os
import random
import re
import time
import uuid
from datetime import datetime, timezone

import httpx
import socketio
from socketio.exceptions import ConnectionRefusedError

from .bot import BotSession, State, run_session
from .framecodec import Encoder

DJANGO_URL = os.environ.get("DJANGO_URL", "http://127.0.0.1:8000").rstrip("/")
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "dev-internal-key")
MOVE_DELAY = float(os.environ.get("MOVE_DELAY_MS", "120")) / 1000
EVENT_DELAY = float(os.environ.get("EVENT_DELAY_MS", "350")) / 1000
CORS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*" if "*" in CORS else CORS)
_http: httpx.AsyncClient | None = None
running: dict[int, BotSession] = {}  # user_id -> آلة حالات الجلسة (TM354)
connections: dict[int, int] = {}     # user_id -> عدد الاتصالات المفتوحة


def http() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient(base_url=DJANGO_URL, timeout=10)
    return _http


async def django(path: str, *, token: str | None = None, method: str = "GET", json: dict | None = None,
                 internal: bool = False) -> tuple[int, dict]:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if internal:
        headers["X-Internal-Key"] = INTERNAL_API_KEY
    r = await http().request(method, path, headers=headers, json=json)
    try:
        data = r.json()
    except ValueError:
        data = {}
    return r.status_code, data if isinstance(data, dict) else {}


# ------------------------------------------------------------------- الأحداث
@sio.event
async def connect(sid, environ, auth):
    token = (auth or {}).get("token")
    if not token:
        raise ConnectionRefusedError("unauthorized")
    try:
        status, me = await django("/api/me/", token=token)
    except httpx.HTTPError:
        raise ConnectionRefusedError("backend_unavailable")
    if status != 200:
        raise ConnectionRefusedError("unauthorized")
    await sio.save_session(sid, {"user": me, "token": token})
    await sio.enter_room(sid, f"user:{me['id']}")
    connections[me["id"]] = connections.get(me["id"], 0) + 1
    await sio.emit("hello", {"username": me["username"], "balance_cents": me["balance_cents"]}, to=sid)


@sio.event
async def disconnect(sid, *args):
    session = await sio.get_session(sid)
    uid = session.get("user", {}).get("id")
    if uid is None:
        return
    connections[uid] = max(0, connections.get(uid, 1) - 1)
    # الروبوت لا يعمل والتطبيق مغلق: يتوقف عند انقطاع آخر اتصال للمستخدم
    if connections[uid] == 0 and uid in running and running[uid].can("stop"):
        running[uid].fire("stop")


@sio.event
async def ping_rt(sid, data=None):
    """لقياس زمن الاستجابة ذهاباً وإياباً (RTT) من التطبيق."""
    return {"t": time.time()}


@sio.event
async def subscribe_platform(sid, data):
    platform = (data or {}).get("platform", "")
    if isinstance(platform, str) and re.fullmatch(r"[a-z0-9-]{1,40}", platform):
        await sio.enter_room(sid, f"platform:{platform}")
        return {"ok": True}
    return {"ok": False}


@sio.event
async def request_bot_suggestion(sid, data):
    session = await sio.get_session(sid)
    try:
        minutes = int((data or {}).get("minutes", 30))
    except (TypeError, ValueError):
        minutes = 30
    status, plan = await django(f"/api/bot/strategy/?minutes={minutes}", token=session["token"])
    payload = plan if status == 200 else {"error": plan.get("error", "failed")}
    await sio.emit("bot_suggestion", payload, to=sid)
    return payload


@sio.event
async def start_bot(sid, data):
    data = data or {}
    session = await sio.get_session(sid)
    user = session["user"]
    if user["id"] in running:
        return {"ok": False, "error": "الروبوت يعمل بالفعل"}
    _, acc = await django("/api/user/accounts/", token=session["token"])
    linked = [a["platform"]["key"] for a in acc.get("accounts", [])
              if a["platform"].get("linked") and a["platform"].get("is_demo") and not a["platform"].get("custom")]
    wanted = data.get("games")
    games = [g for g in linked if g in wanted] if isinstance(wanted, list) else linked
    try:
        rounds = max(1, min(10, int(data.get("rounds", 3))))
    except (TypeError, ValueError):
        rounds = 3
    state = BotSession()
    state.start()
    running[user["id"]] = state
    delta = bool(data.get("delta"))      # TM355: التطبيق يطلب إطارات الفروق بدل الخريطة كاملة
    sio.start_background_task(_run_bot, user, games, rounds, data.get("tasks") or {}, state, delta)
    return {"ok": True, "games": games, "rounds": rounds, "delta": delta}


@sio.event
async def stop_bot(sid, data=None):
    session = await sio.get_session(sid)
    st = running.get(session["user"]["id"])
    if not st or not st.can("stop"):
        return {"ok": False, "error": "لا توجد جلسة تعمل"}
    st.fire("stop")
    return {"ok": True, "state": st.state.value}


# --------------------------------------------------------------- جلسة الروبوت
async def _run_bot(user: dict, games: list[str], rounds: int, tasks: dict, state: BotSession,
                   delta: bool = False) -> None:
    room = f"user:{user['id']}"
    session_id = str(uuid.uuid4())
    started = time.monotonic()
    started_at = datetime.now(timezone.utc)
    session_cents, n = 0, 0
    frames = Encoder()
    try:
        await sio.emit("bot_started", {"session": session_id, "games": games, "rounds": rounds}, room=room)
        for ev in run_session(games, rounds, tasks, random.Random(), stopped=lambda: state.stop_requested):
            if ev["type"] == "task":
                n += 1
                status, res = await django("/api/internal/earnings/", internal=True, method="POST", json={
                    "user_id": user["id"], "platform": ev["platform"], "task": ev["task"],
                    "note": ev["note"], "client_id": f"{session_id}-{n}"})
                if status == 200 and res.get("accepted"):
                    session_cents += res["cents"]
                await sio.emit("earning", {**ev, "accepted": bool(res.get("accepted")), "cents": res.get("cents", 0),
                                           "reason": res.get("reason"), "balance_cents": res.get("balance_cents"),
                                           "session_cents": session_cents}, room=room)
                await asyncio.sleep(EVENT_DELAY)
            else:
                if ev["type"] == "game":
                    frames.reset()                 # لعبة جديدة: الإطار التالي مفتاحي
                if ev["type"] == "move":
                    frame = frames.encode(ev["board"])
                    if delta:
                        ev = {"type": "move", "platform": ev["platform"], "frame": frame}
                await sio.emit("bot_event", ev, room=room)
                if ev.get("platform"):
                    await sio.emit("platform_activity", {"platform": ev["platform"], "type": ev["type"]},
                                   room=f"platform:{ev['platform']}", skip_sid=None)
                await asyncio.sleep(MOVE_DELAY if ev["type"] == "move" else 0 if ev["type"] == "progress"
                                    else EVENT_DELAY)
        state.fire("done")
        seconds = round(time.monotonic() - started)
        _, res = await django("/api/internal/sessions/", internal=True, method="POST", json={
            "user_id": user["id"], "seconds": seconds, "started_at": started_at.isoformat(),
            "session_cents": session_cents})
        await sio.emit("bot_done", {"session": session_id, "session_cents": session_cents, "seconds": seconds,
                                    "minutes_today": res.get("minutes_today"), "stopped": state.state is State.STOPPED, "outcome": state.state.value,
                                    "frames": {**frames.stats, "delta": delta}}, room=room)
    except Exception as e:   # نبلغ التطبيق بدل أن تنتهي الجلسة بصمت
        if state.can("error"):
            state.fire("error")
        await sio.emit("bot_error", {"error": str(e)}, room=room)
    finally:
        running.pop(user["id"], None)


# ---------------------------------------------------------------- تطبيق ASGI
async def _health(scope, receive, send):
    if scope["type"] == "http" and scope["path"] == "/health":
        body = f'{{"ok": true, "sessions": {len(running)}}}'.encode()
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": body})
        return
    if scope["type"] == "http":
        await send({"type": "http.response.start", "status": 404, "headers": []})
        await send({"type": "http.response.body", "body": b""})


app = socketio.ASGIApp(sio, other_asgi_app=_health)
