"""
Gemini servis testleri (mock'lanmış).

Test edilen gereksinimler:
- Few-shot prompting ile JSON çıktısı
- Rate-limit entegrasyonu
- Hata yönetimi
"""

import json
from unittest.mock import MagicMock, patch
import pytest

from app.gemini_service import GeminiService, SYSTEM_PROMPT
from app.rate_limiter import RateLimiter
from app.models import TweetAnalysis


class TestGeminiServiceInit:
    """Servis başlatma testleri."""

    def test_init_with_defaults(self):
        svc = GeminiService(api_key="test-key")
        assert svc.api_key == "test-key"
        assert svc.model_name == "gemini-3.1-flash-lite"
        assert svc.rate_limiter is not None

    def test_init_with_custom_rate_limiter(self):
        rl = RateLimiter(max_rpm=5, max_rpd=100)
        svc = GeminiService(api_key="k", rate_limiter=rl)
        assert svc.rate_limiter is rl


class TestSystemPrompt:
    """Sistem prompt'u gereksinimleri."""

    def test_prompt_requires_json_only(self):
        assert "JSON" in SYSTEM_PROMPT
        assert "başka hiçbir" in SYSTEM_PROMPT

    def test_prompt_has_need_types(self):
        """Dokümandaki tüm ihtiyaç türleri prompt'ta olmalı."""
        expected = [
            "arama_kurtarma", "saglik", "su", "gida",
            "barinma", "yol_kapali", "yangin", "elektrik_iletisim",
        ]
        for need in expected:
            assert need in SYSTEM_PROMPT, f"{need} prompt'ta eksik"

    def test_prompt_has_urgency_scale(self):
        assert "1-5" in SYSTEM_PROMPT

    def test_prompt_has_map_priority(self):
        assert "critical" in SYSTEM_PROMPT
        assert "high" in SYSTEM_PROMPT
        assert "medium" in SYSTEM_PROMPT
        assert "low" in SYSTEM_PROMPT

    def test_prompt_has_few_shot_examples(self):
        """Few-shot örnekleri olmalı."""
        assert "Antakya" in SYSTEM_PROMPT
        assert "Cumhuriyet Mahallesi" in SYSTEM_PROMPT


class TestGeminiAnalyze:
    """Analiz fonksiyonu testleri (mock'lanmış Gemini)."""

    def _make_service(self, max_rpm=15, max_rpd=500):
        rl = RateLimiter(max_rpm=max_rpm, max_rpd=max_rpd)
        return GeminiService(api_key="test", rate_limiter=rl)

    def _mock_gemini_response(self, data: dict):
        """Gemini API yanıtını mock'la."""
        mock_response = MagicMock()
        mock_response.text = json.dumps(data)
        return mock_response

    def test_analyze_rate_limit_blocks(self):
        """Rate limit doluyken analiz engellenmeli."""
        svc = self._make_service(max_rpm=1, max_rpd=500)
        svc.rate_limiter.acquire()  # 1 slot doldur

        with pytest.raises(RuntimeError, match="rate limit"):
            svc.analyze_tweet("test tweet")

    def test_analyze_safe_returns_error_on_limit(self):
        """Safe analiz rate limit hatası döndürmeli."""
        svc = self._make_service(max_rpm=1, max_rpd=500)
        svc.rate_limiter.acquire()

        result, error = svc.analyze_tweet_safe("test")
        assert result is None
        assert error is not None
        assert "rate limit" in error.lower()

    @patch("app.gemini_service.genai", create=True)
    def test_analyze_success(self, mock_genai):
        """Başarılı analiz TweetAnalysis döndürmeli."""
        svc = self._make_service()

        valid_response = {
            "city": "Hatay",
            "district": "Antakya",
            "neighborhood": "Cumhuriyet",
            "need_types": ["arama_kurtarma"],
            "urgency_score": 5,
            "confidence": 0.9,
            "summary": "Test",
            "map_priority": "critical",
        }

        mock_model = MagicMock()
        mock_model.generate_content.return_value = self._mock_gemini_response(valid_response)

        # Lazy init'i bypass et
        svc._client = mock_model

        result = svc.analyze_tweet("Test tweet")
        assert isinstance(result, TweetAnalysis)
        assert result.city == "Hatay"
        assert result.urgency_score == 5

    @patch("app.gemini_service.genai", create=True)
    def test_analyze_invalid_json_raises(self, mock_genai):
        """Geçersiz JSON ValueError fırlatmalı."""
        svc = self._make_service()

        mock_model = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = "Bu JSON değil, düz metin"
        mock_model.generate_content.return_value = mock_resp

        svc._client = mock_model

        with pytest.raises(ValueError, match="geçersiz JSON"):
            svc.analyze_tweet("test")

    @patch("app.gemini_service.genai", create=True)
    def test_analyze_safe_success(self, mock_genai):
        """Safe analiz başarılı sonuç döndürmeli."""
        svc = self._make_service()

        valid_data = {
            "city": "Kahramanmaraş",
            "district": "Merkez",
            "neighborhood": "",
            "need_types": ["su"],
            "urgency_score": 3,
            "confidence": 0.85,
            "summary": "Su kesintisi",
            "map_priority": "medium",
        }

        mock_model = MagicMock()
        mock_model.generate_content.return_value = self._mock_gemini_response(valid_data)
        svc._client = mock_model

        result, error = svc.analyze_tweet_safe("test")
        assert result is not None
        assert error is None
        assert result.city == "Kahramanmaraş"

    def test_rate_limit_status(self):
        """Rate limit durumu doğru raporlanmalı."""
        svc = self._make_service()
        status = svc.get_rate_limit_status()
        assert status["max_rpm"] == 15
        assert status["max_rpd"] == 500
