/**
 * AfetİZ — Ana Uygulama
 *
 * Backend API'ye bağlanır, harita + grafikler + tweet feed günceller.
 * Fake-realtime polling (5sn) + manuel refresh + mock tweet desteği.
 */

import './style.css';
import { fetchTweets, refreshTweets, fetchResults, fetchRateLimit, addMockTweet, analyzeTweet, fetchEarthquakes, fetchTrustedAccounts, addTrustedAccount, removeTrustedAccount, fetchRegionRisk, analyzeAll } from './api.js';
import { initMap, updateMapWithResults, NEED_TYPE_LABELS, PRIORITY_COLORS } from './map.js';
import { initCharts, updateCharts } from './charts.js';
import { exportToExcel, exportToPDF } from './export.js';

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
                <i class="fas fa-chart-line"></i>
                <h1>AFETİZ</h1>
                <span class="header-badge">KRİZ İZLEME</span>
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
            <div class="tweet-input-group">
                <input type="text" class="tweet-input" id="mockTweetInput"
                    placeholder="Demo tweet yaz... (ör: Antakya'da enkaz altında yaralılar var, acil yardım)">
                <button class="btn btn--primary" id="btnMockTweet" title="Demo tweet ekle ve analiz et">
                    <i class="fas fa-paper-plane"></i> Gönder
                </button>
            </div>
            <div class="toolbar-separator"></div>
            <button class="btn btn--trusted" id="btnTrustedAccounts" title="Güvenilir hesapları yönet">
                <i class="fas fa-shield-halved"></i> Güvenilir Hesaplar
            </button>
            <div class="toolbar-separator"></div>
            <button class="btn btn--export" id="btnExportExcel" title="Verileri Excel olarak indir">
                <i class="fas fa-file-excel"></i> Excel
            </button>
            <button class="btn btn--export btn--export-pdf" id="btnExportPDF" title="Harita, grafikler ve AI analizi ile PDF raporu oluştur">
                <i class="fas fa-file-pdf"></i> PDF Raporu
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
        // En yeni önce: analyzed_at yoksa tweet_id'ye göre sırala
        .slice()
        .sort((a, b) => {
            const ta = a.analyzed_at || a.tweet_id || '';
            const tb = b.analyzed_at || b.tweet_id || '';
            return tb.localeCompare(ta);
        })
        .slice(0, 15)
        .map(tweet => {
        const a = tweet.analysis;
        const priority = a.map_priority || 'medium';
        const needTags = (a.need_types || [])
            .map(n => `<span class="need-tag">${NEED_TYPE_LABELS[n] || n}</span>`)
            .join('');

        // Sahtelik analizi badge
        let authenticityBadge = '';
        if (tweet.authenticity) {
            const auth = tweet.authenticity;
            if (auth.is_authentic === true) {
                authenticityBadge = `<span class="auth-badge auth-real" title="${escapeHtml(auth.explanation)}"><i class="fas fa-check-circle"></i> Gerçek</span>`;
            } else if (auth.is_authentic === false) {
                authenticityBadge = `<span class="auth-badge auth-fake" title="${escapeHtml(auth.explanation)}"><i class="fas fa-exclamation-triangle"></i> Şüpheli</span>`;
            } else {
                authenticityBadge = `<span class="auth-badge auth-unknown" title="${escapeHtml(auth.explanation)}"><i class="fas fa-question-circle"></i> Doğrulanamadı</span>`;
            }
        }

        // Güven skoru badge
        let trustBadge = '';
        if (tweet.trust_score) {
            const ts = tweet.trust_score;
            const lvl = ts.score >= 70 ? 'trust-high' : ts.score >= 40 ? 'trust-mid' : 'trust-low';
            trustBadge = `<span class="trust-badge ${lvl}" title="${escapeHtml(ts.explanation)}"><i class="fas fa-percent"></i> ${ts.score} güven</span>`;
        }

        // Kesin konum badge (sokak/bina seviyesi)
        // TODO: Bu badge'e tıklanınca 3D bina modellemesi açılacak (gelecek sprint)
        let preciseBadge = '';
        if (a.has_precise_location) {
            const addr = a.street_address ? ` — ${a.street_address}` : '';
            preciseBadge = `<span class="precise-location-badge" title="Kesin konum mevcut${escapeHtml(addr)} · TODO: 3D modelleme">
                <i class="fas fa-location-crosshairs"></i> Kesin Konum${addr ? ': ' + escapeHtml(a.street_address) : ''}
            </span>`;
        }

        // Yazar badge (varsa)
        let authorBadge = '';
        if (tweet.author?.username) {
            const isTr = tweet.author.is_trusted;
            const followers = tweet.author.followers > 1000
                ? `${(tweet.author.followers / 1000).toFixed(1)}K`
                : String(tweet.author.followers);
            const ageYears = (tweet.author.account_age_days / 365).toFixed(1);
            const tooltip = isTr
                ? 'Güvenilir Hesap'
                : `Hesap yaşı: ${ageYears} yıl | Takipçi: ${followers}`;
            authorBadge = `<span class="author-badge${isTr ? ' trusted' : ''}" title="${escapeHtml(tooltip)}">
                ${isTr ? '<i class="fas fa-shield-check"></i>' : '<i class="fab fa-twitter"></i>'}
                @${escapeHtml(tweet.author.username)}${isTr ? ' <i class="fas fa-star" style="font-size:0.6rem;color:#fbbf24;"></i>' : ''}
            </span>`;
        }

        const isFake = sahtelikAnalizi && tweet.authenticity?.is_authentic === false;

        return `
        <div class="tweet-item ${priority}${isFake ? ' tweet-fake' : ''}">
            <div class="tweet-text"><i class="fab fa-twitter" style="color:#1DA1F2;margin-right:4px;"></i>${escapeHtml(tweet.text)}</div>
            <div class="tweet-meta">
                <span><i class="fas fa-map-marker-alt"></i> ${a.city}${a.district ? ' / ' + a.district : ''}</span>
                <span class="urgency-badge ${priority}">${getUrgencyLabel(a.urgency_score)}</span>
                ${authenticityBadge}
                ${trustBadge}
                ${preciseBadge}
                ${authorBadge}
            </div>
            ${needTags ? `<div class="need-tags">${needTags}</div>` : ''}
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
    updateMapWithResults(analyzedTweets.filter(t => t.analysis));
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

    // Mock Tweet
    const mockInput = document.getElementById('mockTweetInput');
    const btnMock = document.getElementById('btnMockTweet');

    async function sendMockTweet() {
        const text = mockInput?.value?.trim();
        if (!text) return;

        setButtonLoading(btnMock, true);
        try {
            const result = await addMockTweet(text, sahtelikAnalizi);
            // Authenticity'i cache'e kaydet
            if (result.authenticity && result.tweet_id) {
                authCache[result.tweet_id] = result.authenticity;
                persistAuthCache();
            }
            analyzedTweets.unshift(result);
            mockInput.value = '';
            updateAll();
            await loadRateLimit();
            const authMsg = result.authenticity
                ? (result.authenticity.is_authentic === true ? ' \u2714 Ger\u00e7ek deprem do\u011fruland\u0131' :
                   result.authenticity.is_authentic === false ? ' \u26a0 \u015e\u00fcpheli tweet' : '')
                : '';
            showToast(`Tweet analiz edildi!${authMsg}`, 'success');
        } catch (e) {
            showToast(e.message, 'error');
        }
        setButtonLoading(btnMock, false);
    }

    btnMock?.addEventListener('click', sendMockTweet);
    mockInput?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') sendMockTweet();
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
            await exportToPDF(analyzedTweets, (msg) => {
                if (progressText) progressText.textContent = msg || 'Tamamlandı...';
            });
            showToast('PDF raporu indirildi', 'success');
        } catch (e) {
            showToast(`PDF hatası: ${e.message}`, 'error');
        }
        overlay?.classList.add('hidden');
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
    await initCharts();
    setupEventHandlers();
    restoreToggleUI();      // Checkbox'ı kayıtlı state'e ayarla

    // İlk veri yükleme
    await Promise.all([loadResults(), loadTweets(), loadRateLimit(), loadTrustedAccounts()]);

    // Polling başlat
    startPolling();
}

init();