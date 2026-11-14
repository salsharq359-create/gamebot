"""
طابور العمل بدون اتصال (offline-first) — TM255 الوحدة 1، مع إضافات TM355.

عند انقطاع الشبكة يستمر التطبيق في العمل: الروبوت يلعب على الجهاز، والأرباح اليدوية تُسجَّل،
وكل شيء يُحفظ في ملف على الجهاز. عند عودة الاتصال تُرسل السجلات دفعة واحدة.
لكل سجل معرّف فريد (client_id)، فإعادة الإرسال بعد انقطاع في المنتصف لا تضاعف الأرباح.

إضافات TM355:
  - الملف مشفّر بـ AES-256-GCM بمفتاح مشتق من كلمة المرور (securecodec).
  - كل سجل موقّع بـ HMAC-SHA256 بمفتاح المزامنة الذي يعطيه الخادم عند الدخول.
  - الطلب يُضغط بـ DEFLATE (zlib) ويُرسل معه CRC-32؛ إذا فشل التحقق في الخادم يُعاد الإرسال (ARQ).
"""
from __future__ import annotations

import base64
import json
import os
import tempfile
import uuid
import zlib
from datetime import datetime, timezone

from cryptography.exceptions import InvalidTag

from .client import Api, ApiError
from .tm355 import securecodec

SYNC_PATH = "/api/bot/offline-sync/"
MAX_TRIES = 3


class QueueLocked(Exception):
    """الملف مشفّر بكلمة مرور أخرى، أو عُدّل (فشل وسم GCM)."""


def _data_dir() -> str:
    """
    مجلد بيانات التطبيق: على الهاتف يعطيه Flet في FLET_APP_STORAGE_DATA (المجلد الشخصي غير قابل للكتابة هناك).
    وإن تعذّر الكتابة نستخدم مجلد الحاوية المؤقت، فتضيع القائمة المحلية عند تنظيف النظام لا أكثر.
    """
    for base in (os.environ.get("FLET_APP_STORAGE_DATA"), os.path.expanduser("~")):
        if not base:
            continue
        folder = os.path.join(base, ".gamebot")
        try:
            os.makedirs(folder, exist_ok=True)
            return folder
        except OSError:
            continue
    folder = os.path.join(tempfile.gettempdir(), "gamebot")
    os.makedirs(folder, exist_ok=True)
    return folder


class OfflineQueue:
    def __init__(self, username: str, folder: str | None = None, password: str | None = None,
                 sync_key: str | None = None):
        self.path = self.path_for(username, folder)
        self.records: list[dict] = []
        self.sessions: list[dict] = []
        self.manual: list[dict] = []
        self.last_sync: dict | None = None
        self.last_payload: bytes | None = None      # آخر طلب مزامنة قبل الضغط (لمختبر TM355)
        self.sync_key = sync_key
        self._password = password
        self._salt: bytes | None = None
        self._key: bytes | None = None
        self.encrypted = False
        self._load()

    @staticmethod
    def path_for(username: str, folder: str | None = None) -> str:
        folder = folder or _data_dir()
        safe = "".join(ch for ch in username if ch.isalnum() or ch in "-_") or "user"
        return os.path.join(folder, f"queue-{safe}.json")

    # ------------------------------------------------------------- التخزين
    def _load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        if data.get("format") == securecodec.MAGIC:
            if not self._password:
                raise QueueLocked("الطابور مشفّر ويحتاج كلمة المرور")
            self._salt = base64.b64decode(data["salt"])
            self._key = securecodec.derive_key(self._password, self._salt, data.get("iterations",
                                                                                    securecodec.KDF_ITERATIONS))
            try:
                data = securecodec.unseal(self._key, data)
            except InvalidTag:
                raise QueueLocked("تعذّر فك تشفير الطابور: كلمة مرور مختلفة أو ملف معدّل")
            self.encrypted = True
        self.records, self.sessions, self.manual = (data.get("records", []), data.get("sessions", []),
                                                    data.get("manual", []))

    def _ensure_key(self) -> bytes | None:
        if self._password and self._key is None:
            self._salt = os.urandom(16)
            self._key = securecodec.derive_key(self._password, self._salt)
        return self._key

    def save(self) -> None:
        content = {"records": self.records, "sessions": self.sessions, "manual": self.manual}
        key = self._ensure_key()
        if key:
            content = securecodec.seal(key, self._salt, content)
            self.encrypted = True
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False)
        os.replace(tmp, self.path)   # كتابة ذرية: لا يتلف الملف إذا أُغلق التطبيق فجأة

    def rekey(self, password: str, sync_key: str) -> None:
        """بعد تغيير كلمة المرور: مفتاح تشفير جديد، وتوقيع السجلات المعلقة بمفتاح المزامنة الجديد."""
        self._password, self.sync_key = password, sync_key
        self._key = None
        for r in self.records:
            r["mac"] = securecodec.sign(sync_key, r)
        self.save()

    @property
    def size(self) -> int:
        return len(self.records) + len(self.sessions) + len(self.manual)

    @property
    def file_bytes(self) -> int:
        try:
            return os.path.getsize(self.path)
        except OSError:
            return 0

    # ------------------------------------------------------------- الإضافة
    def add_record(self, platform: str, task: str, note: str) -> dict:
        rec = {"client_id": f"off-{uuid.uuid4()}", "platform": platform, "task": task, "note": note,
               "played_at": datetime.now(timezone.utc).isoformat()}
        if self.sync_key:
            rec["mac"] = securecodec.sign(self.sync_key, rec)
        self.records.append(rec)
        self.save()
        return rec

    def add_session(self, started_at: datetime, seconds: int) -> None:
        self.sessions.append({"started_at": started_at.astimezone(timezone.utc).isoformat(), "seconds": int(seconds)})
        self.save()

    def add_manual(self, platform_id: int, amount: float) -> None:
        self.manual.append({"platform_id": platform_id, "amount": amount, "client_id": f"man-{uuid.uuid4()}"})
        self.save()

    # ------------------------------------------------------------- الإرسال
    def build_payload(self) -> tuple[bytes, bytes, int]:
        """يرجع (JSON قبل الضغط، بعد الضغط، CRC-32 للمضغوط)."""
        for r in self.records:
            if "mac" not in r and self.sync_key:
                r["mac"] = securecodec.sign(self.sync_key, r)
        plain = json.dumps({"records": self.records, "sessions": self.sessions}, ensure_ascii=False,
                           separators=(",", ":")).encode()
        packed = zlib.compress(plain, 9)
        return plain, packed, zlib.crc32(packed)

    def flush(self, api: Api) -> dict | None:
        """يرسل كل ما في الطابور. يرجع ملخصاً، أو None إذا لم يكن هناك ما يُرسل أو لا يوجد اتصال."""
        if not self.size:
            return None
        summary = {"accepted": 0, "duplicates": 0, "rejected": 0, "bad_mac": 0, "accepted_cents": 0, "manual": 0,
                   "bytes": 0, "records": len(self.records), "plain_bytes": 0, "packed_bytes": 0, "tries": 0,
                   "reasons": {}}
        if self.records or self.sessions:
            plain, packed, crc = self.build_payload()
            self.last_payload = plain
            before = api.stats.bytes_up
            res = None
            for attempt in range(1, MAX_TRIES + 1):          # ARQ: إعادة الإرسال إذا فشل CRC
                summary["tries"] = attempt
                try:
                    res = api.post_raw(SYNC_PATH, packed, {"Content-Encoding": "deflate",
                                                           "X-Payload-CRC32": f"{crc:08x}"})
                    break
                except ApiError as e:
                    if e.status == 0:
                        return None          # ما زال بدون اتصال: نحاول لاحقاً
                    if not e.data.get("crc_failed") or attempt == MAX_TRIES:
                        raise
            done = set(res.get("processed_ids", []))
            self.records = [r for r in self.records if r["client_id"] not in done]
            self.sessions = []
            for k in ("accepted", "duplicates", "rejected", "bad_mac", "accepted_cents"):
                summary[k] += res.get(k, 0)
            summary["reasons"] = dict(res.get("reasons") or {})     # TM354: سبب كل رفض من الخادم
            summary["bytes"] = api.stats.bytes_up - before
            summary["plain_bytes"], summary["packed_bytes"], summary["crc"] = len(plain), len(packed), f"{crc:08x}"
        remaining = []
        for m in self.manual:
            try:
                api.post("/api/earnings/", m)
                summary["manual"] += 1
            except ApiError as e:
                if e.status == 0:
                    remaining.append(m)   # نحاول لاحقاً
                # غير ذلك (مثلاً منصة حُذفت): خطأ دائم، لا فائدة من إعادة المحاولة
        self.manual = remaining
        self.save()
        self.last_sync = {**summary, "at": datetime.now()}
        return summary
