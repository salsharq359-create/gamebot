"""
عملاء الشبكة (TM255 - الوحدة 1):
  Api        — REST/JSON لخادم Django (httpx)، مع قياس زمن الاستجابة وحجم البيانات
  BotSocket  — Socket.io لخادم الروبوت الفوري (python-socketio)، مع قياس زمن الذهاب والإياب (RTT)

كلاهما يدعم «وضع عدم الاتصال» للتجربة: يتصرف التطبيق كأن الشبكة مقطوعة.
"""
from __future__ import annotations

import os
import time
from collections import deque
from datetime import datetime

import httpx
import socketio

from .config import API_URL, REALTIME_URL  # متغيرات البيئة ← server.json ← localhost
OFFLINE_MSG = "لا يوجد اتصال بالخادم."


class ApiError(Exception):
    def __init__(self, status: int, message: str, data: dict | None = None):
        super().__init__(message)
        self.status = status   # 0 = لا يوجد اتصال
        self.data = data or {}


class NetStats:
    """قياسات الشبكة الفعلية لكل طلب."""

    def __init__(self):
        self.requests = 0
        self.errors = 0
        self.bytes_up = 0
        self.bytes_down = 0
        self.latencies: deque[float] = deque(maxlen=30)
        self.last_ok: datetime | None = None
        self.last_error: str | None = None

    @property
    def avg_latency(self) -> float | None:
        return round(sum(self.latencies) / len(self.latencies), 1) if self.latencies else None


def _headers_size(headers: httpx.Headers) -> int:
    return sum(len(k) + len(v) + 4 for k, v in headers.raw)   # "key: value\r\n"


class Api:
    def __init__(self, base_url: str = API_URL):
        self.token: str | None = None
        self.force_offline = False
        self.stats = NetStats()
        self.http = httpx.Client(base_url=base_url, timeout=12)

    def _send(self, method: str, path: str, body: dict | None = None, query: dict | None = None,
              content: bytes | None = None, extra_headers: dict | None = None) -> dict:
        if self.force_offline:
            raise ApiError(0, OFFLINE_MSG)
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        headers.update(extra_headers or {})
        start = time.perf_counter()
        self.stats.requests += 1
        try:
            if content is not None:
                r = self.http.request(method, path, content=content, params=query,
                                      headers={"Content-Type": "application/json", **headers})
            else:
                r = self.http.request(method, path, json=body if method != "GET" else None, params=query,
                                      headers=headers)
        except httpx.TimeoutException:
            self._fail("انتهت مهلة الاتصال")
            raise ApiError(0, "الخادم لا يستجيب. حاول مرة أخرى.")
        except httpx.HTTPError:
            self._fail("تعذّر الاتصال")
            raise ApiError(0, OFFLINE_MSG + " تحقق من الإنترنت.")
        self.stats.latencies.append(round((time.perf_counter() - start) * 1000, 1))
        req = r.request
        self.stats.bytes_up += len(req.content or b"") + _headers_size(req.headers) + len(req.url.raw_path) + 16
        self.stats.bytes_down += len(r.content) + _headers_size(r.headers) + 17
        self.stats.last_ok = datetime.now()
        try:
            data = r.json()
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        if r.status_code >= 400:
            raise ApiError(r.status_code, str(data.get("error") or f"خطأ من الخادم ({r.status_code})"), data)
        return data

    def _fail(self, reason: str) -> None:
        self.stats.errors += 1
        self.stats.last_error = f"{datetime.now():%H:%M:%S} — {reason}"

    def get(self, path: str, query: dict | None = None) -> dict:
        return self._send("GET", path, query=query)

    def post(self, path: str, body: dict | None = None) -> dict:
        return self._send("POST", path, body or {})

    def get_text(self, path: str) -> str:
        """تنزيل ملف نصي (مثل CSV) بنفس المصادقة — TM351."""
        if self.force_offline:
            raise ApiError(0, OFFLINE_MSG)
        try:
            r = self.http.get(path, headers={"Authorization": f"Bearer {self.token}"} if self.token else {})
        except httpx.HTTPError:
            raise ApiError(0, OFFLINE_MSG)
        self.stats.requests += 1
        self.stats.bytes_down += len(r.content)
        if r.status_code >= 400:
            raise ApiError(r.status_code, f"خطأ من الخادم ({r.status_code})")
        return r.content.decode("utf-8-sig")

    def post_raw(self, path: str, content: bytes, headers: dict) -> dict:
        """إرسال بايتات جاهزة (مضغوطة) مع ترويسات خاصة — TM355."""
        return self._send("POST", path, content=content, extra_headers=headers)

    def patch(self, path: str, body: dict) -> dict:
        return self._send("PATCH", path, body)

    def delete(self, path: str, body: dict | None = None) -> dict:
        return self._send("DELETE", path, body or {})

    def health(self) -> float | None:
        """زمن الاستجابة بالملي ثانية لطلب صغير، أو None إذا لم يكن هناك اتصال."""
        try:
            start = time.perf_counter()
            self.get("/api/health/")
            return round((time.perf_counter() - start) * 1000, 1)
        except ApiError:
            return None


class BotSocket:
    """اتصال Socket.io غير متزامن. المعالجات تُسجَّل بـ on(event, coroutine)."""

    def __init__(self, url: str = REALTIME_URL):
        self.url = url
        self.sio: socketio.AsyncClient | None = None
        self.connected = False
        self.force_offline = False
        self.rtts: deque[float] = deque(maxlen=30)
        self._handlers: dict[str, object] = {}
        self.on_status = None   # تُستدعى عند تغيّر حالة الاتصال

    def on(self, event: str, handler) -> None:
        self._handlers[event] = handler

    async def connect(self, token: str) -> None:
        await self.disconnect()
        if self.force_offline:
            return
        sio = socketio.AsyncClient(reconnection=True)
        for event, handler in self._handlers.items():
            sio.on(event, handler)

        @sio.event
        async def connect():
            await self._set(True)

        @sio.event
        async def disconnect(*_):
            await self._set(False)

        self.sio = sio
        try:
            await sio.connect(self.url, auth={"token": token}, wait_timeout=5)
        except socketio.exceptions.ConnectionError:
            self.sio = None
            await self._set(False)

    async def _set(self, value: bool) -> None:
        changed = value != self.connected
        self.connected = value
        if changed and self.on_status:
            await self.on_status(value)

    async def call(self, event: str, data: dict, timeout: int = 15):
        if not self.sio or not self.connected:
            raise ApiError(0, "غير متصل بخادم الروبوت")
        return await self.sio.call(event, data, timeout=timeout)

    async def ping(self) -> float | None:
        try:
            start = time.perf_counter()
            await self.call("ping_rt", {}, timeout=5)
        except Exception:
            return None
        ms = round((time.perf_counter() - start) * 1000, 1)
        self.rtts.append(ms)
        return ms

    async def emit(self, event: str, data: dict) -> None:
        if self.sio and self.connected:
            await self.sio.emit(event, data)

    async def disconnect(self) -> None:
        sio, self.sio = self.sio, None
        if sio:
            try:
                await sio.disconnect()
            except Exception:
                pass
        await self._set(False)


def money(cents) -> str:
    return f"$ {(cents or 0) / 100:.2f}"
