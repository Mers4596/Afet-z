"""
AFAD Deprem Servisi — Son 24 saatteki depremleri çeker, sahtelik analizi yapar.

Not: son-depremler-afad-api kütüphanesinin iç yapısı (app.dosya.depremler) kendi
app paketimizle çakıştığından, kütüphanenin kullandığı AFAD endpoint'ini doğrudan
httpx ile çağırıyoruz. Aynı veri, aynı format.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_AFAD_BASE = "https://deprem.afad.gov.tr/apiv2/event/filter"


def _build_afad_url() -> str:
    """Son 24 saati kapsayan AFAD API URL'si oluştur."""
    end = datetime.now()
    start = end - timedelta(days=1)
    fmt = "%m-%d-%Y %H:%M:%S"
    # AFAD URL'si boşlukları %20 ile bekliyor
    return (
        f"{_AFAD_BASE}"
        f"?start={start.strftime(fmt).replace(' ', '%20')}"
        f"&end={end.strftime(fmt).replace(' ', '%20')}"
        f"&format=json"
    )


def _normalize(text: str) -> str:
    """Türkçe karakterleri ASCII'ye çevir, küçük harfe al."""
    tr_map = str.maketrans("ğüşıöçĞÜŞİÖÇ", "gusiocGUSIOC")
    return text.translate(tr_map).lower().strip()


class EarthquakeService:
    """AFAD'dan son 24 saatteki depremleri çeker ve sahtelik analizi yapar."""

    def __init__(self, min_magnitude: float = 2.0, cache_ttl: int = 300):
        self.min_magnitude = min_magnitude
        self.cache_ttl = cache_ttl          # saniye — 5 dk cache
        self._cache: list[dict] = []
        self._cache_time: float = 0.0

    def get_earthquakes(self, force: bool = False) -> list[dict]:
        """
        Son 24 saatteki depremleri döndür.
        Cache TTL dolmadıkça AFAD'a tekrar istek atmaz.
        """
        now = time.time()
        if not force and self._cache and now - self._cache_time < self.cache_ttl:
            return self._cache

        try:
            url = _build_afad_url()
            with httpx.Client(timeout=10.0, follow_redirects=True) as client:
                resp = client.get(url)
                resp.raise_for_status()
                raw: list[dict] = resp.json()

            self._cache = [
                {
                    "datetime": e.get("date", "").replace("T", " "),
                    "location": e.get("location", ""),
                    "province": e.get("province", ""),
                    "district": e.get("district", ""),
                    "magnitude": float(e.get("magnitude", 0)),
                    "lat": float(e.get("latitude", 0)),
                    "lon": float(e.get("longitude", 0)),
                    "depth": float(e.get("depth", 0)),
                }
                for e in raw
                if float(e.get("magnitude", 0)) >= self.min_magnitude
            ]
            self._cache_time = now
            logger.info("AFAD: %d deprem yüklendi (min M%.1f)", len(self._cache), self.min_magnitude)

        except Exception as e:
            logger.error("AFAD API hatası: %s", e)
            # Cache varsa eski veriyi kullan, yoksa boş döndür

        return self._cache

    def check_authenticity(self, city: str, district: str = "") -> dict:
        """
        Tweet'teki şehir/ilçe için son 24 saatte deprem var mı kontrol et.

        Returns:
            dict ile şu alanlar:
              - is_authentic: bool | None  (None = doğrulanamadı)
              - matched_earthquake: dict | None
              - explanation: str
              - checked_at: str (ISO)
        """
        earthquakes = self.get_earthquakes()
        checked_at = datetime.now().isoformat()

        if not earthquakes:
            return {
                "is_authentic": None,
                "matched_earthquake": None,
                "explanation": "AFAD verisi alınamadı, doğrulama yapılamadı.",
                "checked_at": checked_at,
            }

        city_norm = _normalize(city) if city and city != "Bilinmiyor" else ""
        district_norm = _normalize(district) if district else ""

        best_match: Optional[dict] = None
        best_magnitude = 0.0

        for eq in earthquakes:
            loc_norm = _normalize(eq["location"])
            province_norm = _normalize(eq.get("province") or "")
            eq_district_norm = _normalize(eq.get("district") or "")

            matched = (
                (city_norm and (city_norm in loc_norm or city_norm in province_norm))
                or (district_norm and (district_norm in loc_norm or district_norm in eq_district_norm))
            )
            if matched and eq["magnitude"] > best_magnitude:
                best_magnitude = eq["magnitude"]
                best_match = eq

        if best_match:
            return {
                "is_authentic": True,
                "matched_earthquake": best_match,
                "explanation": (
                    f"Bölgede son 24 saatte M{best_match['magnitude']:.1f} büyüklüğünde deprem "
                    f"tespit edildi: {best_match['location']} ({best_match['datetime']}). "
                    f"Tweet büyük ihtimalle gerçektir."
                ),
                "checked_at": checked_at,
            }
        else:
            region = city if city_norm else "belirtilen bölge"
            return {
                "is_authentic": False,
                "matched_earthquake": None,
                "explanation": (
                    f"{region} için son 24 saatte kayıtlı deprem bulunamadı. "
                    f"Tweet şüpheli olabilir veya AFAD verisi henüz güncellenmemiş olabilir."
                ),
                "checked_at": checked_at,
            }
