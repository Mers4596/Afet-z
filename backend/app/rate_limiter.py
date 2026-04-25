"""
Gemini API rate-limit koruyucu.

Gemini 3.1 Flash Lite limitleri:
  - 15 RPM  (request per minute)
  - 250K TPM (token per minute)
  - 500 RPD (request per day)

Bu modül, istek göndermeden önce limitlere uyulup uyulmadığını kontrol eder
ve gerekirse bekler / reddeder.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class RateLimiter:
    """Thread-safe sliding-window rate limiter."""

    max_rpm: int = 15
    max_rpd: int = 500

    # ── iç durum ──
    _minute_window: deque = field(default_factory=deque)
    _day_window: deque = field(default_factory=deque)
    _lock: Lock = field(default_factory=Lock)

    # ── genel sayaçlar (test/monitoring) ──
    total_requests: int = 0

    def _purge(self, now: float) -> None:
        """Süresi dolmuş kayıtları temizle."""
        minute_ago = now - 60
        day_ago = now - 86_400

        while self._minute_window and self._minute_window[0] < minute_ago:
            self._minute_window.popleft()

        while self._day_window and self._day_window[0] < day_ago:
            self._day_window.popleft()

    def can_request(self) -> bool:
        """Yeni istek gönderebilir miyiz?"""
        with self._lock:
            now = time.time()
            self._purge(now)
            return (
                len(self._minute_window) < self.max_rpm
                and len(self._day_window) < self.max_rpd
            )

    def record_request(self) -> None:
        """Başarılı isteği kaydet."""
        with self._lock:
            now = time.time()
            self._purge(now)
            self._minute_window.append(now)
            self._day_window.append(now)
            self.total_requests += 1

    def acquire(self) -> bool:
        """
        Slot varsa kaydet ve True döndür; yoksa False döndür.
        Atomik check-and-record.
        """
        with self._lock:
            now = time.time()
            self._purge(now)
            if (
                len(self._minute_window) < self.max_rpm
                and len(self._day_window) < self.max_rpd
            ):
                self._minute_window.append(now)
                self._day_window.append(now)
                self.total_requests += 1
                return True
            return False

    def status(self) -> dict:
        """Mevcut rate-limit durumunu döndür."""
        with self._lock:
            now = time.time()
            self._purge(now)
            rpm_used = len(self._minute_window)
            rpd_used = len(self._day_window)
            return {
                "requests_this_minute": rpm_used,
                "requests_today": rpd_used,
                "max_rpm": self.max_rpm,
                "max_rpd": self.max_rpd,
                "remaining_rpm": self.max_rpm - rpm_used,
                "remaining_rpd": self.max_rpd - rpd_used,
            }

    def wait_time_seconds(self) -> float:
        """
        En erken ne zaman yeni istek gönderebiliriz?
        0.0 → hemen gönderebilirsin.
        """
        with self._lock:
            now = time.time()
            self._purge(now)

            if len(self._day_window) >= self.max_rpd:
                # Günlük limit doldu, en eski kayıt süresi dolana kadar bekle
                return max(0.0, self._day_window[0] + 86_400 - now)

            if len(self._minute_window) >= self.max_rpm:
                # Dakikalık limit doldu
                return max(0.0, self._minute_window[0] + 60 - now)

            return 0.0
