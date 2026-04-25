"""
Uygulama konfigürasyonu — environment variables ve sabitler.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─── API Anahtarları ──────────────────────────────────────
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
TWITTER_BEARER_TOKEN: str = os.getenv("TWITTER_KEY", "")

# ─── Twitter Ayarları ─────────────────────────────────────
TWITTER_USERNAME: str = os.getenv("TWITTER_USERNAME", "meh56954")
TWEET_POLL_INTERVAL_SEC: int = int(os.getenv("TWEET_POLL_INTERVAL_SEC", "30"))
TWEET_CACHE_LIMIT: int = int(os.getenv("TWEET_CACHE_LIMIT", "50"))
TWEET_MAX_RESULTS: int = int(os.getenv("TWEET_MAX_RESULTS", "5"))

# ─── Gemini Rate-Limit Koruması ────────────────────────────
# Gemini 3.1 Flash Lite: 15 RPM, 250K TPM, 500 RPD
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
GEMINI_MAX_RPM: int = int(os.getenv("GEMINI_MAX_RPM", "15"))
GEMINI_MAX_RPD: int = int(os.getenv("GEMINI_MAX_RPD", "500"))
GEMINI_MAX_TPM: int = int(os.getenv("GEMINI_MAX_TPM", "250000"))

# ─── Spam Refresh Koruması ─────────────────────────────────
MIN_REFRESH_INTERVAL_SEC: int = int(os.getenv("MIN_REFRESH_INTERVAL_SEC", "5"))

# ─── Veritabanı ───────────────────────────────────────────
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "afet_haritasi.db")
