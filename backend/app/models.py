"""
Pydantic modelleri — API request/response ve iç veri yapıları.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


# ─── İhtiyaç Türleri ──────────────────────────────────────
class NeedType(str, Enum):
    ARAMA_KURTARMA = "arama_kurtarma"
    SAGLIK = "saglik"
    SU = "su"
    GIDA = "gida"
    BARINMA = "barinma"
    YOL_KAPALI = "yol_kapali"
    YANGIN = "yangin"
    ELEKTRIK_ILETISIM = "elektrik_iletisim"


# ─── Harita Önceliği ──────────────────────────────────────
class MapPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ─── Gemini'den Dönen Analiz Sonucu ──────────────────────
class TweetAnalysis(BaseModel):
    """Gemini'nin tweet'ten çıkardığı yapılandırılmış veri."""
    city: str = Field(..., description="İl (ör: Hatay)")
    district: str = Field("", description="İlçe (ör: Antakya)")
    neighborhood: str = Field("", description="Mahalle")
    need_types: list[str] = Field(default_factory=list, description="İhtiyaç türleri")
    urgency_score: int = Field(..., ge=1, le=5, description="Aciliyet puanı 1-5")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Güven skoru")
    summary: str = Field("", description="Kısa özet")
    map_priority: str = Field("medium", description="critical/high/medium/low")


# ─── Tweet Verisi ─────────────────────────────────────────
class TweetData(BaseModel):
    """Ham tweet verisi."""
    tweet_id: str
    text: str
    author_id: Optional[str] = None
    created_at: Optional[str] = None


# ─── Analiz Edilmiş Tweet ─────────────────────────────────
class AnalyzedTweet(BaseModel):
    """Tweet + AI analiz sonucu."""
    tweet_id: str
    text: str
    analysis: Optional[TweetAnalysis] = None
    analyzed_at: Optional[str] = None
    error: Optional[str] = None


# ─── API Response'ları ────────────────────────────────────
class HealthResponse(BaseModel):
    status: str


class TweetListResponse(BaseModel):
    count: int
    tweets: list[AnalyzedTweet]


class AnalyzeRequest(BaseModel):
    """Tek bir tweeti analiz ettirmek için."""
    text: str


class RateLimitStatus(BaseModel):
    """Rate limit durumu."""
    requests_this_minute: int
    requests_today: int
    max_rpm: int
    max_rpd: int
    remaining_rpm: int
    remaining_rpd: int
