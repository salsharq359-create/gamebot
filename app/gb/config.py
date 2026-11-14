"""
عناوين الخوادم للتطبيق. الأولوية:
  1. متغيرات البيئة API_URL و REALTIME_URL (للتطوير على الكمبيوتر)
  2. الملف server.json بجانب مجلد gb (يكتبه سكربت البناء build_mobile.sh، لأن الهاتف لا يرى متغيرات البيئة)
  3. الافتراضي 127.0.0.1 (يعمل فقط على الكمبيوتر نفسه)
على الهاتف يجب أن يكون العنوانان https://، لأن أندرويد وآيفون يرفضان الاتصال غير المشفّر.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

_FILE = Path(__file__).resolve().parents[1] / "server.json"


def _from_file() -> dict:
    try:
        return json.loads(_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


_cfg = _from_file()
API_URL = (os.environ.get("API_URL") or _cfg.get("api_url") or "http://127.0.0.1:8000").rstrip("/")
REALTIME_URL = (os.environ.get("REALTIME_URL") or _cfg.get("realtime_url") or "http://127.0.0.1:3001").rstrip("/")
