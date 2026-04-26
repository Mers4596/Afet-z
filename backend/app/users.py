"""
Kullanıcı Veritabanı (Mock)
"""

users = [
    {"chat_id": 6751165369, "lat": 40.98, "lon": 29.12}, # Örnek kullanıcı 1 (İstanbul/Ataşehir civarı)
    {"chat_id": 987654321, "lat": 39.92, "lon": 32.85}, # Örnek kullanıcı 2 (Ankara)
    {"chat_id": 2043694084, "lat": 41.01, "lon": 28.97}, # Örnek gerçek veya test chat_id
]

groups = [
    # Telegram grup ID'leri genellikle eksi (-) işareti ile başlar (örn: -1001234567890)
    {"group_id": -5245420048, "name": "Afetiz"},
]
