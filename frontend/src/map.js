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
 * Haritayı başlat
 * @returns {{ map: L.Map }}
 */
export function initMap() {
    map = L.map('map', {
        zoomControl: true,
        attributionControl: false,
    }).setView(MAP_CENTER, MAP_ZOOM);

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; CartoDB, OSM',
        subdomains: 'abcd',
    }).addTo(map);

    // Isı katmanı
    heatLayer = L.heatLayer([], { radius: 22, blur: 16, maxZoom: 12, minOpacity: 0.4 });
    heatLayer.addTo(map);

    // Marker grubu
    markerGroup = L.layerGroup().addTo(map);

    // Türkiye GeoJSON sınırları
    loadTurkeyBorders();

    return { map };
}

/** Türkiye il sınırlarını yükle */
function loadTurkeyBorders() {
    const geoUrl = 'https://raw.githubusercontent.com/alpers/Turkey-Maps-GeoJSON/master/turkey.geojson';
    fetch(geoUrl)
        .then(res => res.json())
        .then(data => {
            L.geoJSON(data, {
                style: {
                    color: '#38bdf8',
                    weight: 1.2,
                    fillColor: '#0f172a',
                    fillOpacity: 0.2,
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

    const heatPoints = [];
    markerGroup.clearLayers();

    analyzedTweets.forEach(tweet => {
        if (!tweet.analysis) return;

        const { city, district, urgency_score, map_priority, need_types, summary } = tweet.analysis;
        const coords = getCityCoords(city);

        // Rastgele küçük offset (aynı şehirdeki noktalar üst üste binmesin)
        const lat = coords[0] + (Math.random() - 0.5) * 0.08;
        const lng = coords[1] + (Math.random() - 0.5) * 0.08;

        // Isı noktası ekle
        const intensity = urgency_score / 5;
        heatPoints.push([lat, lng, intensity]);

        // Marker ekle
        const color = PRIORITY_COLORS[map_priority] || PRIORITY_COLORS.medium;
        const marker = L.circleMarker([lat, lng], {
            radius: 4 + urgency_score * 2,
            fillColor: color,
            color: color,
            weight: 1,
            opacity: 0.9,
            fillOpacity: 0.6,
        });

        const needLabels = (need_types || []).map(n => NEED_TYPE_LABELS[n] || n).join(', ');

        marker.bindPopup(`
            <div style="font-family:Inter,sans-serif; font-size:12px; min-width:180px;">
                <strong style="font-size:14px;">${city}</strong>
                ${district ? `<br><span style="color:#94a3b8;">${district}</span>` : ''}
                <hr style="border-color:#334155; margin:6px 0;">
                <div><b>Aciliyet:</b> ${urgency_score}/5</div>
                <div><b>İhtiyaçlar:</b> ${needLabels || '—'}</div>
                <div style="margin-top:4px; color:#cbd5e1;">${summary || ''}</div>
            </div>
        `);

        markerGroup.addLayer(marker);
    });

    // Isı katmanını güncelle
    if (heatLayer) {
        map.removeLayer(heatLayer);
    }
    heatLayer = L.heatLayer(heatPoints, {
        radius: 22,
        blur: 16,
        maxZoom: 12,
        minOpacity: 0.4,
        gradient: {
            0.2: '#10b981',
            0.4: '#facc15',
            0.6: '#f97316',
            0.8: '#ef4444',
            1.0: '#dc2626',
        },
    });
    heatLayer.addTo(map);
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
