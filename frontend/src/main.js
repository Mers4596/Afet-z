/**
 * AfetİZ — Ana Uygulama
 *
 * Backend API'ye bağlanır, harita + grafikler + tweet feed günceller.
 * Fake-realtime polling (5sn) + manuel refresh + mock tweet desteği.
 */

import './style.css';
import { fetchTweets, refreshTweets, fetchResults, fetchRateLimit, addMockTweet, analyzeTweet, fetchEarthquakes, fetchTrustedAccounts, addTrustedAccount, removeTrustedAccount, fetchRegionRisk, analyzeAll } from './api.js';
import { initMap, updateMapWithResults, initCellTowerLayer, updateCellTowersFromCities, getCellTowerSnapshot, NEED_TYPE_LABELS, PRIORITY_COLORS } from './map.js';
import { initCharts, updateCharts } from './charts.js';
import { exportToExcel, exportToPDF } from './export.js';

const API_BASE = 'http://localhost:8000';

// ── State ──────────────────────────────────────────────────
let analyzedTweets = [];
let rawTweets = [];
let trustedAccounts = [];
let rateLimit = { requests_this_minute: 0, requests_today: 0, max_rpm: 15, max_rpd: 500, remaining_rpm: 15, remaining_rpd: 500 };
let isLoading = false;
let pollTimer = null;
let sahtelikAnalizi = false;   // Sahtelik Analizi toggle state
let authCache = {};            // {tweet_id: AuthenticityResult} — localStorage'da kalıcı

// ── LocalStorage ──────────────────────────────────────────
const LS_TOGGLE = 'afetiz_sahtelik';
const LS_AUTH = 'afetiz_auth_cache';

function loadPersistedState() {
    try {
        sahtelikAnalizi = localStorage.getItem(LS_TOGGLE) === 'true';
        const raw = localStorage.getItem(LS_AUTH);
        if (raw) authCache = JSON.parse(raw);
    } catch (_) { /* localStorage erişilemez */ }
}

function persistToggle() {
    try { localStorage.setItem(LS_TOGGLE, sahtelikAnalizi); } catch (_) {}
}

function persistAuthCache() {
    try {
        // Önbelleği 200 giriş ile sınırla (eski girişleri at)
        const keys = Object.keys(authCache);
        if (keys.length > 200) {
            const trimmed = {};
            keys.slice(-200).forEach(k => { trimmed[k] = authCache[k]; });
            authCache = trimmed;
        }
        localStorage.setItem(LS_AUTH, JSON.stringify(authCache));
    } catch (_) {}
}

// ── DOM Render ─────────────────────────────────────────────
function renderApp() {
    const app = document.getElementById('app');
    app.innerHTML = `
    <div class="dashboard">
        <!-- Header -->
        <div class="header">
            <div class="logo">
                <div class="logo-icon">
                    <svg width="44" height="44" viewBox="0 0 44 44" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <defs>
                            <linearGradient id="sg" x1="0%" y1="0%" x2="100%" y2="100%">
                                <stop offset="0%" stop-color="#38bdf8"/>
                                <stop offset="100%" stop-color="#ef4444"/>
                            </linearGradient>
                            <filter id="gw" x="-30%" y="-30%" width="160%" height="160%">
                                <feGaussianBlur stdDeviation="1.8" result="b"/>
                                <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
                            </filter>
                        </defs>
                        <!-- Shield -->
                        <path d="M22 3L37 9.5V21C37 31 22 41 22 41C22 41 7 31 7 21V9.5Z"
                              fill="url(#sg)" fill-opacity="0.12"
                              stroke="url(#sg)" stroke-width="1.4" filter="url(#gw)"/>
                        <!-- Pulse line -->
                        <polyline points="10,22 14,22 16.5,14 19,30 21,17.5 23,26 25.5,22 34,22"
                                  stroke="#38bdf8" stroke-width="2.2" fill="none"
                                  stroke-linecap="round" stroke-linejoin="round" filter="url(#gw)"/>
                        <!-- Alert dot -->
                        <circle cx="34" cy="22" r="2.5" fill="#ef4444" filter="url(#gw)"/>
                    </svg>
                </div>
                <div class="logo-text">
                    <span class="logo-title">AFETİZ</span>
                    <span class="logo-sub">KRİZ İZLEME PLATFORMU</span>
                </div>
            </div>
            <div class="header-right">
                <div class="rate-limit-badge" id="rateLimitBadge" title="Gemini API Rate Limit">
                    <i class="fas fa-gauge-high"></i>
                    <span id="rateLimitText">RPM: 15/15 · RPD: 500/500</span>
                </div>
                <div class="live-badge">
                    <div class="pulse-dot"></div>
                    <span>GERÇEK ZAMANLI AKIŞ</span>
                </div>
            </div>
        </div>

        <!-- Toolbar -->
        <div class="toolbar">
            <button class="btn btn--primary" id="btnRefresh" title="Tweet'leri yenile">
                <i class="fas fa-sync-alt"></i> Yenile
            </button>
            <button class="btn" id="btnAnalyzeAll" title="Tüm tweet'leri analiz et">
                <i class="fas fa-brain"></i> Tümünü Analiz Et
            </button>
            <div class="toolbar-separator"></div>
            <div class="authenticity-toggle-wrap" title="Açıkken her analiz AFAD deprem verisiyle doğrulanır">
                <label class="toggle-switch">
                    <input type="checkbox" id="toggleAuthenticity">
                    <span class="toggle-slider"></span>
                </label>
                <span class="toggle-label" id="authenticityLabel">
                    <i class="fas fa-shield-halved"></i> Sahtelik Analizi
                    <span class="toggle-state-badge" id="toggleStateBadge">KAPALI</span>
                </span>
            </div>
            <div class="toolbar-separator"></div>
            <button class="btn btn--trusted" id="btnTrustedAccounts" title="Güvenilir hesapları yönet">
                <i class="fas fa-shield-halved"></i> Güvenilir Hesaplar
            </button>
            <div class="toolbar-spacer"></div>
            <button class="btn btn--export" id="btnExportExcel" title="Verileri Excel olarak indir">
                <i class="fas fa-file-excel"></i> Excel
            </button>
            <button class="btn btn--export btn--export-pdf" id="btnExportPDF" title="Harita, grafikler ve AI analizi ile PDF raporu oluştur">
                <i class="fas fa-file-pdf"></i> PDF Raporu
            </button>
            <button class="btn btn--telegram" id="btnSendTelegram" title="CSV raporunu Afetiz Telegram kanalına gönder">
                <i class="fab fa-telegram"></i> Telegram
            </button>
        </div>

        <!-- Ana Alan: Harita + Sağ Panel -->
        <div class="main-grid">
            <div class="map-wrapper">
                <div id="map"></div>
                <div class="map-caption"><i class="fas fa-fire"></i> Isı Haritası (Tweet Yoğunluğu)</div>
                <div class="map-legend">
                    <div class="legend-item"><div class="legend-dot" style="background:${PRIORITY_COLORS.critical}"></div> Çok Acil</div>
                    <div class="legend-item"><div class="legend-dot" style="background:${PRIORITY_COLORS.high}"></div> Acil</div>
                    <div class="legend-item"><div class="legend-dot" style="background:${PRIORITY_COLORS.medium}"></div> Orta</div>
                    <div class="legend-item"><div class="legend-dot" style="background:${PRIORITY_COLORS.low}"></div> Düşük</div>
                </div>
            </div>
            <div class="right-panel">
                <div class="kpi-container">
                    <div class="kpi-card" id="kpiTotal">
                        <div class="kpi-title"><i class="fas fa-database"></i> TOPLAM ANALİZ</div>
                        <div class="kpi-number" id="kpiTotalNum">0</div>
                    </div>
                    <div class="kpi-card critical" id="kpiCritical">
                        <div class="kpi-title"><i class="fas fa-exclamation-triangle"></i> KRİTİK</div>
                        <div class="kpi-number" id="kpiCriticalNum">0</div>
                    </div>
                    <div class="kpi-card" id="kpiCache">
                        <div class="kpi-title"><i class="fab fa-twitter"></i> CACHE TWEET</div>
                        <div class="kpi-number" id="kpiCacheNum">0</div>
                    </div>
                    <div class="kpi-card" id="kpiCities">
                        <div class="kpi-title"><i class="fas fa-map-pin"></i> ETKİLENEN İL</div>
                        <div class="kpi-number" id="kpiCitiesNum">0</div>
                    </div>
                </div>
                <div class="tweet-feed">
                    <div class="feed-header">
                        <div class="feed-title"><i class="fab fa-twitter" style="color:#1DA1F2;"></i> Son Analizler</div>
                        <span class="feed-count" id="feedCount">0 sonuç</span>
                    </div>
                    <div id="tweetFeedList">
                        <div class="skeleton" style="height:60px;margin-bottom:10px;"></div>
                        <div class="skeleton" style="height:60px;margin-bottom:10px;"></div>
                        <div class="skeleton" style="height:60px;"></div>
                    </div>
                </div>
            </div>
        </div>

        <!-- D3 Grafikler -->
        <div class="charts-section">
            <div class="charts-title"><i class="fas fa-chart-simple"></i> ANALİTİK GÖRSELLER</div>
            <div class="charts-grid">
                <div class="chart-card">
                    <h3><i class="fas fa-chart-pie"></i> İhtiyaç Türü Dağılımı</h3>
                    <div id="need-type-chart" class="chart-container"></div>
                </div>
                <div class="chart-card">
                    <h3><i class="fas fa-city"></i> İl Bazlı Tweet Yoğunluğu</h3>
                    <div id="city-bar-chart" class="chart-container"></div>
                </div>
                <div class="chart-card">
                    <h3><i class="fas fa-gauge-high"></i> Aciliyet Dağılımı</h3>
                    <div id="urgency-chart" class="chart-container"></div>
                </div>
            </div>
        </div>
    </div>

    <div class="toast-container" id="toastContainer"></div>

    <!-- PDF İşlem Overlay -->
    <div class="export-overlay hidden" id="exportOverlay">
        <div class="export-spinner-box">
            <div class="export-spinner"></div>
            <div class="export-progress-text" id="exportProgressText">Hazırlanıyor...</div>
        </div>
    </div>

    <!-- Güvenilir Hesaplar Modalı -->
    <div class="modal-overlay hidden" id="trustedModal">
        <div class="modal-panel">
            <div class="modal-header">
                <h3><i class="fas fa-shield-halved"></i> Güvenilir Hesaplar</h3>
                <button class="modal-close" id="btnCloseTrusted" aria-label="Kapat">×</button>
            </div>
            <div class="modal-body">
                <p class="modal-hint">Eklediğin hesaplar profil analizi yapılmadan direkt <strong>%100 güvenilir</strong> kabul edilir. Sunum için ideal.</p>
                <div class="trusted-add-row">
                    <input type="text" class="tweet-input" id="trustedUsernameInput" placeholder="kullanıcı_adı (@ olmadan)">
                    <input type="text" class="tweet-input trusted-note-input" id="trustedNoteInput" placeholder="Not (opsiyonel)">
                    <button class="btn btn--primary" id="btnAddTrusted">
                        <i class="fas fa-plus"></i> Ekle
                    </button>
                </div>
                <div id="trustedList" class="trusted-list">
                    <div class="trusted-empty">Henüz güvenilir hesap eklenmedi.</div>
                </div>
            </div>
        </div>
    </div>
    `;
}

// ── KPI Güncelle ───────────────────────────────────────────
function updateKPIs() {
    const valid = analyzedTweets.filter(t => t.analysis);
    const critical = valid.filter(t => t.analysis.map_priority === 'critical').length;
    const cities = new Set(valid.map(t => t.analysis.city)).size;

    setText('kpiTotalNum', valid.length);
    setText('kpiCriticalNum', critical);
    setText('kpiCacheNum', rawTweets.length);
    setText('kpiCitiesNum', cities);
    setText('feedCount', `${valid.length} sonuç`);
}

// ── Tweet Feed Güncelle ────────────────────────────────────
function updateTweetFeed() {
    const container = document.getElementById('tweetFeedList');
    if (!container) return;

    const valid = analyzedTweets.filter(t => t.analysis);

    if (valid.length === 0) {
        container.innerHTML = '<div style="color:#94a3b8;font-size:0.8rem;text-align:center;padding:1.5rem;">Henüz analiz sonucu yok. Bir tweet gönderin veya "Tümünü Analiz Et" butonuna basın.</div>';
        return;
    }

    container.innerHTML = valid
        .slice()
        .sort((a, b) => {
            const dateA = a.analyzed_at || '';
            const dateB = b.analyzed_at || '';
            if (dateA !== dateB) return dateB.localeCompare(dateA);
            const idA = BigInt(a.tweet_id || '0');
            const idB = BigInt(b.tweet_id || '0');
            return idB > idA ? 1 : idB < idA ? -1 : 0;
        })
        .reverse() // Kullanıcı isteği: Sıralanmış listeyi tersine çevir
        .slice(0, 15)
        .map(tweet => {
        const a = tweet.analysis;
        const priority = a.map_priority || 'medium';

        // Kullanıcı adı ve avatar
        const username = tweet.author?.username || 'afetiz_bildirim';
        const isTrusted = tweet.author?.is_trusted === true;
        const initials = (tweet.author?.username ? tweet.author.username.slice(0, 2) : 'AI').toUpperCase();
        // Avatar rengi — kullanıcı adına göre deterministik
        const avatarColors = ['#3b82f6', '#8b5cf6', '#ec4899', '#f97316', '#10b981', '#06b6d4'];
        let ci = 0;
        for (let i = 0; i < username.length; i++) ci += username.charCodeAt(i);
        const avatarColor = avatarColors[ci % avatarColors.length];

        // Konum
        const location = a.district ? `${a.city} / ${a.district}` : a.city;

        // Aciliyet etiketi
        const urgencyLabel = getUrgencyLabel(a.urgency_score);

        // Sahtelik durumu — sadece analiz edilmişse göster, tek satır
        let statusLine = '';
        if (tweet.authenticity) {
            const auth = tweet.authenticity;
            if (auth.is_authentic === true) {
                statusLine = `<span class="tc-status tc-real"><i class="fas fa-circle-check"></i> Doğrulandı</span>`;
            } else if (auth.is_authentic === false) {
                statusLine = `<span class="tc-status tc-fake"><i class="fas fa-triangle-exclamation"></i> Şüpheli</span>`;
            }
        }

        // Güven skoru badge
        let trustBadge = '';
        if (tweet.trust_score && typeof tweet.trust_score.score === 'number') {
            const ts = tweet.trust_score;
            const s = Math.round(ts.score);
            const trustClass = s >= 70 ? 'trust-high' : s >= 40 ? 'trust-mid' : 'trust-low';
            const userComp   = Math.round(ts.user_score * 0.4);
            const afadComp   = Math.round(ts.afad_boost);
            const clusterComp = Math.round(ts.cluster_boost);
            const tooltipRows = [
                `<div class="tc-tt-row"><span>Kullanıcı profili</span><span>+${userComp}</span></div>`,
                afadComp   > 0 ? `<div class="tc-tt-row tc-tt-accent"><span>AFAD eşleşmesi</span><span>+${afadComp}</span></div>` : '',
                clusterComp > 0 ? `<div class="tc-tt-row"><span>Bölge kümesi</span><span>+${clusterComp}</span></div>` : '',
                `<div class="tc-tt-sep"></div>`,
                `<div class="tc-tt-row tc-tt-total"><span>Toplam</span><span>${s}/100</span></div>`,
            ].join('');
            trustBadge = `
            <div class="tc-trust ${trustClass}">
                <div class="tc-trust-label"><i class="fas fa-shield-halved"></i> ${s}</div>
                <div class="tc-trust-tooltip">
                    <div class="tc-tt-title">Güvenilirlik Skoru</div>
                    ${tooltipRows}
                    ${ts.explanation ? `<div class="tc-tt-note">${escapeHtml(ts.explanation)}</div>` : ''}
                </div>
            </div>`;
        }

        // İhtiyaç etiketleri — sadece kritik/acil için
        let needRow = '';
        if ((priority === 'critical' || priority === 'high') && (a.need_types || []).length > 0) {
            const tags = (a.need_types || [])
                .slice(0, 3)
                .map(n => `<span class="need-tag">${NEED_TYPE_LABELS[n] || n}</span>`)
                .join('');
            needRow = `<div class="need-tags">${tags}</div>`;
        }

        const isFake = sahtelikAnalizi && tweet.authenticity?.is_authentic === false;

        return `
        <div class="tweet-card ${priority}${isFake ? ' tweet-fake' : ''}">
            <div class="tc-header">
                <div class="tc-avatar" style="background:${avatarColor};">${initials}</div>
                <div class="tc-user">
                    <span class="tc-username">@${escapeHtml(username)}</span>
                    ${isTrusted ? '<span class="tc-verified" title="Güvenilir Hesap"><i class="fas fa-circle-check"></i></span>' : ''}
                    <span class="tc-location"><i class="fas fa-location-dot"></i> ${escapeHtml(location)}</span>
                </div>
                <div class="tc-header-right">
                    ${trustBadge}
                    <span class="urgency-badge ${priority}">${urgencyLabel}</span>
                </div>
            </div>
            <div class="tc-body">${escapeHtml(tweet.text)}</div>
            ${statusLine || needRow ? `<div class="tc-footer">${statusLine}${needRow}</div>` : ''}
        </div>`;
    }).join('');
}

// ── Güvenilir Hesaplar ─────────────────────────────────────
async function loadTrustedAccounts() {
    try {
        const data = await fetchTrustedAccounts();
        trustedAccounts = data.accounts || [];
        renderTrustedList();
    } catch (e) {
        console.warn('Güvenilir hesaplar yüklenemedi:', e.message);
    }
}

function renderTrustedList() {
    const container = document.getElementById('trustedList');
    if (!container) return;

    if (trustedAccounts.length === 0) {
        container.innerHTML = '<div class="trusted-empty">Henüz güvenilir hesap eklenmedi.</div>';
        return;
    }

    container.innerHTML = trustedAccounts.map(acc => `
        <div class="trusted-item">
            <div class="trusted-item-info">
                <i class="fas fa-shield-check" style="color:#22c55e;"></i>
                <strong>@${escapeHtml(acc.username)}</strong>
                ${acc.note ? `<span class="trusted-note">${escapeHtml(acc.note)}</span>` : ''}
            </div>
            <button class="btn btn--danger-sm" data-username="${escapeHtml(acc.username)}" title="Listeden çıkar">
                <i class="fas fa-trash"></i>
            </button>
        </div>
    `).join('');

    // Silme butonlarına listener ekle
    container.querySelectorAll('[data-username]').forEach(btn => {
        btn.addEventListener('click', async () => {
            const username = btn.dataset.username;
            try {
                await removeTrustedAccount(username);
                trustedAccounts = trustedAccounts.filter(a => a.username !== username);
                renderTrustedList();
                showToast(`@${username} güvenilir listesinden çıkarıldı`, 'info');
                await loadResults(); // Trust score'ları yenile
            } catch (e) {
                showToast(e.message, 'error');
            }
        });
    });
}

// ── Rate Limit Güncelle ────────────────────────────────────
function updateRateLimitBadge() {
    const badge = document.getElementById('rateLimitBadge');
    const text = document.getElementById('rateLimitText');
    if (!badge || !text) return;

    text.textContent = `RPM: ${rateLimit.remaining_rpm}/${rateLimit.max_rpm} · RPD: ${rateLimit.remaining_rpd}/${rateLimit.max_rpd}`;

    badge.classList.remove('warning', 'danger');
    if (rateLimit.remaining_rpd < 50 || rateLimit.remaining_rpm < 3) {
        badge.classList.add('danger');
    } else if (rateLimit.remaining_rpd < 150 || rateLimit.remaining_rpm < 8) {
        badge.classList.add('warning');
    }
}

// ── Veri Çekme ─────────────────────────────────────────────
async function loadResults() {
    try {
        const data = await fetchResults();
        // Backend authenticity döndürmez — cache'den merge et
        analyzedTweets = (data.tweets || []).map(t => ({
            ...t,
            authenticity: t.authenticity ?? authCache[t.tweet_id] ?? null,
        }));
        updateAll();
    } catch (e) {
        console.warn('Sonuçlar yüklenemedi:', e.message);
    }
}

async function loadTweets() {
    try {
        const data = await fetchTweets();
        rawTweets = data.tweets || [];
        updateKPIs();
    } catch (e) {
        console.warn('Tweet\'ler yüklenemedi:', e.message);
    }
}

async function loadRateLimit() {
    try {
        rateLimit = await fetchRateLimit();
        updateRateLimitBadge();
    } catch (e) {
        console.warn('Rate limit alınamadı:', e.message);
    }
}

function updateAll() {
    updateKPIs();
    updateTweetFeed();
    const withAnalysis = analyzedTweets.filter(t => t.analysis);
    updateMapWithResults(withAnalysis);
    updateCellTowersFromCities(withAnalysis);
    updateCharts(analyzedTweets);
}

// ── Event Handlers ─────────────────────────────────────────
function setupEventHandlers() {
    // Refresh
    document.getElementById('btnRefresh')?.addEventListener('click', async () => {
        const btn = document.getElementById('btnRefresh');
        setButtonLoading(btn, true);
        try {
            // 1) Twitter'dan yeni tweet'leri cache'e çek
            await refreshTweets();
            // 2) Cache'teki tüm tweet'leri analiz et (yeni + eskiler)
            await analyzeAll();
            // 3) DB'den güncel analiz sonuçlarını çek ve UI'ı güncelle
            await Promise.all([loadResults(), loadTweets(), loadRateLimit()]);
            showToast('Tweet\'ler yenilendi ve analiz edildi', 'success');
        } catch (e) {
            showToast(e.message, 'error');
        }
        setButtonLoading(btn, false);
    });

    // Analyze All
    document.getElementById('btnAnalyzeAll')?.addEventListener('click', async () => {
        const btn = document.getElementById('btnAnalyzeAll');
        setButtonLoading(btn, true);
        try {
            const res = await fetch('http://localhost:8000/analyze-all', { method: 'POST' });
            if (!res.ok) {
                const body = await res.json().catch(() => ({}));
                throw new Error(body.detail || 'Analiz hatası');
            }
            const data = await res.json();
            showToast(`${data.analyzed}/${data.total} tweet analiz edildi`, 'success');
            await loadResults();
            await loadRateLimit();
        } catch (e) {
            showToast(e.message, 'error');
        }
        setButtonLoading(btn, false);
    });

    // Sahtelik Analizi Toggle
    const toggleEl = document.getElementById('toggleAuthenticity');
    const badgeEl = document.getElementById('toggleStateBadge');
    toggleEl?.addEventListener('change', () => {
        sahtelikAnalizi = toggleEl.checked;
        persistToggle();
        if (badgeEl) {
            badgeEl.textContent = sahtelikAnalizi ? 'A\u00c7IK' : 'KAPALI';
            badgeEl.className = `toggle-state-badge${sahtelikAnalizi ? ' active' : ''}`;
        }
        showToast(
            sahtelikAnalizi
                ? 'Sahtelik Analizi a\u00e7\u0131ld\u0131 \u2014 her analiz AFAD verisiyle do\u011frulanacak'
                : 'Sahtelik Analizi kapat\u0131ld\u0131',
            'info'
        );
    });

    // Güvenilir Hesaplar Modal
    document.getElementById('btnTrustedAccounts')?.addEventListener('click', () => {
        document.getElementById('trustedModal')?.classList.remove('hidden');
        loadTrustedAccounts();
    });

    document.getElementById('btnCloseTrusted')?.addEventListener('click', () => {
        document.getElementById('trustedModal')?.classList.add('hidden');
    });

    document.getElementById('trustedModal')?.addEventListener('click', (e) => {
        if (e.target.id === 'trustedModal') {
            document.getElementById('trustedModal')?.classList.add('hidden');
        }
    });

    document.getElementById('btnAddTrusted')?.addEventListener('click', async () => {
        const usernameInput = document.getElementById('trustedUsernameInput');
        const noteInput = document.getElementById('trustedNoteInput');
        const username = usernameInput?.value?.trim().replace(/^@/, '');
        if (!username) { showToast('Kullanıcı adı girin', 'error'); return; }

        const btn = document.getElementById('btnAddTrusted');
        setButtonLoading(btn, true);
        try {
            await addTrustedAccount(username, noteInput?.value?.trim() || '');
            if (usernameInput) usernameInput.value = '';
            if (noteInput) noteInput.value = '';
            await loadTrustedAccounts();
            showToast(`@${username} güvenilir listeye eklendi`, 'success');
            await loadResults(); // Trust score'ları yenile
        } catch (e) {
            showToast(e.message, 'error');
        }
        setButtonLoading(btn, false);
    });

    document.getElementById('trustedUsernameInput')?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') document.getElementById('btnAddTrusted')?.click();
    });

    // Excel Dışa Aktar
    document.getElementById('btnExportExcel')?.addEventListener('click', async () => {
        const btn = document.getElementById('btnExportExcel');
        setButtonLoading(btn, true);
        try {
            await exportToExcel(analyzedTweets);
            showToast('Excel dosyası indirildi', 'success');
        } catch (e) {
            showToast(`Excel hatası: ${e.message}`, 'error');
        }
        setButtonLoading(btn, false);
    });

    // PDF Raporu Dışa Aktar
    document.getElementById('btnExportPDF')?.addEventListener('click', async () => {
        const btn = document.getElementById('btnExportPDF');
        const overlay = document.getElementById('exportOverlay');
        const progressText = document.getElementById('exportProgressText');
        setButtonLoading(btn, true);
        overlay?.classList.remove('hidden');
        try {
            await exportToPDF(analyzedTweets, getCellTowerSnapshot(), (msg) => {
                if (progressText) progressText.textContent = msg || 'Tamamlandı...';
            });
            showToast('PDF raporu indirildi', 'success');
        } catch (e) {
            showToast(`PDF hatası: ${e.message}`, 'error');
        }
        overlay?.classList.add('hidden');
        setButtonLoading(btn, false);
    });

    // Telegram Rapor Gönder
    document.getElementById('btnSendTelegram')?.addEventListener('click', async () => {
        const btn = document.getElementById('btnSendTelegram');
        setButtonLoading(btn, true);
        try {
            const res = await fetch(`${API_BASE}/telegram/send-report`, { method: 'POST' });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Gönderim başarısız');
            showToast(`Telegram'a gönderildi: ${data.message}`, 'success');
        } catch (e) {
            showToast(`Telegram hatası: ${e.message}`, 'error');
        }
        setButtonLoading(btn, false);
    });
}

// ── Polling ────────────────────────────────────────────────
function startPolling() {
    // Her 5 saniyede bir sonuçları ve rate limit'i güncelle
    pollTimer = setInterval(async () => {
        await loadResults();
        await loadRateLimit();
    }, 5000);
}

// ── Yardımcılar ────────────────────────────────────────────
function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function escapeHtml(str) {
    return str.replace(/[&<>]/g, m => {
        if (m === '&') return '&amp;';
        if (m === '<') return '&lt;';
        if (m === '>') return '&gt;';
        return m;
    });
}

function getUrgencyLabel(score) {
    const labels = { 1: 'Bilgi', 2: 'Düşük', 3: 'Orta', 4: 'Acil', 5: 'Çok Acil' };
    return labels[score] || 'Bilinmiyor';
}

function setButtonLoading(btn, loading) {
    if (!btn) return;
    btn.disabled = loading;
    if (loading) {
        btn.dataset.originalHtml = btn.innerHTML;
        const text = btn.textContent.trim();
        btn.innerHTML = `<span class="spinner"></span> ${text}`;
    } else {
        btn.innerHTML = btn.dataset.originalHtml || btn.innerHTML;
    }
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const icon = type === 'success' ? 'fa-check-circle' : type === 'error' ? 'fa-exclamation-circle' : 'fa-info-circle';
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<i class="fas ${icon}"></i> ${escapeHtml(message)}`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(10px)';
        toast.style.transition = '0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3500);
}

// ── Toggle UI'ı kayıtlı state'e göre ayarla ──────────────
function restoreToggleUI() {
    const toggleEl = document.getElementById('toggleAuthenticity');
    const badgeEl = document.getElementById('toggleStateBadge');
    if (toggleEl) toggleEl.checked = sahtelikAnalizi;
    if (badgeEl) {
        badgeEl.textContent = sahtelikAnalizi ? 'A\u00c7IK' : 'KAPALI';
        badgeEl.className = `toggle-state-badge${sahtelikAnalizi ? ' active' : ''}`;
    }
}

// ── Başlat ─────────────────────────────────────────────────
async function init() {
    loadPersistedState();   // localStorage'dan state'i yükle
    renderApp();
    initMap();
    initCellTowerLayer();
    await initCharts();
    setupEventHandlers();
    restoreToggleUI();      // Checkbox'ı kayıtlı state'e ayarla

    // İlk veri yükleme
    await Promise.all([loadResults(), loadTweets(), loadRateLimit(), loadTrustedAccounts()]);

    // Polling başlat
    startPolling();
}

init();