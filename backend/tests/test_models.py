"""
Pydantic model testleri.

Test edilen gereksinimler:
- JSON çıktı formatı doğrulaması (project-idea.md)
- İhtiyaç türleri, aciliyet skorları
- Validation kuralları
"""

import pytest
from pydantic import ValidationError
from app.models import (
    TweetAnalysis,
    TweetData,
    AnalyzedTweet,
    NeedType,
    MapPriority,
    AnalyzeRequest,
    RateLimitStatus,
)


class TestTweetAnalysis:
    """TweetAnalysis model testleri — Gemini JSON çıktı formatı."""

    def test_valid_analysis(self):
        """Geçerli analiz verisi kabul edilmeli."""
        data = {
            "city": "Hatay",
            "district": "Antakya",
            "neighborhood": "Cumhuriyet Mahallesi",
            "need_types": ["arama_kurtarma", "saglik", "su"],
            "urgency_score": 5,
            "confidence": 0.86,
            "summary": "Enkaz altında yaralı kişiler var",
            "map_priority": "critical",
        }
        analysis = TweetAnalysis(**data)
        assert analysis.city == "Hatay"
        assert analysis.urgency_score == 5
        assert "arama_kurtarma" in analysis.need_types
        assert analysis.confidence == 0.86

    def test_minimal_analysis(self):
        """Minimum zorunlu alanlarla oluşturulabilmeli."""
        analysis = TweetAnalysis(
            city="İstanbul",
            urgency_score=1,
            confidence=0.5,
        )
        assert analysis.city == "İstanbul"
        assert analysis.need_types == []
        assert analysis.district == ""

    def test_urgency_score_range(self):
        """Aciliyet skoru 1-5 arasında olmalı."""
        # Geçerli
        for score in range(1, 6):
            a = TweetAnalysis(city="X", urgency_score=score, confidence=0.5)
            assert a.urgency_score == score

        # Geçersiz — 0
        with pytest.raises(ValidationError):
            TweetAnalysis(city="X", urgency_score=0, confidence=0.5)

        # Geçersiz — 6
        with pytest.raises(ValidationError):
            TweetAnalysis(city="X", urgency_score=6, confidence=0.5)

    def test_confidence_range(self):
        """Güven skoru 0.0-1.0 arasında olmalı."""
        TweetAnalysis(city="X", urgency_score=1, confidence=0.0)
        TweetAnalysis(city="X", urgency_score=1, confidence=1.0)

        with pytest.raises(ValidationError):
            TweetAnalysis(city="X", urgency_score=1, confidence=1.5)

        with pytest.raises(ValidationError):
            TweetAnalysis(city="X", urgency_score=1, confidence=-0.1)

    def test_json_serialization(self):
        """JSON serileştirme doğru çalışmalı."""
        analysis = TweetAnalysis(
            city="Hatay",
            district="Antakya",
            neighborhood="Cumhuriyet",
            need_types=["saglik"],
            urgency_score=4,
            confidence=0.9,
            summary="Test",
            map_priority="high",
        )
        data = analysis.model_dump()
        assert isinstance(data, dict)
        assert data["city"] == "Hatay"
        assert data["urgency_score"] == 4


class TestNeedType:
    """İhtiyaç türleri enum testleri."""

    def test_all_need_types_exist(self):
        """Dokümandaki tüm ihtiyaç türleri tanımlı olmalı."""
        expected = [
            "arama_kurtarma", "saglik", "su", "gida",
            "barinma", "yol_kapali", "yangin", "elektrik_iletisim",
        ]
        for need in expected:
            assert NeedType(need) is not None

    def test_need_type_values(self):
        assert NeedType.ARAMA_KURTARMA.value == "arama_kurtarma"
        assert NeedType.SAGLIK.value == "saglik"


class TestMapPriority:
    """Harita önceliği enum testleri."""

    def test_all_priorities_exist(self):
        expected = ["critical", "high", "medium", "low"]
        for p in expected:
            assert MapPriority(p) is not None


class TestTweetData:
    """Ham tweet verisi testleri."""

    def test_valid_tweet(self):
        tweet = TweetData(tweet_id="123", text="Test tweet")
        assert tweet.tweet_id == "123"
        assert tweet.text == "Test tweet"
        assert tweet.author_id is None

    def test_tweet_with_optional_fields(self):
        tweet = TweetData(
            tweet_id="456",
            text="Test",
            author_id="user1",
            created_at="2026-04-25T12:00:00Z",
        )
        assert tweet.author_id == "user1"


class TestAnalyzedTweet:
    """Analiz edilmiş tweet testleri."""

    def test_analyzed_with_result(self):
        analysis = TweetAnalysis(
            city="Hatay", urgency_score=5, confidence=0.9,
        )
        tweet = AnalyzedTweet(
            tweet_id="1", text="test", analysis=analysis,
        )
        assert tweet.analysis is not None
        assert tweet.error is None

    def test_analyzed_with_error(self):
        tweet = AnalyzedTweet(
            tweet_id="2", text="test", error="Rate limit",
        )
        assert tweet.analysis is None
        assert tweet.error == "Rate limit"


class TestAnalyzeRequest:
    """Analiz isteği testleri."""

    def test_valid_request(self):
        req = AnalyzeRequest(text="Deprem oldu yardım edin")
        assert req.text == "Deprem oldu yardım edin"


class TestRateLimitStatus:
    """Rate limit durumu testleri."""

    def test_valid_status(self):
        status = RateLimitStatus(
            requests_this_minute=5,
            requests_today=100,
            max_rpm=15,
            max_rpd=500,
            remaining_rpm=10,
            remaining_rpd=400,
        )
        assert status.remaining_rpm == 10
