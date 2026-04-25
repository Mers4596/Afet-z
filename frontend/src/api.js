/**
 * AfetİZ — Backend API Servisi
 *
 * Backend endpoint'leri:
 *   GET  /tweets        → Cache'teki tweet'ler (polling)
 *   GET  /refresh       → Manuel refresh (spam korumalı)
 *   POST /analyze       → Tek tweet analiz
 *   POST /analyze-all   → Tüm cache'i analiz
 *   GET  /results       → DB'deki analiz sonuçları
 *   GET  /results/:pri  → Önceliğe göre filtre
 *   GET  /rate-limit    → Gemini rate-limit durumu
 *   POST /mock-tweet    → Demo tweet ekle + analiz
 *   GET  /earthquakes   → AFAD son 24h depremler
 */

const API_BASE = 'http://localhost:8000';

/**
 * @param {string} endpoint
 * @param {RequestInit} [options]
 */
async function apiFetch(endpoint, options = {}) {
    const res = await fetch(`${API_BASE}${endpoint}`, {
        headers: { 'Content-Type': 'application/json' },
        ...options,
    });
    if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `API hatası: ${res.status}`);
    }
    return res.json();
}

/** Tweet cache'ini getir (polling) */
export function fetchTweets() {
    return apiFetch('/tweets');
}

/** Manuel refresh (spam korumalı) */
export function refreshTweets() {
    return apiFetch('/refresh');
}

/** Tek tweet analiz et */
export function analyzeTweet(text, checkAuthenticity = false) {
    return apiFetch('/analyze', {
        method: 'POST',
        body: JSON.stringify({ text, check_authenticity: checkAuthenticity }),
    });
}

/** Cache'teki tüm tweet'leri analiz et */
export function analyzeAll() {
    return apiFetch('/analyze-all', { method: 'POST' });
}

/** Veritabanındaki analiz sonuçlarını getir */
export function fetchResults() {
    return apiFetch('/results');
}

/** Önceliğe göre filtrele */
export function fetchResultsByPriority(priority) {
    return apiFetch(`/results/${priority}`);
}

/** Gemini rate-limit durumu */
export function fetchRateLimit() {
    return apiFetch('/rate-limit');
}

/** Mock tweet ekle + analiz et (demo) */
export function addMockTweet(text, checkAuthenticity = false) {
    return apiFetch('/mock-tweet', {
        method: 'POST',
        body: JSON.stringify({ text, check_authenticity: checkAuthenticity }),
    });
}

/** AFAD son 24h deprem listesi */
export function fetchEarthquakes(force = false) {
    return apiFetch(`/earthquakes${force ? '?force=true' : ''}`);
}

/** #afetiz hashtagiyle paylaşılan tweet'leri çek */
export function fetchHashtagTweets(force = false) {
    return apiFetch(`/hashtag-tweets${force ? '?force=true' : ''}`);
}

/** Bölge bazlı risk skorlarını getir */
export function fetchRegionRisk() {
    return apiFetch('/region-risk');
}

/** Güvenilir hesap listesini getir */
export function fetchTrustedAccounts() {
    return apiFetch('/trusted-accounts');
}

/** Güvenilir hesap ekle */
export function addTrustedAccount(username, note = '') {
    return apiFetch('/trusted-accounts', {
        method: 'POST',
        body: JSON.stringify({ username, note }),
    });
}

/** Güvenilir hesabı sil */
export function removeTrustedAccount(username) {
    return apiFetch(`/trusted-accounts/${encodeURIComponent(username)}`, {
        method: 'DELETE',
    });
}

/** PDF raporu için Gemini kriz analizi iste */
export function fetchCrisisReport(stats) {
    return apiFetch('/export/pdf-analysis', {
        method: 'POST',
        body: JSON.stringify(stats),
    });
}

/**
 * WeasyPrint tabanlı 5 sayfalık kriz raporunu indir.
 * Blob olarak döner; çağıran taraf <a download> ile tetikler.
 */
export async function downloadFullPdfReport() {
    const res = await fetch(`${API_BASE}/export/full-pdf-report`, {
        headers: { Accept: 'application/pdf' },
    });
    if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `PDF raporu alınamadı: ${res.status}`);
    }
    return res.blob();
}
