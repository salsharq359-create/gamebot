"""
جيم بوت — واجهة بايثون (Flet).

التشغيل (بعد تشغيل Django وخادم الروبوت):
    pip install -r requirements.txt
    python main.py                       # نافذة على الكمبيوتر
    flet run --web main.py               # في المتصفح
    FLET_WEB_PORT=8550 python main.py    # خادم ويب (للنشر)

عناوين الخوادم من متغيرات البيئة: API_URL (افتراضي http://127.0.0.1:8000)
و REALTIME_URL (افتراضي http://127.0.0.1:3001).
"""
import os

import flet as ft

from gb.app import GameBotApp


def main(page: ft.Page):
    GameBotApp(page)


if __name__ == "__main__":
    if os.environ.get("FLET_WEB_PORT"):
        # وضع خادم الويب (للنشر على EC2 خلف Nginx)
        ft.run(main, view=ft.AppView.WEB_BROWSER, host="0.0.0.0", port=int(os.environ["FLET_WEB_PORT"]),
               assets_dir="assets", no_cdn=True)
    else:
        ft.run(main, assets_dir="assets")
