# AfetİZ — Kriz İzleme Paneli

> HackNiğde 2026 Hackathonu projesi.  
> Afet tweet'lerini **Gemini AI** ile gerçek zamanlı analiz eden, harita üzerinde kriz noktalarını gösteren izleme sistemi.

---

## Mimari

```
Twitter / Mock Tweet
        │
        ▼
  FastAPI Backend  ──►  Gemini 3.1 Flash Lite (Few-Shot JSON)
        │
        ▼
    SQLite DB
        │
        ▼
  Next.js / Vite Frontend  ──►  Leaflet Harita + D3 Grafikler
```

---

## Özellikler

- **Gemini Few-Shot Prompting** — Tweet'i yapılandırılmış JSON'a dönüştürür (`city`, `district`, `need_types`, `urgency_score`, `map_priority`)
- **Gerçek zamanlı harita** — Leaflet + ısı katmanı, kritik noktalar kırmızı gösterilir
- **Rate-limit koruması** — Gemini 3.1 Flash Lite: 15 RPM / 500 RPD dahilinde çalışır
- **D3 analitik grafikler** — İhtiyaç dağılımı, il yoğunluğu, aciliyet skoru
- **Mock tweet desteği** — Demo için gerçek API'ye gerek kalmadan test edilebilir
- **Twitter API polling** — Her 30 saniyede bir yeni tweet çeker, cache'de tutar

---

## Kurulum

### Gereksinimler
- Python 3.11+ (conda)
- Node.js 18+
- Gemini API anahtarı ([Google AI Studio](https://aistudio.google.com))
- Twitter Bearer Token (opsiyonel)

### Backend

```bash
conda create -n hacknigde python=3.11 -y
conda activate hacknigde

cd backend
cp .env.example .env
# .env dosyasına GEMINI_API_KEY ve TWITTER_KEY ekle

pip install -r requirements.txt
python main.py
```

Backend `http://localhost:8000` adresinde çalışır.  
Swagger UI: `http://localhost:8000/docs`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend `http://localhost:3000` adresinde açılır.

---

## API Endpoint'leri

| Method | Endpoint | Açıklama |
|--------|----------|----------|
| `GET` | `/health` | Sağlık kontrolü |
| `GET` | `/tweets` | Cache'teki tweet'ler |
| `GET` | `/refresh` | Manuel tweet yenile |
| `POST` | `/analyze` | Tek tweet analiz |
| `POST` | `/analyze-all` | Tüm cache'i analiz et |
| `GET` | `/results` | DB'deki tüm analizler |
| `GET` | `/results/{priority}` | Önceliğe göre filtre |
| `POST` | `/mock-tweet` | Demo tweet ekle + analiz |
| `GET` | `/rate-limit` | Gemini rate-limit durumu |

---

## Örnek Analiz Çıktısı

```json
{
  "city": "Hatay",
  "district": "Antakya",
  "neighborhood": "Cumhuriyet Mahallesi",
  "need_types": ["arama_kurtarma", "saglik"],
  "urgency_score": 5,
  "confidence": 0.98,
  "summary": "Enkaz altında yaralı kişiler var, acil yardım bekleniyor.",
  "map_priority": "critical"
}
```

---

## Teknoloji Yığını

| Katman | Teknoloji |
|--------|-----------|
| Backend | FastAPI, Python 3.11 |
| AI | Google Gemini 3.1 Flash Lite |
| Veritabanı | SQLite |
| Frontend | Vite (Vanilla JS) |
| Harita | Leaflet.js + leaflet-heat |
| Grafikler | D3.js v7 |
| Twitter | Tweepy v4 |

---

## Ekip

**TheTrippleLoop** — HackNiğde 2026

---

## Lisans

[MIT](LICENSE)
