"""
الأمن (TM355 — التشفير وسلامة البيانات).

1) تشفير طابور الجهاز بـ AES-256-GCM:
   - المفتاح يُشتق من كلمة المرور بـ PBKDF2-HMAC-SHA256 (200,000 تكرار) وملح عشوائي محفوظ في الملف.
     فإذا سُرق الجهاز أو الملف، لا تُقرأ السجلات ولا تُعدّل بدون كلمة المرور.
   - GCM يشفّر ويضيف وسم مصادقة (16 بايت): أي تعديل في الملف يُكتشف عند فك التشفير.
   - رقم استخدام واحد (nonce) عشوائي 12 بايت جديد في كل حفظ.

2) توقيع السجلات بـ HMAC-SHA256:
   الخادم يعطي التطبيق عند الدخول «مفتاح مزامنة» خاصاً بالمستخدم. كل سجل يُوقّع بهذا المفتاح،
   والخادم يرفض أي سجل توقيعه غير صحيح (مثلاً سجل أُضيف أو عُدّل يدوياً).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KDF_ITERATIONS = 200_000
MAGIC = "gamebot-queue-v2"


def derive_key(password: str, salt: bytes, iterations: int = KDF_ITERATIONS) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations, dklen=32)


def encrypt(key: bytes, plaintext: bytes, aad: bytes = MAGIC.encode()) -> tuple[bytes, bytes]:
    nonce = os.urandom(12)
    return nonce, AESGCM(key).encrypt(nonce, plaintext, aad)


def decrypt(key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes = MAGIC.encode()) -> bytes:
    return AESGCM(key).decrypt(nonce, ciphertext, aad)    # يرفع InvalidTag إذا عُدّل الملف


def seal(key: bytes, salt: bytes, obj: dict) -> dict:
    """يرجع محتوى الملف: كل شيء نصي (base64) حتى يبقى الملف JSON."""
    nonce, ct = encrypt(key, json.dumps(obj, ensure_ascii=False).encode())
    b64 = lambda b: base64.b64encode(b).decode()
    return {"format": MAGIC, "kdf": "pbkdf2-sha256", "iterations": KDF_ITERATIONS,
            "salt": b64(salt), "nonce": b64(nonce), "ciphertext": b64(ct)}


def unseal(key: bytes, blob: dict) -> dict:
    d = lambda s: base64.b64decode(s)
    return json.loads(decrypt(key, d(blob["nonce"]), d(blob["ciphertext"])))


# ------------------------------------------------------------------- HMAC
SIGNED_FIELDS = ("client_id", "platform", "task", "played_at")


def canonical(record: dict) -> bytes:
    return "|".join(str(record.get(f, "")) for f in SIGNED_FIELDS).encode()


def sign(sync_key: str, record: dict) -> str:
    return hmac.new(bytes.fromhex(sync_key), canonical(record), hashlib.sha256).hexdigest()


def verify(sync_key: str, record: dict) -> bool:
    mac = record.get("mac")
    return isinstance(mac, str) and hmac.compare_digest(mac, sign(sync_key, record))
