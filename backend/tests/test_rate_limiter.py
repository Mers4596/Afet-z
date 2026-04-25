"""
Rate Limiter unit testleri.

Test edilen gereksinimler:
- Gemini 3.1 Flash Lite: 15 RPM, 500 RPD
- Sliding window mekanizması
- Thread-safety
- Atomik acquire
"""

import time
from unittest.mock import patch
from app.rate_limiter import RateLimiter


class TestRateLimiterBasic:
    """Temel rate limiter fonksiyonelliği."""

    def test_initial_state_allows_request(self):
        """Başlangıçta istek gönderilebilmeli."""
        rl = RateLimiter(max_rpm=15, max_rpd=500)
        assert rl.can_request() is True

    def test_initial_status(self):
        """Başlangıç durumu doğru olmalı."""
        rl = RateLimiter(max_rpm=15, max_rpd=500)
        status = rl.status()
        assert status["requests_this_minute"] == 0
        assert status["requests_today"] == 0
        assert status["max_rpm"] == 15
        assert status["max_rpd"] == 500
        assert status["remaining_rpm"] == 15
        assert status["remaining_rpd"] == 500

    def test_record_request_increments(self):
        """İstek kaydı sayaçları artırmalı."""
        rl = RateLimiter(max_rpm=15, max_rpd=500)
        rl.record_request()
        status = rl.status()
        assert status["requests_this_minute"] == 1
        assert status["requests_today"] == 1
        assert rl.total_requests == 1

    def test_acquire_returns_true_when_available(self):
        """Slot varken acquire True döndürmeli."""
        rl = RateLimiter(max_rpm=15, max_rpd=500)
        assert rl.acquire() is True
        assert rl.total_requests == 1

    def test_wait_time_zero_initially(self):
        """Başlangıçta bekleme süresi 0 olmalı."""
        rl = RateLimiter(max_rpm=15, max_rpd=500)
        assert rl.wait_time_seconds() == 0.0


class TestRateLimiterRPM:
    """Dakikalık limit (RPM) testleri."""

    def test_rpm_limit_blocks_requests(self):
        """RPM limiti aşılınca istek engellenmeli."""
        rl = RateLimiter(max_rpm=3, max_rpd=500)
        for _ in range(3):
            assert rl.acquire() is True
        # 4. istek engellenmeli
        assert rl.can_request() is False
        assert rl.acquire() is False

    def test_rpm_status_after_limit(self):
        """RPM limiti dolunca durum doğru raporlanmalı."""
        rl = RateLimiter(max_rpm=3, max_rpd=500)
        for _ in range(3):
            rl.acquire()
        status = rl.status()
        assert status["remaining_rpm"] == 0
        assert status["requests_this_minute"] == 3

    def test_rpm_window_slides(self):
        """Dakikalık pencere kaymalı — eski istekler düşmeli."""
        rl = RateLimiter(max_rpm=2, max_rpd=500)

        # 2 istek yap
        rl.acquire()
        rl.acquire()
        assert rl.can_request() is False

        # Zamanı 61 saniye ileri sar
        with patch("app.rate_limiter.time.time", return_value=time.time() + 61):
            assert rl.can_request() is True

    def test_rpm_wait_time(self):
        """RPM limiti dolunca bekleme süresi > 0 olmalı."""
        rl = RateLimiter(max_rpm=2, max_rpd=500)
        rl.acquire()
        rl.acquire()
        wait = rl.wait_time_seconds()
        assert wait > 0
        assert wait <= 60


class TestRateLimiterRPD:
    """Günlük limit (RPD) testleri."""

    def test_rpd_limit_blocks_requests(self):
        """RPD limiti aşılınca istek engellenmeli."""
        rl = RateLimiter(max_rpm=100, max_rpd=5)
        for _ in range(5):
            assert rl.acquire() is True
        assert rl.can_request() is False
        assert rl.acquire() is False

    def test_rpd_status_after_limit(self):
        """RPD limiti dolunca durum doğru raporlanmalı."""
        rl = RateLimiter(max_rpm=100, max_rpd=5)
        for _ in range(5):
            rl.acquire()
        status = rl.status()
        assert status["remaining_rpd"] == 0
        assert status["requests_today"] == 5

    def test_rpd_wait_time_when_full(self):
        """RPD limiti dolunca bekleme süresi çok büyük olmalı."""
        rl = RateLimiter(max_rpm=100, max_rpd=3)
        for _ in range(3):
            rl.acquire()
        wait = rl.wait_time_seconds()
        # Günlük limit dolmuş, en az birkaç saat beklenmeli
        assert wait > 3600

    def test_rpd_window_slides(self):
        """Günlük pencere kaymalı — 24 saat sonra düşmeli."""
        rl = RateLimiter(max_rpm=100, max_rpd=2)
        rl.acquire()
        rl.acquire()
        assert rl.can_request() is False

        # 24 saat + 1 saniye ileri sar
        with patch("app.rate_limiter.time.time", return_value=time.time() + 86401):
            assert rl.can_request() is True


class TestRateLimiterGeminiDefaults:
    """Gemini 3.1 Flash Lite varsayılan limitleriyle testler."""

    def test_default_limits_match_docs(self):
        """Varsayılan limitler dökümana uymalı: 15 RPM, 500 RPD."""
        rl = RateLimiter()
        assert rl.max_rpm == 15
        assert rl.max_rpd == 500

    def test_fifteen_requests_allowed(self):
        """15 istek dakikada kabul edilmeli."""
        rl = RateLimiter()
        for i in range(15):
            assert rl.acquire() is True, f"İstek {i+1} reddedildi"

    def test_sixteenth_request_blocked(self):
        """16. istek dakikada engelllenmeli."""
        rl = RateLimiter()
        for _ in range(15):
            rl.acquire()
        assert rl.acquire() is False

    def test_five_hundred_requests_daily(self):
        """500 istek günlük kabul edilmeli (RPM'i bypass ederek)."""
        rl = RateLimiter(max_rpm=1000, max_rpd=500)  # RPM'i yükselt
        for i in range(500):
            assert rl.acquire() is True, f"İstek {i+1} reddedildi"
        assert rl.acquire() is False


class TestRateLimiterThreadSafety:
    """Thread-safety testleri."""

    def test_concurrent_acquire(self):
        """Eşzamanlı acquire çağrıları toplam limiti aşmamalı."""
        import threading

        rl = RateLimiter(max_rpm=10, max_rpd=500)
        results = []
        lock = threading.Lock()

        def worker():
            r = rl.acquire()
            with lock:
                results.append(r)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Tam 10 True, 10 False olmalı
        assert results.count(True) == 10
        assert results.count(False) == 10
