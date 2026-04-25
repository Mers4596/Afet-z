"""
Tweet servisi — Twitter API polling + hashtag araması + kullanıcı profili.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from app.models import TweetData, UserProfile

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

        # Hashtag araması için ayrı cache
        self._hashtag_cache: list[TweetData] = []
        self._last_hashtag_id: Optional[str] = None
        self._last_hashtag_fetch: float = 0.0

        # Kullanıcı profil önbelleği (author_id → UserProfile)
        self._user_profile_cache: dict[str, UserProfile] = {}

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

    def _parse_user_profile(self, user_obj) -> UserProfile:
        """Tweepy User nesnesinden UserProfile oluştur."""
        created_at = getattr(user_obj, "created_at", None)
        age_days = 0
        if created_at:
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(
                    created_at.replace("Z", "+00:00")
                )
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            age_days = max(0, (datetime.now(timezone.utc) - created_at).days)

        metrics = getattr(user_obj, "public_metrics", None) or {}
        return UserProfile(
            author_id=str(user_obj.id),
            username=getattr(user_obj, "username", "") or "",
            account_age_days=age_days,
            followers=metrics.get("followers_count", 0),
            following=metrics.get("following_count", 0),
            tweet_count=metrics.get("tweet_count", 0),
            credibility_score=0.0,  # CredibilityService tarafından hesaplanır
            is_trusted=False,
        )

    def fetch_user_profile(self, author_id: str) -> Optional[UserProfile]:
        """Tek bir kullanıcının profilini çek (önbellekli)."""
        if author_id in self._user_profile_cache:
            return self._user_profile_cache[author_id]
        try:
            client = self._get_client()
            resp = client.get_user(
                id=author_id,
                user_fields=["created_at", "public_metrics", "username"],
            )
            if resp.data:
                profile = self._parse_user_profile(resp.data)
                self._user_profile_cache[author_id] = profile
                return profile
        except Exception as e:
            logger.warning("Kullanıcı profili çekilemedi (id=%s): %s", author_id, e)
        return None

    # ── Kullanıcı Tweet'leri (mevcut) ────────────────────
    def fetch_tweets(self, force: bool = False) -> list[TweetData]:
        """Tweet'leri çek. Cache + rate-limit koruması."""
        now = time.time()

        if force and now - self._last_fetch_time < self.min_refresh_interval:
            return self._cache
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

    # ── #afetiz Hashtag Araması ───────────────────────────
    def fetch_hashtag_tweets(self, force: bool = False) -> list[TweetData]:
        """
        #afetiz hashtagiyle paylaşılan son tweet'leri çek.
        Yazar bilgileri ve hesap profili de dahil edilir.
        """
        now = time.time()

        if force and now - self._last_hashtag_fetch < self.min_refresh_interval:
            return self._hashtag_cache
        if not force and now - self._last_hashtag_fetch < self.poll_interval:
            return self._hashtag_cache

        try:
            client = self._get_client()

            kwargs: dict = {
                "query": "#afetiz lang:tr -is:retweet",
                "max_results": max(10, self.max_results),
                "expansions": ["author_id"],
                "user_fields": ["created_at", "public_metrics", "username"],
                "tweet_fields": ["created_at", "author_id"],
            }
            if self._last_hashtag_id:
                kwargs["since_id"] = self._last_hashtag_id

            response = client.search_recent_tweets(**kwargs)

            if not response.data:
                self._last_hashtag_fetch = now
                return self._hashtag_cache

            # Kullanıcı map'i oluştur
            user_map: dict[str, object] = {}
            includes = getattr(response, "includes", None) or {}
            for u in includes.get("users", []):
                uid = str(u.id)
                user_map[uid] = u
                self._user_profile_cache[uid] = self._parse_user_profile(u)

            new_tweets: list[TweetData] = []
            for t in response.data:
                author_id = str(t.author_id) if getattr(t, "author_id", None) else ""
                author_username = ""
                user_profile: Optional[UserProfile] = None

                if author_id and author_id in self._user_profile_cache:
                    user_profile = self._user_profile_cache[author_id]
                    author_username = user_profile.username

                created_at_raw = getattr(t, "created_at", None)
                created_at_str: Optional[str] = None
                if created_at_raw:
                    created_at_str = (
                        created_at_raw.isoformat()
                        if hasattr(created_at_raw, "isoformat")
                        else str(created_at_raw)
                    )

                tweet_data = TweetData(
                    tweet_id=str(t.id),
                    text=t.text,
                    author_id=author_id,
                    author_username=author_username,
                    created_at=created_at_str,
                    user_profile=user_profile,
                )
                new_tweets.append(tweet_data)
                self._last_hashtag_id = str(t.id)

            # Önbelleğe ekle (tekrar yoksa)
            existing_ids = {td.tweet_id for td in self._hashtag_cache}
            for td in reversed(new_tweets):
                if td.tweet_id not in existing_ids:
                    self._hashtag_cache.insert(0, td)
            self._hashtag_cache = self._hashtag_cache[: self.cache_limit]
            self._last_hashtag_fetch = now

        except Exception as e:
            logger.error("Hashtag tweet çekme hatası: %s", e)

        return self._hashtag_cache

    def get_hashtag_cache(self) -> list[TweetData]:
        """Mevcut hashtag cache'ini döndür."""
        return self._hashtag_cache

    def get_cache(self) -> list[TweetData]:
        """Mevcut kullanıcı cache'ini döndür."""
        return self._cache

    def get_all_cached(self) -> list[TweetData]:
        """Hem kullanıcı hem hashtag cache'lerini birleştirip döndür."""
        seen: set[str] = set()
        result: list[TweetData] = []
        for t in self._hashtag_cache + self._cache:
            if t.tweet_id not in seen:
                seen.add(t.tweet_id)
                result.append(t)
        return result[: self.cache_limit]

    def add_mock_tweet(self, tweet_id: str, text: str) -> TweetData:
        """Test/demo için mock tweet ekle."""
        tweet = TweetData(tweet_id=tweet_id, text=text)
        self._cache.insert(0, tweet)
        self._cache = self._cache[: self.cache_limit]
        return tweet

    @property
    def cache_size(self) -> int:
        return len(self._cache) + len(self._hashtag_cache)
