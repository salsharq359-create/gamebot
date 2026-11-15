"""
خادم واحد لـ Render: Django (الحسابات والمحفظة) وخادم الروبوت (socket.io) في عملية واحدة وعنوان واحد.
السبب: الخدمات المجانية في Render لا تستقبل اتصالات الشبكة الخاصة من بعضها، و 750 ساعة مجانية شهرياً تكفي خدمة واحدة فقط.
خادم الروبوت يكلّم Django على 127.0.0.1 داخل الحاوية نفسها (DJANGO_URL في أمر التشغيل).
"""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gamebot_api.settings")

from django.core.asgi import get_asgi_application  # noqa: E402

django_app = get_asgi_application()

import socketio  # noqa: E402

from realtime.server import sio  # noqa: E402

app = socketio.ASGIApp(sio, other_asgi_app=django_app)
