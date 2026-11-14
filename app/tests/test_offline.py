"""اختبار طابور العمل بدون اتصال (بدون خادم حقيقي)."""
import json
import sys
import zlib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gb.client import ApiError, NetStats   # noqa: E402
from gb.offline import OfflineQueue, QueueLocked   # noqa: E402
from gb.tm355 import securecodec           # noqa: E402

KEY = "ab" * 32


class FakeApi:
    """يتصرف مثل الخادم: يتحقق من CRC ويفك الضغط ويتحقق من التوقيع."""

    def __init__(self, online=True, corrupt_first=0):
        self.online = online
        self.corrupt_first = corrupt_first
        self.stats = NetStats()
        self.sent = []

    def post(self, path, body):
        if not self.online:
            raise ApiError(0, "offline")
        self.sent.append((path, body))
        return {}

    def post_raw(self, path, content, headers):
        if not self.online:
            raise ApiError(0, "offline")
        self.stats.bytes_up += len(content)
        if self.corrupt_first:                       # بت انقلب في الطريق
            self.corrupt_first -= 1
            content = bytes([content[0] ^ 1]) + content[1:]
        if zlib.crc32(content) != int(headers["X-Payload-CRC32"], 16):
            raise ApiError(400, "crc", {"crc_failed": True})
        body = json.loads(zlib.decompress(content))
        self.sent.append((path, body))
        good = [r for r in body["records"] if securecodec.verify(KEY, r)]
        return {"accepted": len(good), "duplicates": 0, "rejected": len(body["records"]) - len(good),
                "accepted_cents": 100 * len(good), "processed_ids": [r["client_id"] for r in body["records"]]}


def test_queue_survives_restart_and_flushes_once(tmp_path):
    q = OfflineQueue("salem", folder=str(tmp_path), password="pw", sync_key=KEY)
    q.add_record("coins", "round", "جولة")
    q.add_record("guess", "round", "جولة")
    q.add_manual(5, 0.3)
    assert q.size == 3

    q2 = OfflineQueue("salem", folder=str(tmp_path), password="pw", sync_key=KEY)   # أُغلق التطبيق وفُتح
    assert q2.size == 3
    assert len({r["client_id"] for r in q2.records}) == 2      # كل سجل له معرّف فريد

    assert q2.flush(FakeApi(online=False)) is None             # ما زال بدون اتصال: لا شيء يضيع
    assert q2.size == 3

    res = q2.flush(FakeApi())
    assert (res["accepted"], res["manual"], q2.size) == (2, 1, 0)
    assert res["packed_bytes"] < res["plain_bytes"]
    assert OfflineQueue("salem", folder=str(tmp_path), password="pw").size == 0


def test_manual_earning_keeps_client_id_for_dedupe(tmp_path):
    q = OfflineQueue("ali", folder=str(tmp_path))
    q.add_manual(7, 1.5)
    api = FakeApi()
    q.flush(api)
    path, body = api.sent[0]
    assert path == "/api/earnings/" and body["client_id"].startswith("man-")


def test_queue_file_is_encrypted_and_tamper_evident(tmp_path):
    q = OfflineQueue("mona", folder=str(tmp_path), password="secret phrase", sync_key=KEY)
    q.add_record("coins", "round", "جمع العملات")
    raw = Path(q.path).read_text()
    assert "coins" not in raw and "client_id" not in raw     # لا يُقرأ بدون كلمة المرور
    with pytest.raises(QueueLocked):
        OfflineQueue("mona", folder=str(tmp_path), password="wrong")
    blob = json.loads(raw)
    ct = bytearray(securecodec.base64.b64decode(blob["ciphertext"]))
    ct[5] ^= 1
    blob["ciphertext"] = securecodec.base64.b64encode(bytes(ct)).decode()
    Path(q.path).write_text(json.dumps(blob))
    with pytest.raises(QueueLocked):                          # وسم GCM يكشف التعديل
        OfflineQueue("mona", folder=str(tmp_path), password="secret phrase")


def test_crc_failure_is_retransmitted(tmp_path):
    q = OfflineQueue("sara", folder=str(tmp_path), sync_key=KEY)
    q.add_record("coins", "round", "جولة")
    res = q.flush(FakeApi(corrupt_first=1))
    assert (res["tries"], res["accepted"], q.size) == (2, 1, 0)


def test_rekey_after_password_change(tmp_path):
    q = OfflineQueue("omar", folder=str(tmp_path), password="old pw", sync_key=KEY)
    q.add_record("coins", "round", "جولة")
    new_key = "cd" * 32
    q.rekey("new pw", new_key)
    assert securecodec.verify(new_key, q.records[0])
    assert OfflineQueue("omar", folder=str(tmp_path), password="new pw").size == 1
