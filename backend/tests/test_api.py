"""
FastAPI endpoint testleri (TestClient ile).
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    """Test client — geçici DB ile."""
    import os
    os.environ["DATABASE_PATH"] = str(tmp_path / "test.db")

    # Config'i yeniden yükle
    import importlib
    import app.config
    importlib.reload(app.config)

    from main import app, db
    db.db_path = str(tmp_path / "test.db")
    db.connect()

    with TestClient(app) as c:
        yield c

    db.close()


class TestHealthEndpoints:
    """Sağlık kontrol endpoint'leri."""

    def test_root(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"


class TestRateLimitEndpoint:
    """Rate limit endpoint testi."""

    def test_rate_limit_status(self, client):
        resp = client.get("/rate-limit")
        assert resp.status_code == 200
        data = resp.json()
        assert "max_rpm" in data
        assert "max_rpd" in data
        assert data["max_rpm"] == 15
        assert data["max_rpd"] == 500


class TestAnalyzeEndpoint:
    """Tweet analiz endpoint'i testleri."""

    def test_analyze_returns_result(self, client):
        """Analiz endpoint'i sonuç döndürmeli."""
        # Gemini'yi mock'la
        with patch("main.gemini_service") as mock_svc:
            from app.models import TweetAnalysis
            mock_analysis = TweetAnalysis(
                city="Hatay", district="Antakya",
                neighborhood="Cumhuriyet",
                need_types=["arama_kurtarma"],
                urgency_score=5, confidence=0.9,
                summary="Test", map_priority="critical",
            )
            mock_svc.analyze_tweet_safe.return_value = (mock_analysis, None)

            resp = client.post("/analyze", json={"text": "Enkaz altındayız"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["tweet_id"] == "manual"
            assert data["analysis"]["city"] == "Hatay"

    def test_analyze_empty_text(self, client):
        """Boş metin gönderildiğinde hata."""
        resp = client.post("/analyze", json={})
        assert resp.status_code == 422


class TestResultsEndpoint:
    """Sonuç endpoint'i testleri."""

    def test_results_empty(self, client):
        resp = client.get("/results")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_results_priority_invalid(self, client):
        resp = client.get("/results/invalid_priority")
        assert resp.status_code == 400
