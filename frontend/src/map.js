/**
 * AfetİZ — Leaflet Harita Modülü
 *
 * Isı haritası + marker'lar ile afet noktalarını gösterir.
 * Backend'den gelen analiz sonuçlarını haritaya yansıtır.
 */

// Leaflet CDN'den yüklü — global L mevcut
const MAP_CENTER = [39.0, 35.0];
const MAP_ZOOM = 6;

const PRIORITY_COLORS = {
    critical: '#ef4444',
    high: '#f97316',
    medium: '#facc15',
    low: '#10b981',
};

// Türkiye şehir koordinatları (geocoding yedeği)
const CITY_COORDS = {
    'hatay': [36.4018, 36.3498],
    'kahramanmaraş': [37.5858, 36.9371],
    'gaziantep': [37.0662, 37.3833],
    'adıyaman': [37.7648, 38.2786],
    'malatya': [38.3552, 38.3095],
    'diyarbakır': [37.9144, 40.2306],
    'adana': [36.9914, 35.3308],
    'osmaniye': [37.0743, 36.2463],
    'şanlıurfa': [37.1591, 38.7969],
    'elazığ': [38.6810, 39.2264],
    'istanbul': [41.0082, 28.9784],
    'ankara': [39.9334, 32.8597],
    'izmir': [38.4192, 27.1287],
    'bursa': [40.1885, 29.061],
    'antalya': [36.8969, 30.7133],
    'trabzon': [41.0019, 39.7178],
    'konya': [37.8746, 32.4932],
    'samsun': [41.2867, 36.33],
    'kayseri': [38.7312, 35.4787],
    'mersin': [36.8121, 34.6415],
    'bilinmiyor': [39.0, 35.0],
};

let map = null;
let heatLayer = null;
let markerGroup = null;

// ── Baz İstasyonu Simülasyonu ──────────────────────────────
let cellTowerGroup = null;
let cellTowerTimer = null;
let cellTowerVisible = true;

// Aktif simülasyon zonları (updateCellTowersFromCities ile doldurulur)
let _activeCellZones = [];

// Şehir başına bina şablonları (2-3 ad per city)
const BUILDING_TEMPLATES_BY_CITY = {
    'adana': ['Seyhan Rezidans', 'Adana Şehir Hastanesi', 'Yüreğir Ticaret Merkezi'],
    'adiyaman': ['Adıyaman Çarşı Pasajı', 'Besni Konutları', 'Gölbaşı Mahalle Okulu'],
    'afyonkarahisar': ['Afyon Termal Otel', 'Sandıklı Konutları', 'Dumlupınar Üniversitesi'],
    'agri': ['Ağrı Dağı Konakları', 'Patnos İş Merkezi', 'Doğubayazıt Çarşısı'],
    'amasya': ['Yeşilırmak Yalı Boyu', 'Merzifon OSB', 'Amasya Devlet Hastanesi'],
    'ankara': ['Çankaya Ofis Kulesi', 'Keçiören Mahalle Bloğu', 'Mamak Konut Sitesi'],
    'antalya': ['Lara Tatil Köyü', 'Konyaaltı Sahil Konutları', 'Muratpaşa İş Merkezi'],
    'artvin': ['Hopa Liman İşletmesi', 'Artvin Orman Bölge', 'Borçka Konutları'],
    'aydin': ['Kuşadası Yazlıkları', 'Aydın Tekstil Fabrikası', 'Nazilli Çarşı'],
    'balikesir': ['Edremit Körfez Sitesi', 'Balıkesir Sanayi Odası', 'Bandırma Lojistik'],
    'bilecik': ['Bilecik Seramik Fabrikası', 'Bozüyük Toki', 'Söğüt Kültür Merkezi'],
    'bingol': ['Bingöl Kayak Merkezi', 'Genç Caddesi İş Hanı', 'Solhan Devlet Hastanesi'],
    'bitlis': ['Tatvan İskelesi', 'Ahlat Taş Konakları', 'Bitlis Eren Üniv.'],
    'bolu': ['Abant Dağ Evleri', 'Bolu Tünel Tesisleri', 'Gerede Deri Sanayi'],
    'burdur': ['Burdur Şeker Fabrikası', 'Bucak İş Merkezi', 'Salda Turizm Tesisleri'],
    'bursa': ['Osmangazi Tekstil', 'Nilüfer Rezidansları', 'İnegöl Mobilya AVM'],
    'canakkale': ['18 Mart Yerleşkesi', 'Gelibolu Konutları', 'Çanakkale Liman'],
    'cankiri': ['Çankırı Tuz Madeni', 'Ilgaz Dağ Tesisi', 'Orta Mahalle Konutları'],
    'corum': ['Çorum Leblebi Fabrikası', 'Sungurlu OSB', 'Kargı Devlet Hastanesi'],
    'denizli': ['Pamukkale Tekstil', 'Denizli OSB', 'Merkezefendi Rezidans'],
    'diyarbakir': ['Tarihi Sur Konutları', 'Büyükşehir Kampüsü', 'Bağlar İş Hanı'],
    'edirne': ['Selimiye Arasta', 'Keşan İş Merkezi', 'Edirne Devlet Hastanesi'],
    'elazig': ['Elazığ Çarşısı', 'Fırat Üniv. Yerleşkesi', 'Sivrice Konutları'],
    'erzincan': ['Erzincan Bakır Çarşısı', 'Tercan Konutları', 'Refahiye İş Merkezi'],
    'erzurum': ['Palandöken Oteli', 'Atatürk Üniversitesi', 'Yakutiye İş Merkezi'],
    'eskisehir': ['Odunpazarı Evleri', 'Anadolu Üniv. Kampüsü', 'Eskişehir OSB'],
    'gaziantep': ['Şahinbey Ticaret Merkezi', 'Gaziantep Şehir Hastanesi', 'Nurdağı Sanayi Sitesi'],
    'giresun': ['Giresun Fındık Fabrikası', 'Bulancak Sanayi', 'Espiye Konutları'],
    'gumushane': ['Gümüşhane Maden İşletmesi', 'Kelkit Tarım Merkezi', 'Köse Konutları'],
    'hakkari': ['Yüksekova Havalimanı', 'Hakkari Devlet Hastanesi', 'Şemdinli Çarşısı'],
    'hatay': ['Antakya Merkez Rezidans', 'Hatay Devlet Hastanesi', 'Defne Ticaret Merkezi'],
    'isparta': ['Isparta Gül Fabrikası', 'Eğirdir Tatil Sitesi', 'Süleyman Demirel Üniv.'],
    'mersin': ['Mersin Liman Kulesi', 'Mezitli Sahil Sitesi', 'Tarsus Sanayi'],
    'istanbul': ['Kadıköy İş Merkezi', 'Pendik Rezidans', 'Sultanbeyli Konut'],
    'izmir': ['Konak Çarşısı', 'Bornova Üniv. Sitesi', 'Karşıyaka Rezidans'],
    'kars': ['Kars Kalesi Konakları', 'Sarıkamış Kayak Merkezi', 'Digor İş Hanı'],
    'kastamonu': ['İnebolu Limanı', 'Tosya Pirinç Fabrikası', 'Kastamonu Valilik'],
    'kayseri': ['Kayseri OSB Fabrika', 'Erciyes Üniversitesi', 'Melikgazi Rezidans'],
    'kirklareli': ['Lüleburgaz Fabrikaları', 'Babaeski Konutları', 'Kırklareli OSB'],
    'kirsehir': ['Kırşehir Termal Tesis', 'Mucur İş Hanı', 'Kaman Konutları'],
    'kocaeli': ['Gebze Teknoloji Kampüsü', 'İzmit Petrokimya', 'Kartepe Konutları'],
    'konya': ['Selçuklu Konut Kompleksi', 'Konya Şehir Hastanesi', 'Karatay Sanayi'],
    'kutahya': ['Kütahya Seramik Fabrikası', 'Tavşanlı Linyit', 'Gediz Konutları'],
    'malatya': ['Yeşilyurt Sitesi', 'Malatya Devlet Hastanesi', 'Battalgazi Ticaret Hanı'],
    'manisa': ['Manisa Vestel City', 'Akhisar Zeytin İşleme', 'Turgutlu OSB'],
    'kahramanmaras': ['KMaraş Şehir Hastanesi', 'Merkez Konut Bloğu-7', 'Elbistan AVM'],
    'mardin': ['Artuklu Taş Evleri', 'Kızıltepe Hububat Merkezi', 'Mardin OSB'],
    'mugla': ['Bodrum Marina Evleri', 'Marmaris Otel Kampüsü', 'Fethiye Tatil Köyü'],
    'mus': ['Muş Ovası Tarım İşletmesi', 'Malazgirt Konutları', 'Varto Devlet Hastanesi'],
    'nevsehir': ['Ürgüp Kaya Otel', 'Kapadokya Müze Binası', 'Avanos Atölyeleri'],
    'nigde': ['Niğde Merkez Sitesi', 'Bor Ticaret Hanı', 'Ulukışla İst. Mah.'],
    'ordu': ['Fındık İşleme Tesisi', 'Ünye Liman Deposu', 'Fatsa Sanayi'],
    'rize': ['Rize Çay Fabrikası', 'Ardeşen Konutları', 'Pazar İş Merkezi'],
    'sakarya': ['Adapazarı Otomotiv Fabrikası', 'Serdivan Rezidans', 'Sapanca Villaları'],
    'samsun': ['Samsun Liman Lojistik', 'Atakum Sahil Blokları', 'Bafra Tarım İşletmesi'],
    'siirt': ['Siirt Fıstık İşleme', 'Kurtalan Devlet Hastanesi', 'Pervari Konutları'],
    'sinop': ['Sinop Tersanesi', 'Boyabat Tuğla Fabrikası', 'Ayancık Orman İşletme'],
    'sivas': ['Sivas Demir Çelik', 'Cumhuriyet Üniv. Hastanesi', 'Şarkışla Konutları'],
    'tekirdag': ['Çorlu Tekstil Fabrikası', 'Çerkezköy OSB', 'Süleymanpaşa Liman'],
    'tokat': ['Tokat Gaziosmanpaşa Üniv.', 'Erbaa Sanayi', 'Niksar İş Hanı'],
    'trabzon': ['Trabzon Liman İşletmesi', 'Akçaabat Konutları', 'KTÜ Yerleşkesi'],
    'tunceli': ['Munzur Su Fabrikası', 'Ovacık Konutları', 'Tunceli Devlet Hastanesi'],
    'sanliurfa': ['Balıklıgöl Çarşı İş Hanı', 'Harran Konukevi', 'Viranşehir Tarım OSB'],
    'usak': ['Uşak Battaniye Fabrikası', 'Eşme Konutları', 'Uşak OSB'],
    'van': ['Van Gölü İskelesi', 'Edremit Sahil Evleri', 'Erciş İş Merkezi'],
    'yozgat': ['Yozgat Şehir Hastanesi', 'Sorgun Kömür İşletme', 'Yerköy Konutları'],
    'zonguldak': ['TTK Maden Tesisleri', 'Ereğli Demir Çelik', 'Zonguldak Limanı'],
    'aksaray': ['Aksaray Mercedes Fabrikası', 'Ihlara Turizm Tesisi', 'Eskil Tarım'],
    'bayburt': ['Bayburt Taşı İşleme', 'Aydıntepe Konutları', 'Demirözü İş Hanı'],
    'karaman': ['Karaman Bisküvi Fabrikası', 'Ermenek Konutları', 'Karamanoğlu Mehmet Bey Üniv.'],
    'kirikkale': ['MKE Fabrikaları', 'Yahşihan Öğrenci Evleri', 'Kırıkkale Rafinerisi'],
    'batman': ['Batman Petrol Rafinerisi', 'Hasankeyf Müzesi', 'Kozluk Konutları'],
    'sirnak': ['Cizre Sınır Kapısı', 'Silopi Lojistik Merkezi', 'Şırnak Valilik'],
    'bartin': ['Bartın Liman Tesisleri', 'Amasra Turizm Oteli', 'Ulus Konutları'],
    'ardahan': ['Ardahan Kalesi Çarşısı', 'Göle Tarım Merkezi', 'Posof Devlet Hastanesi'],
    'igdir': ['Iğdır Kayısı Fabrikası', 'Aralık Sınır Ticaret', 'Tuzluca İş Hanı'],
    'yalova': ['Yalova Tersaneler Bölgesi', 'Çınarcık Yazlıkları', 'Termal Otel Kampüsü'],
    'karabuk': ['Kardemir Fabrikaları', 'Safranbolu Tarihi Konak', 'Eskipazar OSB'],
    'kilis': ['Kilis Zeytin İşleme', 'Elbeyli Konutları', 'Polateli Sanayi'],
    'osmaniye': ['İnönü Apartmanı', 'Osmaniye Devlet Hastanesi', 'Kadirli Çarşısı'],
    'duzce': ['Düzce Mobilya Sanayi', 'Akçakoca Turizm Tesisleri', 'Gümüşova OSB']
};
const BUILDING_TEMPLATES_DEFAULT = ['Şehir Merkezi Binası', 'Devlet Hastanesi', 'Ticaret Hanı'];

/**
 * Türkçe şehir adını ASCII'ye indirge (template sözlüğü için)
 */
function _cityKey(city) {
    return city.toLowerCase()
        .replace(/ş/g, 's').replace(/ğ/g, 'g').replace(/ı/g, 'i')
        .replace(/ö/g, 'o').replace(/ü/g, 'u').replace(/ç/g, 'c')
        .replace(/\s+/g, '');
}

/**
 * Analiz edilmiş tweet'lerden dinamik baz istasyonu zonları oluştur.
 * Her ilde tweet yoğunluğuna göre 2-3 baz istasyonu üretilir.
 */
function buildCellTowerZones(analyzedTweets) {
    const cityMap = {};
    analyzedTweets.forEach(tweet => {
        const city = tweet.analysis && tweet.analysis.city;
        if (!city || city === 'Bilinmiyor') return;
        if (!cityMap[city]) cityMap[city] = { count: 0, district: tweet.analysis.district || '' };
        cityMap[city].count++;
    });

    const zones = [];
    Object.entries(cityMap).forEach(([city, info], ci) => {
        const coords = getCityCoords(city);
        const tpl = BUILDING_TEMPLATES_BY_CITY[_cityKey(city)] || BUILDING_TEMPLATES_DEFAULT;
        const towerCount = info.count >= 3 ? 3 : 2;

        for (let t = 0; t < towerCount; t++) {
            const seedId = `${city}_bt_${t}`;
            const off = deterministicOffset(seedId);
            const base = 100 + Math.round((Math.abs(off.dLat * 1e4) % 400)) + info.count * 30;
            zones.push({
                id: `dyn_${ci}_${t}`,
                name: city + (info.district ? ' / ' + info.district : ''),
                lat: coords[0] + off.dLat * 0.6,
                lng: coords[1] + off.dLng * 0.7,
                building: tpl[t] || tpl[0],
                base,
                city,
            });
        }
    });
    return zones;
}

/** Deterministic gürültü üreteci — sinüs bazlı döngüsel varyasyon */
function _simulatePeopleCount(baseCount, id, nowMs) {
    let phase = 0;
    for (let i = 0; i < id.length; i++) phase += id.charCodeAt(i);
    const cycle = (2 * Math.PI * (nowMs % 600000)) / 600000;
    const variation = Math.sin(cycle + phase * 0.7) * 0.30;
    return Math.max(1, Math.round(baseCount * (1 + variation)));
}

/** Baz istasyonu marker'larını oluştur/güncelle */
function _refreshCellTowers() {
    if (!map || !cellTowerGroup) return;
    cellTowerGroup.clearLayers();
    const now = Date.now();

    _activeCellZones.forEach(zone => {
        const count = _simulatePeopleCount(zone.base, zone.id, now);
        const danger = count > zone.base * 1.2 ? 'high' : count < zone.base * 0.6 ? 'low' : 'normal';
        const color = danger === 'high' ? '#f97316' : danger === 'low' ? '#22c55e' : '#38bdf8';
        const ringColor = danger === 'high' ? 'rgba(249,115,22,0.35)' : 'rgba(56,189,248,0.2)';

        const icon = L.divIcon({
            className: '',
            html: `<div class="cell-tower-label" style="--ct-color:${color}; --ct-ring:${ringColor};">
                <div class="ct-count">${count.toLocaleString('tr-TR')}</div>
                <div class="ct-sub">kişi</div>
            </div>`,
            iconAnchor: [30, 30],
        });

        const marker = L.marker([zone.lat, zone.lng], { icon });
        marker.bindPopup(`
            <div style="font-family:Inter,sans-serif;font-size:12px;min-width:180px;">
                <div style="font-weight:700;font-size:13px;margin-bottom:4px;">
                    <span style="color:${color};">▼</span> ${zone.building}
                </div>
                <div style="color:#94a3b8;font-size:11px;margin-bottom:6px;">${zone.name}</div>
                <hr style="border-color:#334155;margin:4px 0;">
                <div><b>Tahmini Kişi:</b> <span style="color:${color};font-weight:700;">${count.toLocaleString('tr-TR')}</span></div>
                <div style="margin-top:2px;"><b>Referans (10 dk önce):</b> ${zone.base.toLocaleString('tr-TR')}</div>
                <div style="margin-top:4px;color:#64748b;font-size:10px;">🗼 Baz istasyonu sinyalinden simüle edilmiştir</div>
            </div>
        `);
        cellTowerGroup.addLayer(marker);

        const ring = L.circleMarker([zone.lat, zone.lng], {
            radius: 14,
            fillColor: color,
            fillOpacity: 0.08,
            color: color,
            weight: 1.2,
            opacity: 0.45,
            interactive: false,
        });
        cellTowerGroup.addLayer(ring);
    });
}

/** Baz istasyonu katmanını başlat (harita init sonrası çağrılır) */
export function initCellTowerLayer() {
    if (!map) return;
    cellTowerGroup = L.layerGroup().addTo(map);
    cellTowerTimer = setInterval(_refreshCellTowers, 10 * 60 * 1000);
}

/**
 * Analiz sonuçlarına göre baz istasyonlarını güncelle.
 * updateMapWithResults çağrısının ardından çağrılır.
 */
export function updateCellTowersFromCities(analyzedTweets) {
    _activeCellZones = buildCellTowerZones(analyzedTweets);
    if (cellTowerGroup && cellTowerVisible) _refreshCellTowers();
}

/**
 * Güncel baz istasyonu verilerini PDF için döndür.
 */
export function getCellTowerSnapshot() {
    const now = Date.now();
    return _activeCellZones.map(zone => ({
        name: zone.name,
        building: zone.building,
        city: zone.city,
        base: zone.base,
        current: _simulatePeopleCount(zone.base, zone.id, now),
    }));
}

/** Baz istasyonu katmanını aç/kapat — toggle butonu için */
export function toggleCellTowerLayer() {
    if (!map || !cellTowerGroup) return;
    if (map.hasLayer(cellTowerGroup)) {
        map.removeLayer(cellTowerGroup);
        cellTowerVisible = false;
    } else {
        map.addLayer(cellTowerGroup);
        cellTowerVisible = true;
        _refreshCellTowers();
    }
    return cellTowerVisible;
}

/**
 * tweet_id string'inden deterministik [-0.5, 0.5] aralığında iki sabit değer üretir.
 * Aynı tweet_id her zaman aynı koordinat offsetini verir — harita yenilenince noktalar kaymaaz.
 * @param {string} id
 * @returns {{ dLat: number, dLng: number }}
 */
function deterministicOffset(id) {
    let h1 = 0x9e3779b9, h2 = 0x6c62272e;
    const s = String(id);
    for (let i = 0; i < s.length; i++) {
        const c = s.charCodeAt(i);
        h1 = Math.imul(h1 ^ c, 0x9e3779b9);
        h2 = Math.imul(h2 ^ c, 0x517cc1b7);
    }
    h1 ^= h1 >>> 16;
    h2 ^= h2 >>> 16;
    return {
        dLat: (((h1 >>> 0) % 10000) / 10000 - 0.5) * 0.10,
        dLng: (((h2 >>> 0) % 10000) / 10000 - 0.5) * 0.14,
    };
}

// Aktif görünüm modu: 'points' | 'heat'
let mapMode = 'points';

// Son veri — mod değişince yeniden render için saklanır
let _lastTweets = [];

/**
 * Haritayı başlat
 * @returns {{ map: L.Map }}
 */
export function initMap() {
    // Türkiye sınırları (SouthWest, NorthEast)
    const southWest = L.latLng(35.0, 25.0);
    const northEast = L.latLng(43.0, 46.0);
    const bounds = L.latLngBounds(southWest, northEast);

    map = L.map('map', {
        zoomControl: true,
        attributionControl: true,
        maxBounds: bounds,
        maxBoundsViscosity: 1.0,
        minZoom: 5,
    }).setView(MAP_CENTER, MAP_ZOOM);

    // Google Hybrid Tiles (Satellite + Road + Terrain)
    L.tileLayer('https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', {
        attribution: '&copy; Google Maps',
        maxZoom: 20,
    }).addTo(map);

    // Isı katmanı
    heatLayer = L.heatLayer([], { radius: 22, blur: 16, maxZoom: 12, minOpacity: 0.4 });
    heatLayer.addTo(map);

    // Marker grubu
    markerGroup = L.layerGroup().addTo(map);

    // Türkiye GeoJSON sınırları
    loadTurkeyBorders();

    // Harita mod kontrol butonu (sağ üst köşe)
    _addModeControl();

    return { map };
}

/** Harita köşesine mod geçiş kontrolü ekle */
function _addModeControl() {
    const MapModeControl = L.Control.extend({
        options: { position: 'topright' },

        onAdd() {
            const container = L.DomUtil.create('div', 'map-mode-control leaflet-bar');
            container.innerHTML = `
                <button class="map-mode-btn active" data-mode="points" title="Noktasal görünüm">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/>
                    </svg>
                    Noktasal
                </button>
                <button class="map-mode-btn" data-mode="heat" title="Isı haritası görünümü">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M13.5 0.67s.74 2.65.74 4.8c0 2.06-1.35 3.73-3.41 3.73-2.07 0-3.63-1.67-3.63-3.73l.03-.36C5.21 7.51 4 10.62 4 14c0 4.42 3.58 8 8 8s8-3.58 8-8C20 8.61 17.41 3.8 13.5.67zM11.71 19c-1.78 0-3.22-1.4-3.22-3.14 0-1.62 1.05-2.76 2.81-3.12 1.77-.36 3.6-1.21 4.62-2.58.39 1.29.59 2.65.59 4.04 0 2.65-2.15 4.8-4.8 4.8z"/>
                    </svg>
                    Isı Haritası
                </button>
                <button class="map-mode-btn cell-tower-toggle-btn active-ct" id="mapBtnCellTower" title="Baz istasyonu kişi sayıları (10 dk güncelleme)">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M1.293 7.707a1 1 0 0 1 0-1.414 10 10 0 0 1 14.142 0 1 1 0 1 1-1.414 1.414 8 8 0 0 0-11.314 0 1 1 0 0 1-1.414 0zM5.05 11.464a1 1 0 0 1 0-1.414 6 6 0 0 1 8.485 0 1 1 0 1 1-1.414 1.414 4 4 0 0 0-5.657 0 1 1 0 0 1-1.414 0zM9 16a1 1 0 1 0 0-2 1 1 0 0 0 0 2z"/>
                    </svg>
                    Baz İst.
                </button>
            `;

            // Leaflet click-propagation'ı durdur (harita sürüklenmesini engeller)
            L.DomEvent.disableClickPropagation(container);
            L.DomEvent.disableScrollPropagation(container);

            container.querySelectorAll('.map-mode-btn[data-mode]').forEach(btn => {
                L.DomEvent.on(btn, 'click', () => {
                    if (btn.dataset.mode === mapMode) return;
                    mapMode = btn.dataset.mode;
                    container.querySelectorAll('.map-mode-btn[data-mode]')
                        .forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    _applyMode();
                });
            });

            // Baz istasyonu toggle
            const ctBtn = container.querySelector('#mapBtnCellTower');
            if (ctBtn) {
                L.DomEvent.on(ctBtn, 'click', () => {
                    const visible = toggleCellTowerLayer();
                    ctBtn.classList.toggle('active-ct', visible);
                    ctBtn.style.opacity = visible ? '1' : '0.45';
                });
            }

            return container;
        },
    });

    new MapModeControl().addTo(map);
}

/** Mevcut moda göre katmanları göster/gizle */
function _applyMode() {
    if (!map) return;
    if (mapMode === 'points') {
        if (!map.hasLayer(markerGroup)) markerGroup.addTo(map);
        if (heatLayer && map.hasLayer(heatLayer)) map.removeLayer(heatLayer);
    } else {
        if (map.hasLayer(markerGroup)) map.removeLayer(markerGroup);
        if (heatLayer && !map.hasLayer(heatLayer)) heatLayer.addTo(map);
    }
}

/** Türkiye il sınırlarını yükle */
function loadTurkeyBorders() {
    const geoUrl = 'https://raw.githubusercontent.com/alpers/Turkey-Maps-GeoJSON/master/turkey.geojson';
    fetch(geoUrl)
        .then(res => res.json())
        .then(data => {
            L.geoJSON(data, {
                style: {
                    color: '#ffffff',
                    weight: 0.8,
                    fillColor: 'transparent',
                    fillOpacity: 0,
                },
                onEachFeature: (feature, layer) => {
                    if (feature.properties?.name) {
                        layer.bindTooltip(feature.properties.name, {
                            className: 'geo-tooltip',
                        });
                    }
                },
            }).addTo(map);
        })
        .catch(err => console.warn('GeoJSON yüklenemedi:', err));
}

/**
 * Şehir adından koordinat bul
 * @param {string} city
 * @returns {[number, number]}
 */
function getCityCoords(city) {
    const key = city.toLowerCase().replace(/\s+/g, '');
    return CITY_COORDS[key] || CITY_COORDS['bilinmiyor'];
}

/**
 * Analiz sonuçlarını haritaya yansıt
 * @param {Array} analyzedTweets - Backend'den gelen AnalyzedTweet[]
 */
export function updateMapWithResults(analyzedTweets) {
    if (!map) return;
    _lastTweets = analyzedTweets;
    _rebuildLayers(analyzedTweets);
    _applyMode();
}

/** Veriyi işleyerek ısı + marker katmanlarını sıfırdan oluştur */
function _rebuildLayers(analyzedTweets) {
    const heatPoints = [];
    markerGroup.clearLayers();

    analyzedTweets.forEach(tweet => {
        if (!tweet.analysis) return;

        const { city, district, urgency_score, map_priority, need_types, summary } = tweet.analysis;
        const isPrecise = tweet.analysis?.has_precise_location === true;

        // Kesin konumlu tweet'ler: şehir merkezine sabitlenir (offset yok)
        // Diğerleri: tweet_id tabanlı deterministik offset — yenileme/zoom'da kaymazlar
        const coords = getCityCoords(city);
        let lat, lng;
        if (isPrecise) {
            // Kesin adres varsa şehir merkezini kullan (GPS olmadığı için)
            // İlçe adı ile küçük ama sabit ayırım sağla
            const districtSeed = district ? String(city) + String(district) : String(city);
            const off = deterministicOffset(districtSeed + '_precise');
            lat = coords[0] + off.dLat * 0.3;  // kesin konumlar daha yakın kümelenir
            lng = coords[1] + off.dLng * 0.3;
        } else {
            // tweet_id bazlı sabit offset
            const off = deterministicOffset(String(tweet.tweet_id || tweet.id || city));
            lat = coords[0] + off.dLat;
            lng = coords[1] + off.dLng;
        }

        // Isı noktası ekle
        const intensity = urgency_score / 5;
        heatPoints.push([lat, lng, intensity]);

        // Marker ekle
        const color = PRIORITY_COLORS[map_priority] || PRIORITY_COLORS.medium;
        const markerColor = isPrecise ? '#c084fc' : color;
        const markerRadius = isPrecise ? 7 + urgency_score * 1.5 : 4 + urgency_score * 1.5;
        const marker = L.circleMarker([lat, lng], {
            radius: markerRadius,
            fillColor: markerColor,
            color: isPrecise ? '#ffffff' : markerColor,
            weight: isPrecise ? 2.5 : 1,
            opacity: isPrecise ? 1 : 0.9,
            fillOpacity: isPrecise ? 0.85 : 0.6,
        });

        // Kesin konumlu noktalar için dış halka (pulse ring) ekle
        if (isPrecise) {
            const ring = L.circleMarker([lat, lng], {
                radius: markerRadius + 6,
                fillColor: 'transparent',
                color: '#c084fc',
                weight: 1.5,
                opacity: 0.5,
                fillOpacity: 0,
                interactive: false,
            });
            markerGroup.addLayer(ring);
        }

        const needLabels = (need_types || []).map(n => NEED_TYPE_LABELS[n] || n).join(', ');
        const streetHtml = tweet.analysis?.street_address
            ? `<div style="color:#c084fc;margin-top:3px;"><b>📍 Adres:</b> ${tweet.analysis.street_address}</div>`
            : '';
        const preciseHtml = isPrecise
            ? `<div style="color:#c084fc;font-weight:600;margin-top:3px;">📌 Kesin Konum Tespit Edildi</div>`
            : '';

        marker.bindPopup(`
            <div style="font-family:Inter,sans-serif; font-size:12px; min-width:180px;">
                <strong style="font-size:14px;">${city}</strong>
                ${district ? `<br><span style="color:#94a3b8;">${district}</span>` : ''}
                ${streetHtml}
                ${preciseHtml}
                <hr style="border-color:#334155; margin:6px 0;">
                <div><b>Aciliyet:</b> ${urgency_score}/5</div>
                <div><b>İhtiyaçlar:</b> ${needLabels || '—'}</div>
                <div style="margin-top:4px; color:#cbd5e1;">${summary || ''}</div>
            </div>
        `);

        markerGroup.addLayer(marker);
    });

    // Isı katmanını güncelle (haritadan kaldırılmış olsa bile verisi taze olsun)
    if (heatLayer && map.hasLayer(heatLayer)) {
        map.removeLayer(heatLayer);
    }
    heatLayer = L.heatLayer(heatPoints, {
        radius: 28,
        blur: 20,
        maxZoom: 12,
        minOpacity: 0.45,
        gradient: {
            0.2: '#10b981',
            0.4: '#facc15',
            0.6: '#f97316',
            0.8: '#ef4444',
            1.0: '#7f1d1d',
        },
    });
    // _applyMode() çağırıncaya kadar haritaya ekleme
}

const NEED_TYPE_LABELS = {
    arama_kurtarma: 'Arama Kurtarma',
    saglik: 'Sağlık',
    su: 'Su',
    gida: 'Gıda',
    barinma: 'Barınma',
    yol_kapali: 'Yol Kapalı',
    yangin: 'Yangın',
    elektrik_iletisim: 'Elektrik/İletişim',
};

export { NEED_TYPE_LABELS, PRIORITY_COLORS };
