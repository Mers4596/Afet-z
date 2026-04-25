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
            `;

            // Leaflet click-propagation'ı durdur (harita sürüklenmesini engeller)
            L.DomEvent.disableClickPropagation(container);
            L.DomEvent.disableScrollPropagation(container);

            container.querySelectorAll('.map-mode-btn').forEach(btn => {
                L.DomEvent.on(btn, 'click', () => {
                    if (btn.dataset.mode === mapMode) return;
                    mapMode = btn.dataset.mode;
                    container.querySelectorAll('.map-mode-btn')
                        .forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    _applyMode();
                });
            });

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
