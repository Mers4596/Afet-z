"""
Tweet servisi — Twitter API polling + cache mekanizması.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from app.models import TweetData

logger = logging.getLogger(__name__)


class TweetService:
    """Twitter API polling + cache yönetimi."""

    def __init__(
        self,
        bearer_token: str,
        username: str = "meh56954",
        poll_interval: int = 30,
        cache_limit: int = 50,
        max_results: int = 5,
        min_refresh_interval: int = 5,
    ):
        self.bearer_token = bearer_token
        self.username = username
        self.poll_interval = poll_interval
        self.cache_limit = cache_limit
        self.max_results = max_results
        self.min_refresh_interval = min_refresh_interval

        self._cache: list[TweetData] = []
        self._last_id: Optional[str] = None
        self._last_fetch_time: float = 0.0
        self._user_id: Optional[str] = None
        self._client = None

    def _get_client(self):
        """Lazy-init Tweepy client."""
        if self._client is None:
            import tweepy
            self._client = tweepy.Client(
                bearer_token=self.bearer_token,
                wait_on_rate_limit=True,
            )
        return self._client

    def _resolve_user_id(self) -> str:
        """Username'den user ID çöz."""
        if self._user_id is None:
            client = self._get_client()
            user = client.get_user(username=self.username)
            if user.data is None:
                raise ValueError(f"Kullanıcı bulunamadı: {self.username}")
            self._user_id = str(user.data.id)
        return self._user_id

    def fetch_tweets(self, force: bool = False) -> list[TweetData]:
        """Tweet'leri çek. Cache + rate-limit koruması."""
        now = time.time()

        # Spam refresh koruması
        if force and now - self._last_fetch_time < self.min_refresh_interval:
            return self._cache

        # Normal polling aralığı
        if not force and now - self._last_fetch_time < self.poll_interval:
            return self._cache

        try:
            user_id = self._resolve_user_id()
            client = self._get_client()

            kwargs = {"id": user_id, "max_results": self.max_results}
            if self._last_id:
                kwargs["since_id"] = self._last_id

            tweets = client.get_users_tweets(**kwargs)

            if tweets.data:
                new_tweets = []
                for t in reversed(tweets.data):
                    tweet_data = TweetData(tweet_id=str(t.id), text=t.text)
                    new_tweets.append(tweet_data)
                    self._last_id = str(t.id)

                self._cache = new_tweets + self._cache
                self._cache = self._cache[: self.cache_limit]

            self._last_fetch_time = now

        except Exception as e:
            logger.error("Tweet çekme hatası: %s", e)

        return self._cache

    def get_cache(self) -> list[TweetData]:
        """Mevcut cache'i döndür."""
        return self._cache

    def add_mock_tweet(self, tweet_id: str, text: str) -> TweetData:
        """Test/demo için mock tweet ekle."""
        tweet = TweetData(tweet_id=tweet_id, text=text)
        self._cache.insert(0, tweet)
        self._cache = self._cache[: self.cache_limit]
        return tweet

    @property
    def cache_size(self) -> int:
        return len(self._cache)
