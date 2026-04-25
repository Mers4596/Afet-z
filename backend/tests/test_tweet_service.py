"""
Tweet servisi testleri (mock'lanmış Twitter API).

Test edilen gereksinimler:
- Polling + cache mekanizması
- Spam refresh koruması (min 5 sn)
- Cache limiti (50)
- Mock tweet desteği
"""

import time
from unittest.mock import MagicMock, patch
from app.tweet_service import TweetService
from app.models import TweetData


class TestTweetServiceInit:
    """Servis başlatma testleri."""

    def test_init_defaults(self):
        svc = TweetService(bearer_token="test")
        assert svc.poll_interval == 30
        assert svc.cache_limit == 50
        assert svc.min_refresh_interval == 5
        assert svc.cache_size == 0

    def test_init_custom(self):
        svc = TweetService(
            bearer_token="t",
            username="test_user",
            poll_interval=60,
            cache_limit=100,
        )
        assert svc.username == "test_user"
        assert svc.poll_interval == 60
        assert svc.cache_limit == 100


class TestTweetServiceCache:
    """Cache mekanizması testleri."""

    def test_empty_cache(self):
        svc = TweetService(bearer_token="t")
        assert svc.get_cache() == []
        assert svc.cache_size == 0

    def test_mock_tweet_adds_to_cache(self):
        svc = TweetService(bearer_token="t")
        tweet = svc.add_mock_tweet("1", "Test tweet")
        assert isinstance(tweet, TweetData)
        assert svc.cache_size == 1
        assert svc.get_cache()[0].text == "Test tweet"

    def test_mock_tweet_prepends(self):
        """Yeni tweet cache'in başına eklenmeli."""
        svc = TweetService(bearer_token="t")
        svc.add_mock_tweet("1", "Birinci")
        svc.add_mock_tweet("2", "İkinci")
        cache = svc.get_cache()
        assert cache[0].text == "İkinci"
        assert cache[1].text == "Birinci"

    def test_cache_limit_enforced(self):
        """Cache limiti aşılmamalı."""
        svc = TweetService(bearer_token="t", cache_limit=5)
        for i in range(10):
            svc.add_mock_tweet(str(i), f"Tweet {i}")
        assert svc.cache_size == 5

    def test_cache_limit_default_50(self):
        """Varsayılan cache limiti 50."""
        svc = TweetService(bearer_token="t")
        for i in range(60):
            svc.add_mock_tweet(str(i), f"Tweet {i}")
        assert svc.cache_size == 50


class TestTweetServicePolling:
    """Polling mekanizması testleri."""

    def test_polling_interval_returns_cache(self):
        """Polling aralığı içinde API çağrılmamalı, cache dönmeli."""
        svc = TweetService(bearer_token="t", poll_interval=30)
        svc.add_mock_tweet("1", "Cached tweet")
        svc._last_fetch_time = time.time()  # Az önce çekilmiş

        # fetch_tweets çağrıldığında API çağrılmamalı, cache dönmeli
        result = svc.fetch_tweets()
        assert len(result) == 1
        assert result[0].text == "Cached tweet"


class TestTweetServiceSpamProtection:
    """Spam refresh koruması testleri."""

    def test_spam_refresh_blocked(self):
        """5 saniyeden kısa aralıkla force refresh engellenmeli."""
        svc = TweetService(bearer_token="t", min_refresh_interval=5)
        svc.add_mock_tweet("1", "Test")
        svc._last_fetch_time = time.time()  # Az önce çekilmiş

        # Force refresh 5 saniye içinde — cache dönmeli, API çağrılmamalı
        result = svc.fetch_tweets(force=True)
        assert len(result) == 1

    def test_spam_interval_customizable(self):
        """Spam aralığı özelleştirilebilir olmalı."""
        svc = TweetService(bearer_token="t", min_refresh_interval=10)
        assert svc.min_refresh_interval == 10
