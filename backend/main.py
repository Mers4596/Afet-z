"""
Afet Haritası API — FastAPI backend.

Tweet'leri çeker, Gemini ile analiz eder, harita için JSON üretir.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import tempfile
import os
import uvicorn

from app.config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GEMINI_MAX_RPM,
    GEMINI_MAX_RPD,
    TWITTER_BEARER_TOKEN,
    TWITTER_USERNAME,
    TWEET_POLL_INTERVAL_SEC,
    TWEET_CACHE_LIMIT,
    TWEET_MAX_RESULTS,
    MIN_REFRESH_INTERVAL_SEC,
    DATABASE_PATH,
)
from app.models import (
    HealthResponse,
    TweetListResponse,
    AnalyzedTweet,
    AnalyzeRequest,
    RateLimitStatus,
    TrustedAccountRequest,
    CrisisReportRequest,
)
from app.rate_limiter import RateLimiter
from app.gemini_service import GeminiService
from app.tweet_service import TweetService
from app.database import Database
from app.earthquake_service import EarthquakeService
from app.credibility_service import CredibilityService


# ─── Servisler ────────────────────────────────────────────
rate_limiter = RateLimiter(max_rpm=GEMINI_MAX_RPM, max_rpd=GEMINI_MAX_RPD)

gemini_service = GeminiService(
    api_key=GEMINI_API_KEY,
    model_name=GEMINI_MODEL,
    rate_limiter=rate_limiter,
)

tweet_service = TweetService(
    bearer_token=TWITTER_BEARER_TOKEN,
    username=TWITTER_USERNAME,
    poll_interval=TWEET_POLL_INTERVAL_SEC,
    cache_limit=TWEET_CACHE_LIMIT,
    max_results=TWEET_MAX_RESULTS,
    min_refresh_interval=MIN_REFRESH_INTERVAL_SEC,
)

db = Database(db_path=DATABASE_PATH)
earth_service = EarthquakeService(min_magnitude=2.0, cache_ttl=300)
credibility_service = CredibilityService()


# ─── Yardımcı: Trust Score Hesapla ──────────────────────
def _enrich_with_trust(
    analyzed: AnalyzedTweet,
    author_username: str = "",
    city_counts: dict | None = None,
) -> AnalyzedTweet:
    """Analiz edilmiş tweete kullanıcı ve bölge bazlı güven skoru ekle."""
    if city_counts is None:
        city_counts = {}

    is_trusted = db.is_trusted(author_username) if author_username else False

    # Kullanıcı profili varsa skoru hesapla
    user_score = 50.0  # Profil yoksa varsayılan orta skor
    if analyzed.author:
        user_score = credibility_service.compute_user_score(
            analyzed.author, is_trusted=is_trusted
        )
        analyzed.author.credibility_score = user_score
        analyzed.author.is_trusted = is_trusted
    elif is_trusted:
        user_score = 100.0

    # Bölge kümeleme sayısı
    cluster_count = 1
    if analyzed.analysis and analyzed.analysis.city:
        key = f"{analyzed.analysis.city}||{analyzed.analysis.district or ''}"
        cluster_count = city_counts.get(key, 1)

    # AFAD eşleşme durumu
    afad_matched = (
        analyzed.authenticity is not None
        and analyzed.authenticity.is_authentic is True
    )

    analyzed.trust_score = credibility_service.compute_tweet_trust(
        user_score=user_score,
        afad_matched=afad_matched,
        cluster_count=cluster_count,
        is_trusted_author=is_trusted,
    )
    return analyzed


# ─── Lifecycle ────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    db.connect()
    yield
    db.close()


# ─── App ──────────────────────────────────────────────────
app = FastAPI(
    title="Afet Haritası API",
    description="Deprem/afet tweet analiz ve haritalama backend'i",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Endpoints ────────────────────────────────────────────
@app.get("/", response_model=HealthResponse)
def root():
    return {"status": "ok"}


@app.get("/health", response_model=HealthResponse)
def health():
    return {"status": "healthy"}


@app.get("/tweets")
def get_tweets():
    """Hem kullanıcı hem #afetiz hashtag cache'ini döndür."""
    tweets = tweet_service.get_all_cached()
    return {"count": len(tweets), "tweets": [t.model_dump() for t in tweets]}


@app.get("/refresh")
def refresh_tweets():
    """Manuel refresh — spam korumalı (kullanıcı + hashtag)."""
    tweet_service.fetch_tweets(force=True)
    tweet_service.fetch_hashtag_tweets(force=True)
    tweets = tweet_service.get_all_cached()
    return {"count": len(tweets), "tweets": [t.model_dump() for t in tweets]}


@app.get("/earthquakes")
def get_earthquakes(force: bool = False):
    """Son 24 saatteki depremleri AFAD'dan getir."""
    data = earth_service.get_earthquakes(force=force)
    return {"count": len(data), "earthquakes": data}


@app.post("/analyze", response_model=AnalyzedTweet)
def analyze_single_tweet(req: AnalyzeRequest):
    """Tek bir tweeti Gemini ile analiz et."""
    analysis, error = gemini_service.analyze_tweet_safe(req.text)

    authenticity = None
    if req.check_authenticity and analysis:
        auth_dict = earth_service.check_authenticity(
            city=analysis.city,
            district=analysis.district,
        )
        from app.models import AuthenticityResult
        authenticity = AuthenticityResult(**auth_dict)

    result = AnalyzedTweet(
        tweet_id="manual",
        text=req.text,
        analysis=analysis,
        error=error,
        authenticity=authenticity,
    )
    db.save_analysis("manual", req.text, analysis, error)

    city_counts = db.get_city_tweet_counts()
    result = _enrich_with_trust(result, city_counts=city_counts)
    return result


@app.post("/analyze-all")
def analyze_all_cached():
    """Cache'teki tüm tweetleri analiz et (kullanıcı + hashtag cache)."""
    tweets = tweet_service.get_all_cached()
    if not tweets:
        raise HTTPException(status_code=404, detail="Cache'te tweet yok")

    results = []
    for tweet in tweets:
        analysis, error = gemini_service.analyze_tweet_safe(tweet.text)
        analyzed = AnalyzedTweet(
            tweet_id=tweet.tweet_id,
            text=tweet.text,
            analysis=analysis,
            error=error,
        )
        db.save_analysis(tweet.tweet_id, tweet.text, analysis, error)
        results.append(analyzed)

        # Rate limit durumunu kontrol et
        if not rate_limiter.can_request():
            break

    return {"analyzed": len(results), "total": len(tweets), "results": [r.model_dump() for r in results]}


@app.get("/results", response_model=TweetListResponse)
def get_results():
    """Veritabanındaki tüm analiz sonuçlarını getir (trust score dahil)."""
    results = db.get_all_analyses()
    city_counts = db.get_city_tweet_counts()
    enriched = [
        _enrich_with_trust(
            t,
            author_username=t.author.username if t.author else "",
            city_counts=city_counts,
        )
        for t in results
    ]
    return {"count": len(enriched), "tweets": enriched}


@app.get("/results/{priority}")
def get_results_by_priority(priority: str):
    """Öncelik seviyesine göre filtreleme."""
    valid = {"critical", "high", "medium", "low"}
    if priority not in valid:
        raise HTTPException(status_code=400, detail=f"Geçersiz öncelik: {priority}")
    results = db.get_by_priority(priority)
    return {"count": len(results), "priority": priority, "tweets": [r.model_dump() for r in results]}


@app.get("/rate-limit", response_model=RateLimitStatus)
def get_rate_limit():
    """Gemini API rate-limit durumunu göster."""
    return rate_limiter.status()


@app.post("/mock-tweet")
def add_mock_tweet(req: AnalyzeRequest):
    """Demo/test için mock tweet ekle ve analiz et."""
    import uuid
    tweet_id = str(uuid.uuid4())[:8]
    tweet_service.add_mock_tweet(tweet_id, req.text)

    analysis, error = gemini_service.analyze_tweet_safe(req.text)

    authenticity = None
    if req.check_authenticity and analysis:
        auth_dict = earth_service.check_authenticity(
            city=analysis.city,
            district=analysis.district,
        )
        from app.models import AuthenticityResult
        authenticity = AuthenticityResult(**auth_dict)

    analyzed = AnalyzedTweet(
        tweet_id=tweet_id,
        text=req.text,
        analysis=analysis,
        error=error,
        authenticity=authenticity,
    )
    db.save_analysis(tweet_id, req.text, analysis, error)

    city_counts = db.get_city_tweet_counts()
    analyzed = _enrich_with_trust(analyzed, city_counts=city_counts)
    return analyzed


# ─── Hashtag Tweet'leri ──────────────────────────────────
@app.get("/hashtag-tweets")
def get_hashtag_tweets(force: bool = False):
    """#afetiz hashtagiyle paylaşılan tweet'leri Twitter'dan çek."""
    tweets = tweet_service.fetch_hashtag_tweets(force=force)
    return {"count": len(tweets), "tweets": [t.model_dump() for t in tweets]}


# ─── Bölge Risk Skoru ────────────────────────────────────
@app.get("/region-risk")
def get_region_risk():
    """Analiz edilmiş tweet'lere göre bölge bazlı risk skorlarını döndür."""
    results = db.get_all_analyses()
    city_counts = db.get_city_tweet_counts()

    # Her tweet için trust_score hesapla ve bölge verisi topla
    tweet_data_for_risk: list[dict] = []
    for t in results:
        if not t.analysis or not t.analysis.city:
            continue
        author_username = t.author.username if t.author else ""
        is_trusted = db.is_trusted(author_username) if author_username else False

        user_score = 50.0
        if t.author:
            user_score = credibility_service.compute_user_score(t.author, is_trusted=is_trusted)
        elif is_trusted:
            user_score = 100.0

        key = f"{t.analysis.city}||{t.analysis.district or ''}"
        cluster_count = city_counts.get(key, 1)
        afad_matched = (t.authenticity is not None and t.authenticity.is_authentic is True)

        ts = credibility_service.compute_tweet_trust(
            user_score=user_score,
            afad_matched=afad_matched,
            cluster_count=cluster_count,
            is_trusted_author=is_trusted,
        )

        tweet_data_for_risk.append({
            "city": t.analysis.city,
            "district": t.analysis.district or "",
            "trust_score_val": ts.score,
        })

    risks = credibility_service.compute_region_risks(tweet_data_for_risk)
    return {"count": len(risks), "risks": risks}


# ─── Güvenilir Hesaplar ──────────────────────────────────
@app.get("/trusted-accounts")
def get_trusted_accounts():
    """Güvenilir hesap listesini getir."""
    return {"accounts": db.get_trusted_accounts()}


@app.post("/trusted-accounts")
def add_trusted_account(req: TrustedAccountRequest):
    """Güvenilir hesap ekle."""
    if not req.username.strip():
        raise HTTPException(status_code=400, detail="Kullanıcı adı boş olamaz")
    db.add_trusted_account(req.username.strip(), req.note)
    return {"success": True, "username": req.username.lower().strip()}


@app.delete("/trusted-accounts/{username}")
def remove_trusted_account(username: str):
    """Güvenilir hesabı sil."""
    db.remove_trusted_account(username)
    return {"success": True, "username": username}


# ─── PDF Dışa Aktarım — Gemini Kriz Raporu ─────────────
@app.post("/export/pdf-analysis")
def export_pdf_analysis(req: CrisisReportRequest):
    """
    Frontend'den gelen özet istatistikleri Gemini ile analiz et,
    PDF raporuna yerleştirilecek detaylı kriz raporu metnini döndür.
    """
    stats = req.model_dump()
    report = gemini_service.generate_crisis_report(stats)
    return {"report": report}


# ─── PDF Tam Rapor (WeasyPrint) ──────────────────────────
@app.get("/export/full-pdf-report")
def export_full_pdf_report():
    """
    Veritabanındaki tüm analiz sonuçlarını alır, Gemini AI özeti ile
    birleştirerek 5 sayfalık profesyonel PDF kriz raporu üretir.

    Döndürülen dosya: afet_raporu.pdf (application/pdf)
    """
    try:
        from report_generator import rapor_olustur
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Rapor motoru yüklenemedi: {exc}. "
                   "WeasyPrint ve bağımlılıklarının kurulu olduğundan emin olun.",
        )

    # Tüm analiz sonuçlarını al
    results = db.get_all_analyses()
    city_counts = db.get_city_tweet_counts()

    enriched: list[dict] = []
    for t in results:
        te = _enrich_with_trust(
            t,
            author_username=t.author.username if t.author else "",
            city_counts=city_counts,
        )
        enriched.append(te.model_dump())

    if not enriched:
        raise HTTPException(
            status_code=404,
            detail="Rapor oluşturmak için önce tweetleri analiz edin (/analyze-all).",
        )

    # AI raporu oluştur (opsiyonel — hata verirse boş geç)
    ai_text = ""
    try:
        ai_text = gemini_service.generate_crisis_report({"tweets": enriched})
    except Exception:
        pass

    # Baz istasyonu simülasyonu: şehir başına 2-3 baz
    import math
    import time

    def _sim_bt(base: int, seed: str) -> int:
        phase = sum(ord(c) for c in seed)
        cycle = (2 * math.pi * (time.time() % 600)) / 600
        return max(1, round(base * (1 + math.sin(cycle + phase * 0.7) * 0.30)))

    _bt_templates: dict[str, list[str]] = {
        'hatay':         ['Antakya Merkez Rezidans', 'Hatay Devlet Hastanesi', 'Defne Ticaret Merkezi'],
        'kahramanmaras': ['KMaraş Şehir Hastanesi',  'Merkez Konut Bloğu-7',  'Elbistan AVM'],
        'gaziantep':     ['Şahinbey Ticaret Merkezi','Gaziantep Şehir Hastanesi','Nurdağı Sanayi Sitesi'],
        'adiyaman':      ['Adıyaman Çarşı Pasajı',   'Besni Konutları',        'Gölbaşı Mahalle Okulu'],
        'malatya':       ['Yeşilyurt Sitesi',         'Malatya Devlet Hastanesi','Battalgazi Ticaret Hanı'],
        'diyarbakir':    ['Tarihi Sur Konutları',     'Büyükşehir Kampüsü',    'Bağlar İş Hanı'],
        'adana':         ['Seyhan Rezidans',          'Adana Şehir Hastanesi', 'Yüreğir Ticaret Merkezi'],
        'osmaniye':      ['İnönü Apartmanı',          'Osmaniye Devlet Hastanesi','Kadirli Çarşısı'],
        'elazig':        ['Elazığ Çarşısı',           'Fırat Üniv. Yerleşkesi','Sivrice Konutları'],
        'nigde':         ['Niğde Merkez Sitesi',      'Bor Ticaret Hanı',      'Ulukışla İst. Mah.'],
    }
    _default_bt = ['Şehir Merkezi Binası', 'Devlet Hastanesi', 'Ticaret Hanı']

    def _city_key(city: str) -> str:
        tr_map = str.maketrans('şğıöüçŞĞİÖÜÇ', 'sgioucSGIOUC')
        return city.translate(tr_map).lower().replace(' ', '')

    # Şehir başına tweet sayısını bul
    city_count: dict[str, int] = {}
    for t in enriched:
        an = (t.get('analysis') or {})
        city = an.get('city', '') or ''
        if city and city != 'Bilinmiyor':
            city_count[city] = city_count.get(city, 0) + 1

    baz_istasyonlari: list[dict] = []
    for city, cnt in city_count.items():
        key = _city_key(city)
        tpls = _bt_templates.get(key, _default_bt)
        tower_n = 3 if cnt >= 3 else 2
        for t_idx in range(tower_n):
            seed_id = f"{city}_bt_{t_idx}"
            base = 100 + (hash(seed_id) % 400) + cnt * 30
            baz_istasyonlari.append({
                'name': city,
                'building': tpls[t_idx] if t_idx < len(tpls) else tpls[0],
                'base': base,
                'current': _sim_bt(base, seed_id),
            })

    # Geçici PDF dosyası
    tmp = tempfile.NamedTemporaryFile(
        suffix=".pdf", prefix="afetiz_rapor_", delete=False
    )
    tmp.close()

    try:
        rapor_olustur(
            data={"tweets": enriched},
            output_path=tmp.name,
            ai_rapor=ai_text,
            baz_istasyonlari=baz_istasyonlari,
        )
    except Exception as exc:
        os.unlink(tmp.name)
        raise HTTPException(status_code=500, detail=f"PDF üretilemedi: {exc}")

    return FileResponse(
        tmp.name,
        media_type="application/pdf",
        filename="afet_raporu.pdf",
        headers={"Content-Disposition": 'attachment; filename="afet_raporu.pdf"'},
        background=None,
    )


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
