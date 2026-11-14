"""TM354: حالة الروبوت في التطبيق تُدار بآلة الحالات (بدون واجهة Flet حقيقية)."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gb.app import GameBotApp            # noqa: E402
from gb.engine.bot import BotSession, State   # noqa: E402


def bare_app():
    """تطبيق بلا صفحة: نضبط فقط الحقول التي تحتاجها معالجات الأحداث."""
    app = GameBotApp.__new__(GameBotApp)
    app.session, app.bot_log, app.current, app.me = BotSession(), [], "home", None
    app.bot_status, app.bot_progress, app.session_cents, app.board = "", 0.0, 0, None
    return app


def run(coro):
    return asyncio.run(coro)


def test_connection_lost_ends_an_online_session():
    """الخطأ قبل الإصلاح: انقطاع الاتصال أثناء الجلسة يترك «الروبوت يعمل» إلى الأبد."""
    app = bare_app()
    app.session.start()
    assert app.bot_running
    run(app.on_socket_status(False))
    assert app.session.state is State.INTERRUPTED and not app.bot_running
    assert "انقطع الاتصال" in app.bot_log[0]
    run(app.on_bot_done({"session_cents": 100, "seconds": 5}))    # وصلت متأخرة: تُتجاهل بلا خطأ
    assert app.session.state is State.INTERRUPTED


def test_local_session_is_not_affected_by_connection_changes():
    app = bare_app()
    app.session.start(local=True)
    run(app.on_socket_status(False))
    assert app.local_running and app.session.state is State.RUNNING


def test_stop_reported_by_server_ends_in_stopped():
    app = bare_app()
    app.session.start()
    app.refresh_me = lambda: None
    run(app.on_bot_done({"session_cents": 0, "seconds": 3, "stopped": True}))
    assert app.session.state is State.STOPPED and app.bot_status == "أوقفت الروبوت"


def test_sync_message_shows_real_reasons():
    from gb.app import sync_message
    msg = sync_message({"accepted": 2, "accepted_cents": 200, "rejected": 3, "manual": 0,
                        "reasons": {"daily_limit": 2, "bad_mac": 1}})
    assert "تجاوزت الحد اليومي: 2" in msg and "توقيع غير صحيح: 1" in msg
    old_server = sync_message({"accepted": 0, "accepted_cents": 0, "rejected": 1, "manual": 0})
    assert old_server.endswith("رُفضت 1")          # خادم قديم بلا أسباب: لا نخمّن
