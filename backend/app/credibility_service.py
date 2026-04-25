"""
Güvenilirlik Servisi — Kullanıcı profili, tweet güven skoru ve bölge risk analizi.

Puanlama mantığı:
  Kullanıcı Skoru (0-100):
    • Hesap yaşı   → 0-40 puan  (730+ gün = tam puan)
    • Takipçi sayısı → 0-30 puan (log ölçek, 10k = tam puan)
    • Takip/Takipçi oranı → 0-20 puan
    • Tweet aktivitesi → 0-10 puan

  Tweet Güven Skoru (0-100):
    • Kullanıcı skoru × 0.40
    • AFAD eşleşmesi → +30 puan sabit bonus
    • Aynı bölge kümeleme → +5/tweet, max +30

  Bölge Risk Skoru (0-100):
    • Ortalama tweet güven skoru × 0.80
    • Tweet sayısı bonusu → +4/tweet, max +20
"""

from __future__ import annotations

import math
from typing import Optional

from app.models import TrustScore, UserProfile


class CredibilityService:
    """Kullanıcı + tweet + bölge güvenilirlik hesaplama motoru."""

    # ── Kullanıcı Skoru ──────────────────────────────────
    def compute_user_score(
        self,
        profile: UserProfile,
        is_trusted: bool = False,
    ) -> float:
        """0-100 arasında kullanıcı güvenilirlik skoru döndür."""
        if is_trusted:
            return 100.0

        # Hesap yaşı (0-40 puan): 730 gün (2 yıl) veya üstü = tam puan
        age_score = min(40.0, profile.account_age_days / 730.0 * 40.0)

        # Takipçi sayısı (0-30 puan): log ölçek, 10k = tam puan
        followers_score = min(
            30.0,
            math.log10(profile.followers + 1) / math.log10(10001) * 30.0,
        )

        # Takip/Takipçi oranı (0-20 puan)
        if profile.following > 0:
            ratio = profile.followers / profile.following
            # oran 2.0+ = tam puan, 0 = sıfır
            ratio_score = min(20.0, ratio / 2.0 * 20.0)
        else:
            # Takip etmiyorsa belirsiz → orta puan
            ratio_score = 10.0

        # Tweet aktivitesi (0-10 puan): 5000+ tweet = tam puan
        tweet_score = min(
            10.0,
            math.log10(profile.tweet_count + 1) / math.log10(5001) * 10.0,
        )

        return round(age_score + followers_score + ratio_score + tweet_score, 1)

    # ── Tweet Güven Skoru ────────────────────────────────
    def compute_tweet_trust(
        self,
        user_score: float,
        afad_matched: bool,
        cluster_count: int,
        is_trusted_author: bool = False,
    ) -> TrustScore:
        """
        Tweet bazlı güvenilirlik skoru döndür.

        Args:
            user_score: Kullanıcının profil skoru (0-100)
            afad_matched: AFAD deprem verisiyle eşleşip eşleşmediği
            cluster_count: Aynı şehir/ilçede biriken toplam tweet sayısı
            is_trusted_author: Güvenilir hesap listesinde mi?
        """
        if is_trusted_author:
            return TrustScore(
                score=95.0,
                user_score=100.0,
                afad_boost=0.0,
                cluster_boost=0.0,
                explanation="Güvenilir hesap listesinde → Direkt güvenilir",
            )

        user_component = user_score * 0.40
        afad_component = 30.0 if afad_matched else 0.0
        cluster_boost = min(30.0, max(0.0, (cluster_count - 1) * 5.0))

        score = round(min(100.0, user_component + afad_component + cluster_boost), 1)

        parts: list[str] = []
        if afad_matched:
            parts.append("AFAD verisiyle eşleşti (+30)")
        if cluster_count > 1:
            parts.append(f"Bölgede {cluster_count} tweet birikimi (+{int(cluster_boost)})")
        if user_score >= 70:
            parts.append("Güvenilir hesap profili")
        elif user_score >= 40:
            parts.append("Orta güvenilirlik hesap")
        else:
            parts.append("Yeni/düşük aktiviteli hesap")

        explanation = " | ".join(parts) if parts else "Veri yetersiz"

        return TrustScore(
            score=score,
            user_score=round(user_score, 1),
            afad_boost=afad_component,
            cluster_boost=round(cluster_boost, 1),
            explanation=explanation,
        )

    # ── Bölge Risk Skoru ─────────────────────────────────
    def compute_region_risks(
        self,
        analyzed_tweets: list[dict],
    ) -> list[dict]:
        """
        Tüm analiz edilmiş tweet'lerden bölge bazlı risk skoru hesapla.

        Her tweet dict şu anahtarları içermeli:
          city, district, trust_score (float 0-100)
        """
        # Şehir/ilçe bazlı gruplandır
        groups: dict[str, list[float]] = {}
        for t in analyzed_tweets:
            city = t.get("city", "Bilinmiyor")
            district = t.get("district", "")
            key = f"{city}||{district}"
            trust = t.get("trust_score_val", 50.0)
            groups.setdefault(key, []).append(trust)

        risks = []
        for key, trust_list in groups.items():
            city, district = key.split("||", 1)
            count = len(trust_list)
            avg_trust = sum(trust_list) / count
            count_bonus = min(20.0, count * 4.0)
            risk_score = round(min(100.0, avg_trust * 0.80 + count_bonus), 1)

            risks.append({
                "city": city,
                "district": district,
                "risk_score": risk_score,
                "tweet_count": count,
                "avg_trust": round(avg_trust, 1),
                "explanation": (
                    f"{count} tweet | Ort. güvenilirlik %{round(avg_trust, 1)}"
                    f" | Risk skoru %{risk_score}"
                ),
            })

        # Risk skoru yüksekten düşüğe sırala
        risks.sort(key=lambda x: x["risk_score"], reverse=True)
        return risks
