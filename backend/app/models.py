"""
Pydantic modelleri — API request/response ve iç veri yapıları.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, List
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
    street_address: str = Field("", description="Sokak/bina adresi (ör: Gül Sokak No:12)")
    has_precise_location: bool = Field(False, description="Sokak/bina seviyesinde kesin konum var mı")
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
    author_username: Optional[str] = None
    created_at: Optional[str] = None
    user_profile: Optional["UserProfile"] = None


# ─── Kullanıcı Profili ────────────────────────────────────
class UserProfile(BaseModel):
    """Twitter kullanıcı profili ve hesap güvenilirlik skoru."""
    author_id: str = ""
    username: str = ""
    account_age_days: int = 0
    followers: int = 0
    following: int = 0
    tweet_count: int = 0
    credibility_score: float = 0.0  # 0-100
    is_trusted: bool = False


# ─── Tweet Güven Skoru ────────────────────────────────────
class TrustScore(BaseModel):
    """Tweet bazlı güvenilirlik skoru (kullanıcı + AFAD + kümeleme)."""
    score: float = 0.0          # 0-100 toplam güvenilirlik %
    user_score: float = 0.0     # kullanıcı profil skoru
    afad_boost: float = 0.0     # AFAD eşleşme bonusu
    cluster_boost: float = 0.0  # aynı bölge tweet birikimi bonusu
    explanation: str = ""


# ─── Bölge Risk Skoru ─────────────────────────────────────
class RegionRisk(BaseModel):
    """Bir bölgede biriken tweet'lerden hesaplanan risk skoru."""
    city: str
    district: str = ""
    risk_score: float = 0.0     # 0-100
    tweet_count: int = 0
    avg_trust: float = 0.0
    explanation: str = ""


# ─── Güvenilir Hesaplar ───────────────────────────────────
class TrustedAccount(BaseModel):
    """Manuel olarak güvenilir işaretlenen Twitter hesabı."""
    username: str
    added_at: str = ""
    note: str = ""


class TrustedAccountRequest(BaseModel):
    """Güvenilir hesap ekleme/çıkarma isteği."""
    username: str
    note: str = ""


# ─── Analiz Edilmiş Tweet ─────────────────────────────────
class AnalyzedTweet(BaseModel):
    """Tweet + AI analiz sonucu."""
    tweet_id: str
    text: str
    analysis: Optional[TweetAnalysis] = None
    analyzed_at: Optional[str] = None
    error: Optional[str] = None
    authenticity: Optional["AuthenticityResult"] = None
    author: Optional[UserProfile] = None
    trust_score: Optional[TrustScore] = None


# ─── API Response'ları ────────────────────────────────────
class HealthResponse(BaseModel):
    status: str


class TweetListResponse(BaseModel):
    count: int
    tweets: list[AnalyzedTweet]


class AuthenticityResult(BaseModel):
    """AFAD deprem verisiyle sahtelik analizi sonucu."""
    is_authentic: Optional[bool] = None
    matched_earthquake: Optional[dict] = None
    explanation: str = ""
    checked_at: Optional[str] = None


class AnalyzeRequest(BaseModel):
    """Tek bir tweeti analiz ettirmek için."""
    text: str
    check_authenticity: bool = False


class RateLimitStatus(BaseModel):
    """Rate limit durumu."""
    requests_this_minute: int
    requests_today: int
    max_rpm: int
    max_rpd: int
    remaining_rpm: int
    remaining_rpd: int


# ─── PDF/Excel Dışa Aktarım ──────────────────────────────
class CityBreakdown(BaseModel):
    city: str
    count: int
    max_urgency: int = 0
    top_needs: list[str] = []


class TrustStats(BaseModel):
    avg: float = 0.0
    total_trusted_sources: int = 0


class CriticalTweetSummary(BaseModel):
    text: str = ""
    city: str = ""
    district: str = ""
    neighborhood: str = ""
    street_address: str = ""
    has_precise_location: bool = False
    need_types: list[str] = []
    urgency_score: int = 0
    summary: str = ""
    map_priority: str = "medium"


class CrisisReportRequest(BaseModel):
    """Frontend'den gelen özet istatistikler — Gemini raporu için."""
    total_analyzed: int
    critical_count: int
    high_count: int
    medium_count: int = 0
    low_count: int = 0
    affected_cities: int
    analysis_date: str = ""
    city_breakdown: list[CityBreakdown] = []
    need_frequencies: dict[str, int] = {}
    top_critical_tweets: list[CriticalTweetSummary] = []
    trust_stats: TrustStats = TrustStats()
