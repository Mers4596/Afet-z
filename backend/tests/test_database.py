"""
Veritabanı katmanı testleri.

Test edilen gereksinimler:
- SQLite tablo oluşturma
- Analiz sonucu kaydetme / okuma
- Önceliğe göre filtreleme
"""

import os
import pytest
from app.database import Database
from app.models import TweetAnalysis


@pytest.fixture
def db(tmp_path):
    """Her test için temiz bir veritabanı."""
    db_path = str(tmp_path / "test.db")
    database = Database(db_path=db_path)
    database.connect()
    yield database
    database.close()


class TestDatabaseInit:
    """Veritabanı başlatma testleri."""

    def test_creates_db_file(self, tmp_path):
        db_path = str(tmp_path / "new.db")
        database = Database(db_path=db_path)
        database.connect()
        assert os.path.exists(db_path)
        database.close()

    def test_table_created(self, db):
        """analyzed_tweets tablosu oluşmalı."""
        cursor = db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='analyzed_tweets'"
        )
        assert cursor.fetchone() is not None


class TestDatabaseSaveAndRead:
    """Kaydetme ve okuma testleri."""

    def test_save_and_retrieve(self, db):
        """Analiz kaydedip geri okunabilmeli."""
        analysis = TweetAnalysis(
            city="Hatay",
            district="Antakya",
            neighborhood="Cumhuriyet",
            need_types=["arama_kurtarma", "saglik"],
            urgency_score=5,
            confidence=0.92,
            summary="Enkaz altında yaralılar",
            map_priority="critical",
        )
        db.save_analysis("tweet1", "Test tweet metni", analysis)

        results = db.get_all_analyses()
        assert len(results) == 1
        assert results[0].tweet_id == "tweet1"
        assert results[0].analysis.city == "Hatay"
        assert results[0].analysis.urgency_score == 5

    def test_save_with_error(self, db):
        """Hatalı analiz kaydedilebilmeli."""
        db.save_analysis("tweet2", "Hatalı tweet", None, "Rate limit aşıldı")

        results = db.get_all_analyses()
        assert len(results) == 1
        assert results[0].error == "Rate limit aşıldı"
        assert results[0].analysis is None

    def test_save_multiple(self, db):
        """Birden fazla analiz kaydedilebilmeli."""
        for i in range(5):
            analysis = TweetAnalysis(
                city=f"Şehir{i}", urgency_score=i + 1, confidence=0.5,
            )
            db.save_analysis(f"t{i}", f"Tweet {i}", analysis)

        results = db.get_all_analyses()
        assert len(results) == 5

    def test_upsert_on_same_id(self, db):
        """Aynı ID ile kayıt güncellenebilmeli."""
        a1 = TweetAnalysis(city="İstanbul", urgency_score=2, confidence=0.5)
        db.save_analysis("dup", "İlk", a1)

        a2 = TweetAnalysis(city="Ankara", urgency_score=4, confidence=0.8)
        db.save_analysis("dup", "Güncel", a2)

        results = db.get_all_analyses()
        assert len(results) == 1
        assert results[0].analysis.city == "Ankara"


class TestDatabasePriorityFilter:
    """Öncelik filtreleme testleri."""

    def test_filter_by_priority(self, db):
        """Önceliğe göre filtreleme çalışmalı."""
        priorities = [
            ("t1", "critical", 5),
            ("t2", "critical", 5),
            ("t3", "high", 4),
            ("t4", "medium", 3),
            ("t5", "low", 1),
        ]
        for tid, pri, score in priorities:
            analysis = TweetAnalysis(
                city="X", urgency_score=score, confidence=0.5, map_priority=pri,
            )
            db.save_analysis(tid, f"Tweet {tid}", analysis)

        critical = db.get_by_priority("critical")
        assert len(critical) == 2

        high = db.get_by_priority("high")
        assert len(high) == 1

        low = db.get_by_priority("low")
        assert len(low) == 1

    def test_filter_empty_result(self, db):
        """Olmayan öncelik boş liste döndürmeli."""
        results = db.get_by_priority("critical")
        assert results == []


class TestDatabaseNeedTypes:
    """İhtiyaç türleri JSON serileştirme testleri."""

    def test_need_types_roundtrip(self, db):
        """İhtiyaç türleri JSON olarak saklanıp geri okunabilmeli."""
        needs = ["arama_kurtarma", "saglik", "su", "gida"]
        analysis = TweetAnalysis(
            city="Hatay", need_types=needs, urgency_score=5, confidence=0.9,
        )
        db.save_analysis("t1", "Test", analysis)

        results = db.get_all_analyses()
        assert results[0].analysis.need_types == needs
