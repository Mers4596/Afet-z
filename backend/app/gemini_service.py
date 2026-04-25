"""
Gemini AI servisi — Tweet'leri yapılandırılmış JSON'a dönüştürür.

Few-Shot prompting ile Gemini'yi bir "veri dönüştürme motoru" olarak kullanır.
Rate-limit koruması uygulanır.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from app.models import TweetAnalysis
from app.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

# ─── Sistem Prompt'u ──────────────────────────────────────
SYSTEM_PROMPT = """Sen bir afet veri ayrıştırma botusun. 
Sana verilen deprem/afet tweetlerinden yapılandırılmış JSON verisi çıkaracaksın.

KURALLAR:
1. Sadece JSON döndür, başka hiçbir açıklama veya metin yazma.
2. JSON şu formatta olmalı:
{
  "city": "İl adı",
  "district": "İlçe adı",
  "neighborhood": "Mahalle adı",
  "street_address": "Sokak ve bina bilgisi (varsa, ör: Gül Sokak No:12 Daire:3)",
  "has_precise_location": true/false,
  "need_types": ["arama_kurtarma", "saglik", "su", "gida", "barinma", "yol_kapali", "yangin", "elektrik_iletisim"],
  "urgency_score": 1-5 arası tam sayı (5 en acil),
  "confidence": 0.0-1.0 arası güven skoru,
  "summary": "Kısa özet",
  "map_priority": "critical/high/medium/low"
}

3. need_types sadece şu değerlerden olabilir: arama_kurtarma, saglik, su, gida, barinma, yol_kapali, yangin, elektrik_iletisim
4. Eğer lokasyon bilgisi yoksa, city alanına "Bilinmiyor" yaz.
5. urgency_score: 5=Çok acil (enkaz altı, ölüm tehlikesi), 4=Acil, 3=Orta, 2=Düşük, 1=Bilgi amaçlı
6. map_priority: urgency_score 5→critical, 4→high, 3→medium, 1-2→low
7. has_precise_location: Tweet'te sokak adı, bina numarası, daire numarası, kapı no gibi kesin adres varsa true; sadece şehir/ilçe/mahalle bilgisi varsa false.
8. street_address: Sokak/cadde adı ve numara varsa doldur, yoksa boş bırak.

ÖRNEK:
Tweet: "Antakya Cumhuriyet Mahallesi Gül Sokak No:12, enkaz altındayız yardım edin, kanama var"
Çıktı:
{"city": "Hatay", "district": "Antakya", "neighborhood": "Cumhuriyet Mahallesi", "street_address": "Gül Sokak No:12", "has_precise_location": true, "need_types": ["arama_kurtarma", "saglik"], "urgency_score": 5, "confidence": 0.92, "summary": "Enkaz altında yaralı kişiler, kanama var", "map_priority": "critical"}

Tweet: "Kahramanmaraş merkez su yok 2 gündür"
Çıktı:
{"city": "Kahramanmaraş", "district": "Merkez", "neighborhood": "", "street_address": "", "has_precise_location": false, "need_types": ["su"], "urgency_score": 3, "confidence": 0.85, "summary": "2 gündür su kesintisi", "map_priority": "medium"}
"""


class GeminiService:
    """Gemini API ile tweet analiz servisi."""

    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-3.1-flash-lite",
        rate_limiter: Optional[RateLimiter] = None,
    ):
        self.api_key = api_key
        self.model_name = model_name
        self.rate_limiter = rate_limiter or RateLimiter()
        self._client = None

    def _get_client(self):
        """Lazy-init Gemini client."""
        if self._client is None:
            import google.generativeai as genai

            genai.configure(api_key=self.api_key)
            self._client = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=SYSTEM_PROMPT,
                generation_config={
                    "temperature": 0.1,
                    "top_p": 0.95,
                    "response_mime_type": "application/json",
                },
            )
        return self._client

    def analyze_tweet(self, tweet_text: str) -> TweetAnalysis:
        """
        Tweet metnini analiz edip TweetAnalysis döndürür.

        Raises:
            RuntimeError: Rate limit aşıldığında
            ValueError: Gemini'den geçersiz JSON geldiğinde
        """
        # ── Rate-limit kontrolü ──
        if not self.rate_limiter.acquire():
            status = self.rate_limiter.status()
            raise RuntimeError(
                f"Gemini rate limit aşıldı. "
                f"RPM: {status['requests_this_minute']}/{status['max_rpm']}, "
                f"RPD: {status['requests_today']}/{status['max_rpd']}"
            )

        try:
            client = self._get_client()
            response = client.generate_content(
                f"Tweet: \"{tweet_text}\"\nÇıktı:"
            )

            raw_text = response.text.strip()
            data = json.loads(raw_text)
            return TweetAnalysis(**data)

        except json.JSONDecodeError as e:
            logger.error("Gemini'den geçersiz JSON: %s", e)
            raise ValueError(f"Gemini geçersiz JSON döndürdü: {e}") from e
        except Exception as e:
            logger.error("Gemini API hatası: %s", e)
            raise

    def analyze_tweet_safe(self, tweet_text: str) -> tuple[Optional[TweetAnalysis], Optional[str]]:
        """
        Tweet analizi yapar, hata durumunda (None, error_msg) döndürür.
        Başarılıysa (analysis, None) döndürür.
        """
        try:
            result = self.analyze_tweet(tweet_text)
            return result, None
        except Exception as e:
            return None, str(e)

    def get_rate_limit_status(self) -> dict:
        """Rate-limit durumunu döndür."""
        return self.rate_limiter.status()

    def generate_crisis_report(self, stats: dict) -> str:
        """
        Yapılandırılmış istatistik verisinden kapsamlı kriz raporu üretir.
        PDF dışa aktarımı için kullanılır.
        """
        import google.generativeai as genai

        genai.configure(api_key=self.api_key)
        report_model = genai.GenerativeModel(
            model_name=self.model_name,
            generation_config={
                "temperature": 0.4,
                "top_p": 0.95,
                "max_output_tokens": 3000,
            },
        )

        # Veriyi metin formatına çevir
        city_lines = "\n".join(
            f"  - {c['city']}: {c['count']} tweet, maks aciliyet {c['max_urgency']}/5, "
            f"ihtiyaclar: {', '.join(c.get('top_needs', []))}"
            for c in stats.get("city_breakdown", [])[:10]
        )
        need_lines = "\n".join(
            f"  - {k}: {v} tweet"
            for k, v in sorted(stats.get("need_frequencies", {}).items(), key=lambda x: -x[1])
        )
        critical_lines = "\n".join(
            f"  [{t.get('map_priority','?').upper()}] {t.get('city','')} "
            f"{t.get('district','')}{' / ' + t.get('street_address','') if t.get('street_address') else ''} "
            f"— Aciliyet {t.get('urgency_score',0)}/5: {t.get('summary', t.get('text',''))[:100]}"
            for t in stats.get("top_critical_tweets", [])[:10]
        )

        prompt = f"""Sen bir afet koordinasyon ve kriz yönetim uzmanısın.
Aşağıda verilen sosyal medya tweet analiz verilerini inceleyerek kapsamlı bir kriz değerlendirmesi raporu hazırla.

ÖZET VERİLER:
- Analiz Tarihi: {stats.get('analysis_date', 'Bilinmiyor')}
- Toplam Analiz Edilen Tweet: {stats.get('total_analyzed', 0)}
- Kritik Alarm: {stats.get('critical_count', 0)}
- Yüksek Öncelikli: {stats.get('high_count', 0)}
- Orta Öncelikli: {stats.get('medium_count', 0)}
- Etkilenen İl Sayısı: {stats.get('affected_cities', 0)}
- Ortalama Güven Skoru: %{stats.get('trust_stats', {}).get('avg', 0)}

İL BAZLI DAĞILIM:
{city_lines or '  Veri yok'}

İHTİYAÇ DAĞILIMI:
{need_lines or '  Veri yok'}

EN KRİTİK NOKTALAR:
{critical_lines or '  Kritik kayit bulunamadi'}

Aşağıdaki bölümleri içeren kapsamlı bir rapor yaz.
Her bölümü ## ile başlat, profesyonel ve somut bir dil kullan:

## YÖNETİCİ ÖZETİ
Tüm durumun 3-4 paragrafta değerlendirmesi: kaç bölge etkilendi, en acil ihtiyaçlar, genel risk seviyesi.

## BÖLGESEL RİSK ANALİZİ
Her etkilenen il için tweet yoğunluğu ve aciliyet skorlarına göre ayrı değerlendirme ve öncelik sıralaması.

## İHTİYAÇ HARİTALAMASI
Her ihtiyaç türü için detaylı değerlendirme. Hangileri kritik seviyede? Kaynak tahsisi önerileri.

## DOĞRULAMA VE GÜVENİLİRLİK
Verinin güvenilirliği, doğrulanan bilgiler vs şüpheli içerikler, güven skoru analizi.

## ACİL MÜDAHALE ÖNERİLERİ
Öncelik sırasına göre en az 7 somut, uygulanabilir öneri. Her öneri için sorumlu kurum ve tahmini süre.

## KRİTİK RİSK FAKTÖRLERİ VE UYARILAR
Durumu daha da kötüleştirebilecek faktörler, gözden kaçmaması gereken riskler.

Rapor Türkçe, profesyonel ve aksiyon odaklı olsun. Gereksiz tekrar yapma."""

        try:
            response = report_model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            logger.error("Kriz raporu üretme hatası: %s", e)
            return f"Rapor üretilemedi: {e}"
