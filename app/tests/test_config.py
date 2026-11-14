"""عناوين الخوادم: متغيرات البيئة أولاً، ثم server.json الذي يكتبه سكربت بناء الهاتف، ثم localhost."""
import importlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _reload(monkeypatch, env: dict, file_data: dict | None):
    for k in ("API_URL", "REALTIME_URL"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    cfg = ROOT / "server.json"
    existed = cfg.exists()
    backup = cfg.read_text(encoding="utf-8") if existed else None
    try:
        if file_data is None:
            cfg.unlink(missing_ok=True)
        else:
            cfg.write_text(json.dumps(file_data), encoding="utf-8")
        import gb.config as C
        importlib.reload(C)
        return SimpleNamespace(API_URL=C.API_URL, REALTIME_URL=C.REALTIME_URL)   # نسخ القيم قبل إعادة التحميل
    finally:
        if backup is None:
            cfg.unlink(missing_ok=True)
        else:
            cfg.write_text(backup, encoding="utf-8")
        importlib.reload(sys.modules["gb.config"])


def test_defaults_to_localhost_without_file_or_env(monkeypatch):
    C = _reload(monkeypatch, {}, None)
    assert C.API_URL == "http://127.0.0.1:8000" and C.REALTIME_URL == "http://127.0.0.1:3001"


def test_server_json_is_used_on_device(monkeypatch):
    C = _reload(monkeypatch, {}, {"api_url": "https://api.example.org/", "realtime_url": "https://rt.example.org"})
    assert C.API_URL == "https://api.example.org"            # بدون / في الآخر
    assert C.REALTIME_URL == "https://rt.example.org"


def test_env_overrides_server_json(monkeypatch):
    C = _reload(monkeypatch, {"API_URL": "http://10.0.0.5:8000"}, {"api_url": "https://api.example.org"})
    assert C.API_URL == "http://10.0.0.5:8000"


def test_offline_queue_folder_is_writable_on_device(monkeypatch, tmp_path):
    from gb import offline
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path))
    folder = offline._data_dir()
    assert folder == str(tmp_path / ".gamebot") and os.path.isdir(folder)
    path = offline.OfflineQueue.path_for("ali")
    assert path.startswith(str(tmp_path))
