"""
SQLite veritabanı katmanı — analiz edilen tweet'leri saklar.
"""

from __future__ import annotations

import json
import sqlite3
import logging
from datetime import datetime, timezone
from typing import Optional

from app.models import TweetAnalysis, AnalyzedTweet

logger = logging.getLogger(__name__)


class Database:
    """SQLite veritabanı yöneticisi."""

    def __init__(self, db_path: str = "afet_haritasi.db"):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self) -> None:
        """Veritabanına bağlan ve tabloları oluştur."""
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        """Gerekli tabloları oluştur."""
        assert self._conn is not None
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS analyzed_tweets (
                tweet_id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                city TEXT DEFAULT '',
                district TEXT DEFAULT '',
                neighborhood TEXT DEFAULT '',
                street_address TEXT DEFAULT '',
                has_precise_location INTEGER DEFAULT 0,
                need_types TEXT DEFAULT '[]',
                urgency_score INTEGER DEFAULT 0,
                confidence REAL DEFAULT 0.0,
                summary TEXT DEFAULT '',
                map_priority TEXT DEFAULT 'low',
                error TEXT,
                analyzed_at TEXT NOT NULL,
                author_id TEXT DEFAULT '',
                author_username TEXT DEFAULT ''
            )
        """)
        # Mevcut tabloya sütun ekle (eski DB varsa)
        for col, typedef in [
            ("author_id", "TEXT DEFAULT ''"),
            ("author_username", "TEXT DEFAULT ''"),
            ("street_address", "TEXT DEFAULT ''"),
            ("has_precise_location", "INTEGER DEFAULT 0"),
        ]:
            try:
                self._conn.execute(
                    f"ALTER TABLE analyzed_tweets ADD COLUMN {col} {typedef}"
                )
            except sqlite3.OperationalError:
                pass  # Sütun zaten var

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS trusted_accounts (
                username TEXT PRIMARY KEY,
                added_at TEXT NOT NULL,
                note TEXT DEFAULT ''
            )
        """)
        self._conn.commit()

    def save_analysis(
        self,
        tweet_id: str,
        text: str,
        analysis: Optional[TweetAnalysis],
        error: Optional[str] = None,
        author_id: str = "",
        author_username: str = "",
    ) -> None:
        """Analiz sonucunu kaydet."""
        assert self._conn is not None
        now = datetime.now(timezone.utc).isoformat()

        if analysis:
            self._conn.execute(
                """INSERT OR REPLACE INTO analyzed_tweets
                   (tweet_id, text, city, district, neighborhood, street_address,
                    has_precise_location, need_types,
                    urgency_score, confidence, summary, map_priority, error,
                    analyzed_at, author_id, author_username)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    tweet_id, text, analysis.city, analysis.district,
                    analysis.neighborhood, analysis.street_address,
                    int(analysis.has_precise_location),
                    json.dumps(analysis.need_types),
                    analysis.urgency_score, analysis.confidence,
                    analysis.summary, analysis.map_priority, error, now,
                    author_id, author_username,
                ),
            )
        else:
            self._conn.execute(
                """INSERT OR REPLACE INTO analyzed_tweets
                   (tweet_id, text, error, analyzed_at, author_id, author_username)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (tweet_id, text, error, now, author_id, author_username),
            )
        self._conn.commit()

    def get_all_analyses(self) -> list[AnalyzedTweet]:
        """Tüm analiz sonuçlarını getir."""
        assert self._conn is not None
        cursor = self._conn.execute(
            "SELECT * FROM analyzed_tweets ORDER BY analyzed_at DESC"
        )
        results = []
        for row in cursor.fetchall():
            analysis = None
            if row["city"]:
                analysis = TweetAnalysis(
                    city=row["city"],
                    district=row["district"] or "",
                    neighborhood=row["neighborhood"] or "",
                    street_address=row["street_address"] or "",
                    has_precise_location=bool(row["has_precise_location"]),
                    need_types=json.loads(row["need_types"] or "[]"),
                    urgency_score=row["urgency_score"] or 1,
                    confidence=row["confidence"] or 0.0,
                    summary=row["summary"] or "",
                    map_priority=row["map_priority"] or "low",
                )
            from app.models import UserProfile
            author = None
            if row["author_username"]:
                author = UserProfile(
                    author_id=row["author_id"] or "",
                    username=row["author_username"] or "",
                )
            results.append(AnalyzedTweet(
                tweet_id=row["tweet_id"],
                text=row["text"],
                analysis=analysis,
                analyzed_at=row["analyzed_at"],
                error=row["error"],
                author=author,
            ))
        return results

    def get_city_tweet_counts(self) -> dict[str, int]:
        """Şehir+ilçe bazında tweet sayılarını döndür (trust hesabı için)."""
        assert self._conn is not None
        cursor = self._conn.execute(
            "SELECT city, district, COUNT(*) as cnt FROM analyzed_tweets "
            "WHERE city != '' AND city != 'Bilinmiyor' GROUP BY city, district"
        )
        result: dict[str, int] = {}
        for row in cursor.fetchall():
            key = f"{row['city']}||{row['district'] or ''}"
            result[key] = row["cnt"]
        return result

    def get_by_priority(self, priority: str) -> list[AnalyzedTweet]:
        """Belirli öncelik seviyesindeki tweet'leri getir."""
        assert self._conn is not None
        cursor = self._conn.execute(
            "SELECT * FROM analyzed_tweets WHERE map_priority = ? ORDER BY analyzed_at DESC",
            (priority,),
        )
        results = []
        for row in cursor.fetchall():
            analysis = TweetAnalysis(
                city=row["city"],
                district=row["district"] or "",
                neighborhood=row["neighborhood"] or "",
                street_address=row["street_address"] or "",
                has_precise_location=bool(row["has_precise_location"]),
                need_types=json.loads(row["need_types"] or "[]"),
                urgency_score=row["urgency_score"] or 1,
                confidence=row["confidence"] or 0.0,
                summary=row["summary"] or "",
                map_priority=row["map_priority"] or "low",
            )
            from app.models import UserProfile
            author = None
            if row["author_username"]:
                author = UserProfile(
                    author_id=row["author_id"] or "",
                    username=row["author_username"] or "",
                )
            results.append(AnalyzedTweet(
                tweet_id=row["tweet_id"],
                text=row["text"],
                analysis=analysis,
                analyzed_at=row["analyzed_at"],
                error=row["error"],
                author=author,
            ))
        return results

    # ── Güvenilir Hesaplar ───────────────────────────────
    def add_trusted_account(self, username: str, note: str = "") -> None:
        """Güvenilir hesap ekle."""
        assert self._conn is not None
        now = datetime.now(timezone.utc).isoformat()
        # Kullanıcı adını küçük harfe normalize et
        self._conn.execute(
            "INSERT OR REPLACE INTO trusted_accounts (username, added_at, note) VALUES (?, ?, ?)",
            (username.lower().strip(), now, note),
        )
        self._conn.commit()

    def remove_trusted_account(self, username: str) -> None:
        """Güvenilir hesabı sil."""
        assert self._conn is not None
        self._conn.execute(
            "DELETE FROM trusted_accounts WHERE username = ?",
            (username.lower().strip(),),
        )
        self._conn.commit()

    def get_trusted_accounts(self) -> list[dict]:
        """Tüm güvenilir hesapları getir."""
        assert self._conn is not None
        cursor = self._conn.execute(
            "SELECT username, added_at, note FROM trusted_accounts ORDER BY added_at DESC"
        )
        return [dict(row) for row in cursor.fetchall()]

    def is_trusted(self, username: str) -> bool:
        """Kullanıcı güvenilir listesinde mi?"""
        if not username:
            return False
        assert self._conn is not None
        cursor = self._conn.execute(
            "SELECT 1 FROM trusted_accounts WHERE username = ?",
            (username.lower().strip(),),
        )
        return cursor.fetchone() is not None

    def close(self) -> None:
        """Bağlantıyı kapat."""
        if self._conn:
            self._conn.close()
            self._conn = None
