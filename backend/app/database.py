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
                need_types TEXT DEFAULT '[]',
                urgency_score INTEGER DEFAULT 0,
                confidence REAL DEFAULT 0.0,
                summary TEXT DEFAULT '',
                map_priority TEXT DEFAULT 'low',
                error TEXT,
                analyzed_at TEXT NOT NULL
            )
        """)
        self._conn.commit()

    def save_analysis(self, tweet_id: str, text: str, analysis: Optional[TweetAnalysis], error: Optional[str] = None) -> None:
        """Analiz sonucunu kaydet."""
        assert self._conn is not None
        now = datetime.now(timezone.utc).isoformat()

        if analysis:
            self._conn.execute(
                """INSERT OR REPLACE INTO analyzed_tweets
                   (tweet_id, text, city, district, neighborhood, need_types,
                    urgency_score, confidence, summary, map_priority, error, analyzed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    tweet_id, text, analysis.city, analysis.district,
                    analysis.neighborhood, json.dumps(analysis.need_types),
                    analysis.urgency_score, analysis.confidence,
                    analysis.summary, analysis.map_priority, error, now,
                ),
            )
        else:
            self._conn.execute(
                """INSERT OR REPLACE INTO analyzed_tweets
                   (tweet_id, text, error, analyzed_at)
                   VALUES (?, ?, ?, ?)""",
                (tweet_id, text, error, now),
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
                    need_types=json.loads(row["need_types"] or "[]"),
                    urgency_score=row["urgency_score"] or 1,
                    confidence=row["confidence"] or 0.0,
                    summary=row["summary"] or "",
                    map_priority=row["map_priority"] or "low",
                )
            results.append(AnalyzedTweet(
                tweet_id=row["tweet_id"],
                text=row["text"],
                analysis=analysis,
                analyzed_at=row["analyzed_at"],
                error=row["error"],
            ))
        return results

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
                need_types=json.loads(row["need_types"] or "[]"),
                urgency_score=row["urgency_score"] or 1,
                confidence=row["confidence"] or 0.0,
                summary=row["summary"] or "",
                map_priority=row["map_priority"] or "low",
            )
            results.append(AnalyzedTweet(
                tweet_id=row["tweet_id"],
                text=row["text"],
                analysis=analysis,
                analyzed_at=row["analyzed_at"],
                error=row["error"],
            ))
        return results

    def close(self) -> None:
        """Bağlantıyı kapat."""
        if self._conn:
            self._conn.close()
            self._conn = None
