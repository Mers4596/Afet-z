"""
Afet Haritası API — FastAPI backend.

Tweet'leri çeker, Gemini ile analiz eder, harita için JSON üretir.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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
)
from app.rate_limiter import RateLimiter
from app.gemini_service import GeminiService
from app.tweet_service import TweetService
from app.database import Database
from app.earthquake_service import EarthquakeService


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
    """Tweet cache'ini döndür (polling ile güncellenir)."""
    tweets = tweet_service.fetch_tweets()
    return {"count": len(tweets), "tweets": [t.model_dump() for t in tweets]}


@app.get("/refresh")
def refresh_tweets():
    """Manuel refresh — spam korumalı."""
    tweets = tweet_service.fetch_tweets(force=True)
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
    return result


@app.post("/analyze-all")
def analyze_all_cached():
    """Cache'teki tüm tweetleri analiz et."""
    tweets = tweet_service.get_cache()
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
    """Veritabanındaki tüm analiz sonuçlarını getir."""
    results = db.get_all_analyses()
    return {"count": len(results), "tweets": results}


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
    return analyzed


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
