/**
 * AfetİZ — Dışa Aktarma Modülü
 *
 * Excel (SheetJS) ve PDF (jsPDF + html2canvas) dışa aktarımı
 */

const API_BASE = 'http://localhost:8000';

// ── Türkçe karakterleri PDF için normalize et ─────────────
function normTR(str) {
    if (!str) return '';
    return String(str)
        .replace(/ş/g, 's').replace(/Ş/g, 'S')
        .replace(/ğ/g, 'g').replace(/Ğ/g, 'G')
        .replace(/ı/g, 'i').replace(/İ/g, 'I')
        .replace(/ö/g, 'o').replace(/Ö/g, 'O')
        .replace(/ü/g, 'u').replace(/Ü/g, 'U')
        .replace(/ç/g, 'c').replace(/Ç/g, 'C');
}

const NEED_LABELS = {
    arama_kurtarma: 'Arama Kurtarma',
    saglik: 'Saglik',
    su: 'Su',
    gida: 'Gida',
    barinma: 'Barinma',
    yol_kapali: 'Yol Kapali',
    yangin: 'Yangin',
    elektrik_iletisim: 'Elektrik/Iletisim',
};

const NEED_LABELS_TR = {
    arama_kurtarma: 'Arama Kurtarma',
    saglik: 'Sağlık',
    su: 'Su',
    gida: 'Gıda',
    barinma: 'Barınma',
    yol_kapali: 'Yol Kapalı',
    yangin: 'Yangın',
    elektrik_iletisim: 'Elektrik/İletişim',
};

const PRIORITY_LABELS_TR = { critical: 'Kritik', high: 'Yüksek', medium: 'Orta', low: 'Düşük' };

// ── CDN Yükleyiciler ───────────────────────────────────────
async function loadLib(globalKey, url) {
    if (window[globalKey]) return;
    await new Promise((resolve, reject) => {
        const s = document.createElement('script');
        s.src = url;
        s.onload = resolve;
        s.onerror = () => reject(new Error(`${url} yüklenemedi`));
        document.head.appendChild(s);
    });
}

async function loadXLSX() {
    await loadLib('XLSX', 'https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js');
    return window.XLSX;
}

async function loadJsPDF() {
    await loadLib('jspdf', 'https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js');
    return window.jspdf.jsPDF;
}

async function loadHtml2Canvas() {
    await loadLib('html2canvas', 'https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js');
    return window.html2canvas;
}

// ── İstatistik Hesapla ────────────────────────────────────
function buildStats(tweets) {
    const valid = tweets.filter(t => t.analysis);
    const cityMap = {};
    const needMap = {};
    let totalTrust = 0;
    let trustCount = 0;
    let trustedCount = 0;
    const criticalTweets = [];

    valid.forEach(t => {
        const a = t.analysis;
        const city = a.city || 'Bilinmiyor';
        if (!cityMap[city]) cityMap[city] = { count: 0, needs: {}, maxUrgency: 0 };
        cityMap[city].count++;
        cityMap[city].maxUrgency = Math.max(cityMap[city].maxUrgency, a.urgency_score || 0);
        (a.need_types || []).forEach(n => {
            cityMap[city].needs[n] = (cityMap[city].needs[n] || 0) + 1;
            needMap[n] = (needMap[n] || 0) + 1;
        });

        if (t.trust_score) {
            totalTrust += t.trust_score.score || 0;
            trustCount++;
            if (t.trust_score.score >= 70) trustedCount++;
        }

        if (['critical', 'high'].includes(a.map_priority)) {
            criticalTweets.push({
                text: (t.text || '').slice(0, 140),
                city: a.city,
                district: a.district,
                neighborhood: a.neighborhood,
                street_address: a.street_address,
                has_precise_location: a.has_precise_location,
                need_types: a.need_types,
                urgency_score: a.urgency_score,
                summary: a.summary,
                map_priority: a.map_priority,
            });
        }
    });

    const cityBreakdown = Object.entries(cityMap)
        .sort((a, b) => b[1].count - a[1].count)
        .map(([city, data]) => ({
            city,
            count: data.count,
            max_urgency: data.maxUrgency,
            top_needs: Object.entries(data.needs).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([n]) => n),
        }));

    return {
        total_analyzed: valid.length,
        critical_count: valid.filter(t => t.analysis.map_priority === 'critical').length,
        high_count: valid.filter(t => t.analysis.map_priority === 'high').length,
        medium_count: valid.filter(t => t.analysis.map_priority === 'medium').length,
        low_count: valid.filter(t => t.analysis.map_priority === 'low').length,
        affected_cities: Object.keys(cityMap).length,
        analysis_date: new Date().toLocaleString('tr-TR'),
        city_breakdown: cityBreakdown,
        need_frequencies: needMap,
        top_critical_tweets: criticalTweets.slice(0, 12),
        trust_stats: {
            avg: trustCount > 0 ? Math.round(totalTrust / trustCount) : 0,
            total_trusted_sources: trustedCount,
        },
    };
}

// ══════════════════════════════════════════════════════════
// EXCEL DIŞA AKTARIM
// ══════════════════════════════════════════════════════════
export async function exportToExcel(analyzedTweets) {
    const XLSX = await loadXLSX();
    const valid = analyzedTweets.filter(t => t.analysis);

    if (valid.length === 0) {
        alert('Dışa aktarılacak analiz verisi yok. Önce tweet\'leri analiz edin.');
        return;
    }

    // ── Sayfa 1: Analiz Sonuçları ──
    const rows = valid.map(t => {
        const a = t.analysis;
        return {
            'Tweet ID': t.tweet_id || '',
            'Tweet Metni': t.text || '',
            'Yazar': t.author?.username ? `@${t.author.username}` : '',
            'İl': a.city || '',
            'İlçe': a.district || '',
            'Mahalle': a.neighborhood || '',
            'Sokak / Bina Adresi': a.street_address || '',
            'Kesin Konum': a.has_precise_location ? 'Evet' : 'Hayır',
            'İhtiyaç Türleri': (a.need_types || []).map(n => NEED_LABELS_TR[n] || n).join(', '),
            'Aciliyet Puanı (1-5)': a.urgency_score ?? '',
            'Öncelik': PRIORITY_LABELS_TR[a.map_priority] || a.map_priority || '',
            'Güven Skoru (%)': t.trust_score?.score ?? '',
            'Güven Açıklaması': t.trust_score?.explanation || '',
            'Özet': a.summary || '',
            'Sahtelik Durumu': t.authenticity
                ? (t.authenticity.is_authentic === true ? 'Gerçek'
                    : t.authenticity.is_authentic === false ? 'Şüpheli'
                    : 'Doğrulanamadı')
                : 'Kontrol Edilmedi',
            'Koordinat İl': a.city || '',
            'Koordinat İlçe': a.district || '',
        };
    });

    const wb = XLSX.utils.book_new();

    const wsAnaliz = XLSX.utils.json_to_sheet(rows);
    wsAnaliz['!cols'] = [
        { wch: 12 }, { wch: 70 }, { wch: 20 }, { wch: 15 }, { wch: 15 },
        { wch: 20 }, { wch: 40 }, { wch: 12 }, { wch: 40 }, { wch: 14 },
        { wch: 12 }, { wch: 14 }, { wch: 45 }, { wch: 55 }, { wch: 16 },
        { wch: 15 }, { wch: 15 },
    ];
    XLSX.utils.book_append_sheet(wb, wsAnaliz, 'Analiz Sonuçları');

    // ── Sayfa 2: İstatistikler ──
    const stats = buildStats(analyzedTweets);
    const cityMap = {};
    const needMap = {};
    valid.forEach(t => {
        const city = t.analysis.city || 'Bilinmiyor';
        cityMap[city] = (cityMap[city] || 0) + 1;
        (t.analysis.need_types || []).forEach(n => {
            needMap[n] = (needMap[n] || 0) + 1;
        });
    });

    const statsRows = [
        { 'Kategori': 'GENEL İSTATİSTİKLER', 'Değer': '' },
        { 'Kategori': 'Toplam Analiz', 'Değer': stats.total_analyzed },
        { 'Kategori': 'Kritik', 'Değer': stats.critical_count },
        { 'Kategori': 'Yüksek', 'Değer': stats.high_count },
        { 'Kategori': 'Orta', 'Değer': stats.medium_count },
        { 'Kategori': 'Düşük', 'Değer': stats.low_count },
        { 'Kategori': 'Etkilenen İl', 'Değer': stats.affected_cities },
        { 'Kategori': 'Ort. Güven Skoru (%)', 'Değer': stats.trust_stats.avg },
        { 'Kategori': '', 'Değer': '' },
        { 'Kategori': 'İL DAĞILIMI', 'Değer': 'Tweet Sayısı' },
        ...Object.entries(cityMap).sort((a, b) => b[1] - a[1]).map(([c, v]) => ({ 'Kategori': c, 'Değer': v })),
        { 'Kategori': '', 'Değer': '' },
        { 'Kategori': 'İHTİYAÇ DAĞILIMI', 'Değer': 'Tweet Sayısı' },
        ...Object.entries(needMap).sort((a, b) => b[1] - a[1]).map(([n, v]) => ({ 'Kategori': NEED_LABELS_TR[n] || n, 'Değer': v })),
        { 'Kategori': '', 'Değer': '' },
        { 'Kategori': 'KESİN ADRES OLAN NOKTALAR', 'Değer': '' },
        ...valid
            .filter(t => t.analysis.has_precise_location && t.analysis.street_address)
            .map(t => ({
                'Kategori': `${t.analysis.city} / ${t.analysis.district} — ${t.analysis.street_address}`,
                'Değer': `Aciliyet: ${t.analysis.urgency_score}/5`,
            })),
    ];

    const wsStats = XLSX.utils.json_to_sheet(statsRows);
    wsStats['!cols'] = [{ wch: 50 }, { wch: 20 }];
    XLSX.utils.book_append_sheet(wb, wsStats, 'İstatistikler');

    // ── Sayfa 3: Kesin Adresler (Yardım Noktaları) ──
    const preciseRows = valid
        .filter(t => t.analysis.has_precise_location)
        .sort((a, b) => (b.analysis.urgency_score || 0) - (a.analysis.urgency_score || 0))
        .map(t => ({
            'Tam Adres': [
                t.analysis.street_address,
                t.analysis.neighborhood,
                t.analysis.district,
                t.analysis.city,
            ].filter(Boolean).join(', '),
            'İl': t.analysis.city || '',
            'İlçe': t.analysis.district || '',
            'Mahalle': t.analysis.neighborhood || '',
            'Sokak / Bina': t.analysis.street_address || '',
            'İhtiyaç': (t.analysis.need_types || []).map(n => NEED_LABELS_TR[n] || n).join(', '),
            'Aciliyet (1-5)': t.analysis.urgency_score ?? '',
            'Öncelik': PRIORITY_LABELS_TR[t.analysis.map_priority] || '',
            'Özet': t.analysis.summary || '',
            'Tweet': (t.text || '').slice(0, 200),
        }));

    if (preciseRows.length > 0) {
        const wsAdr = XLSX.utils.json_to_sheet(preciseRows);
        wsAdr['!cols'] = [{ wch: 60 }, { wch: 15 }, { wch: 15 }, { wch: 20 }, { wch: 35 }, { wch: 40 }, { wch: 14 }, { wch: 12 }, { wch: 55 }, { wch: 80 }];
        XLSX.utils.book_append_sheet(wb, wsAdr, 'Kesin Adresler (Yardım)');
    }

    const now = new Date();
    const dateStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    XLSX.writeFile(wb, `afetiz_raporu_${dateStr}.xlsx`);
}

// ══════════════════════════════════════════════════════════
// PDF DIŞA AKTARIM
// ══════════════════════════════════════════════════════════
export async function exportToPDF(analyzedTweets, onProgress = () => { }) {
    const valid = analyzedTweets.filter(t => t.analysis);
    if (valid.length === 0) {
        alert('Dışa aktarılacak analiz verisi yok. Önce tweet\'leri analiz edin.');
        return;
    }

    const [JsPDF, html2canvas] = await Promise.all([loadJsPDF(), loadHtml2Canvas()]);

    // ── AI Raporu Çek ──
    onProgress('Yapay zeka analiz raporu hazırlanıyor...');
    let aiReport = null;
    try {
        const stats = buildStats(analyzedTweets);
        const res = await fetch(`${API_BASE}/export/pdf-analysis`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(stats),
        });
        if (res.ok) {
            const data = await res.json();
            aiReport = data.report || null;
        }
    } catch (e) {
        console.warn('AI raporu alınamadı:', e);
    }

    // ── Harita Screenshot ──
    onProgress('Harita görüntüsü alınıyor...');
    let mapCanvas = null;
    const mapEl = document.getElementById('map');
    if (mapEl) {
        try {
            mapCanvas = await html2canvas(mapEl, {
                useCORS: true,
                allowTaint: true,
                scale: 1.5,
                logging: false,
                backgroundColor: '#0f172a',
            });
        } catch (e) {
            console.warn('Harita screenshot alınamadı:', e);
        }
    }

    // ── Grafik Screenshottları ──
    onProgress('Grafik görselleri alınıyor...');
    const chartDefs = [
        { id: 'need-type-chart', title: 'Ihtiyac Turu Dagilimi' },
        { id: 'city-bar-chart', title: 'Il Bazli Tweet Yogunlugu' },
        { id: 'urgency-chart', title: 'Aciliyet Skoru Dagilimi' },
    ];
    const chartCanvases = [];
    for (const def of chartDefs) {
        const el = document.getElementById(def.id);
        if (el && el.children.length > 0) {
            try {
                const c = await html2canvas(el, {
                    backgroundColor: '#1e293b',
                    scale: 1.5,
                    logging: false,
                });
                chartCanvases.push({ ...def, canvas: c });
            } catch (e) {
                console.warn(`${def.id} screenshot alınamadı:`, e);
            }
        }
    }

    onProgress('PDF dosyası olusturuluyor...');

    // ── PDF Oluştur ──
    const doc = new JsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
    const pageW = doc.internal.pageSize.getWidth();
    const pageH = doc.internal.pageSize.getHeight();
    const margin = 14;
    const contentW = pageW - margin * 2;
    const stats = buildStats(analyzedTweets);

    // ── SAYFA 1: Kapak ──────────────────────────────────
    doc.setFillColor(15, 23, 42);
    doc.rect(0, 0, pageW, pageH, 'F');
    doc.setFillColor(239, 68, 68);
    doc.rect(0, 45, pageW, 3, 'F');

    doc.setTextColor(248, 250, 252);
    doc.setFontSize(36);
    doc.setFont('helvetica', 'bold');
    doc.text('AFETIZ', pageW / 2, 30, { align: 'center' });

    doc.setFontSize(11);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(148, 163, 184);
    doc.text('Kriz Izleme ve Afet Analiz Raporu', pageW / 2, 38, { align: 'center' });

    doc.setFontSize(9);
    doc.setTextColor(100, 116, 139);
    doc.text(stats.analysis_date, pageW / 2, 42, { align: 'center' });

    // KPI Kartları
    const kpis = [
        { label: 'TOPLAM ANALIZ', value: stats.total_analyzed, color: [59, 130, 246] },
        { label: 'KRITIK ALARM', value: stats.critical_count, color: [239, 68, 68] },
        { label: 'ETKILENEN IL', value: stats.affected_cities, color: [168, 85, 247] },
        { label: 'YUKSEK ONCELIK', value: stats.high_count, color: [249, 115, 22] },
    ];
    const boxW = (contentW - 12) / 4;
    let bx = margin;
    kpis.forEach(kpi => {
        doc.setFillColor(30, 41, 59);
        doc.roundedRect(bx, 52, boxW, 24, 2, 2, 'F');
        doc.setFillColor(...kpi.color);
        doc.rect(bx, 52, boxW, 1.5, 'F');
        doc.setFontSize(20);
        doc.setTextColor(...kpi.color);
        doc.setFont('helvetica', 'bold');
        doc.text(String(kpi.value), bx + boxW / 2, 66, { align: 'center' });
        doc.setFontSize(7);
        doc.setTextColor(100, 116, 139);
        doc.setFont('helvetica', 'normal');
        doc.text(kpi.label, bx + boxW / 2, 72, { align: 'center' });
        bx += boxW + 4;
    });

    // Öncelik Dağılımı Özeti
    let sy = 86;
    doc.setFontSize(9);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(248, 250, 252);
    doc.text('ONCELIK DAGILIMI', margin, sy);
    doc.setFillColor(239, 68, 68);
    doc.rect(margin, sy + 2, 30, 0.6, 'F');
    sy += 8;

    const priorityData = [
        { label: 'Kritik', count: stats.critical_count, color: [239, 68, 68] },
        { label: 'Yuksek', count: stats.high_count, color: [249, 115, 22] },
        { label: 'Orta', count: stats.medium_count, color: [250, 204, 21] },
        { label: 'Dusuk', count: stats.low_count, color: [16, 185, 129] },
    ];
    const total = stats.total_analyzed || 1;
    const barMaxW = contentW - 40;
    priorityData.forEach(p => {
        const w = Math.max(2, (p.count / total) * barMaxW);
        doc.setFillColor(30, 41, 59);
        doc.rect(margin + 20, sy - 3, barMaxW, 5, 'F');
        doc.setFillColor(...p.color);
        doc.rect(margin + 20, sy - 3, w, 5, 'F');
        doc.setFontSize(7.5);
        doc.setTextColor(203, 213, 225);
        doc.setFont('helvetica', 'normal');
        doc.text(p.label, margin, sy + 0.5);
        doc.text(String(p.count), margin + 20 + barMaxW + 2, sy + 0.5);
        sy += 8;
    });

    // İhtiyaç Dağılımı
    sy += 4;
    doc.setFontSize(9);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(248, 250, 252);
    doc.text('IHTIYAC TURLERI', margin, sy);
    doc.setFillColor(239, 68, 68);
    doc.rect(margin, sy + 2, 30, 0.6, 'F');
    sy += 8;

    const needEntries = Object.entries(stats.need_frequencies).sort((a, b) => b[1] - a[1]);
    const needMax = needEntries[0]?.[1] || 1;
    const needColors = [[239, 68, 68], [249, 115, 22], [59, 130, 246], [168, 85, 247], [16, 185, 129], [250, 204, 21], [236, 72, 153], [6, 182, 212]];
    needEntries.slice(0, 8).forEach(([n, v], i) => {
        const w = Math.max(2, (v / needMax) * barMaxW);
        doc.setFillColor(30, 41, 59);
        doc.rect(margin + 28, sy - 3, barMaxW, 5, 'F');
        doc.setFillColor(...(needColors[i % needColors.length]));
        doc.rect(margin + 28, sy - 3, w, 5, 'F');
        doc.setFontSize(7);
        doc.setTextColor(203, 213, 225);
        doc.setFont('helvetica', 'normal');
        doc.text(normTR(NEED_LABELS[n] || n), margin, sy + 0.5);
        doc.text(String(v), margin + 28 + barMaxW + 2, sy + 0.5);
        sy += 7;
    });

    // İl Dağılımı
    if (sy + 40 < pageH - 20) {
        sy += 4;
        doc.setFontSize(9);
        doc.setFont('helvetica', 'bold');
        doc.setTextColor(248, 250, 252);
        doc.text('IL BAZLI DAGILIM', margin, sy);
        doc.setFillColor(239, 68, 68);
        doc.rect(margin, sy + 2, 30, 0.6, 'F');
        sy += 8;

        const cityEntries = stats.city_breakdown.slice(0, 8);
        const cityMax = cityEntries[0]?.count || 1;
        cityEntries.forEach((c, i) => {
            const w = Math.max(2, (c.count / cityMax) * barMaxW);
            doc.setFillColor(30, 41, 59);
            doc.rect(margin + 22, sy - 3, barMaxW, 5, 'F');
            doc.setFillColor(59, 130, 246);
            doc.rect(margin + 22, sy - 3, w, 5, 'F');
            doc.setFontSize(7);
            doc.setTextColor(203, 213, 225);
            doc.setFont('helvetica', 'normal');
            doc.text(normTR(c.city), margin, sy + 0.5);
            doc.text(String(c.count), margin + 22 + barMaxW + 2, sy + 0.5);
            sy += 7;
        });
    }

    doc.setFontSize(7.5);
    doc.setTextColor(71, 85, 105);
    doc.text('AfetIZ — Yapay Zeka Destekli Afet Yonetim Platformu', pageW / 2, pageH - 8, { align: 'center' });
    doc.text(`Rapor Tarihi: ${stats.analysis_date}`, pageW / 2, pageH - 4, { align: 'center' });

    // ── SAYFA 2: Türkiye Haritası ──────────────────────
    doc.addPage();
    doc.setFillColor(15, 23, 42);
    doc.rect(0, 0, pageW, pageH, 'F');

    doc.setFontSize(13);
    doc.setTextColor(248, 250, 252);
    doc.setFont('helvetica', 'bold');
    doc.text('TURKIYE AFET HARITASI', margin, 16);
    doc.setFillColor(239, 68, 68);
    doc.rect(margin, 19, 45, 0.8, 'F');
    doc.setFontSize(8);
    doc.setTextColor(100, 116, 139);
    doc.setFont('helvetica', 'normal');
    doc.text('Gercek zamanli tweet yogunlugu ve risk seviyeleri', margin, 24);

    if (mapCanvas) {
        const mapImgData = mapCanvas.toDataURL('image/jpeg', 0.88);
        const mapH = (mapCanvas.height / mapCanvas.width) * contentW;
        const clampedH = Math.min(mapH, pageH - 50);
        doc.addImage(mapImgData, 'JPEG', margin, 28, contentW, clampedH);
        const legendY = 28 + clampedH + 5;
        doc.setFontSize(7.5);
        doc.setTextColor(100, 116, 139);
        doc.text('Renk Kodlari:  Kirmizi = Kritik   Turuncu = Yuksek   Sari = Orta   Yesil = Dusuk', margin, legendY);
    } else {
        doc.setFontSize(9);
        doc.setTextColor(100, 116, 139);
        doc.text('Harita goruntusu alinamamadi.', margin, 35);
    }

    doc.setFontSize(7.5);
    doc.setTextColor(71, 85, 105);
    doc.text('AfetIZ — Yapay Zeka Destekli Afet Yonetim Platformu', pageW / 2, pageH - 6, { align: 'center' });

    // ── SAYFA 3: Grafikler ──────────────────────────────
    if (chartCanvases.length > 0) {
        doc.addPage();
        doc.setFillColor(15, 23, 42);
        doc.rect(0, 0, pageW, pageH, 'F');

        doc.setFontSize(13);
        doc.setTextColor(248, 250, 252);
        doc.setFont('helvetica', 'bold');
        doc.text('ANALITIK GORSELLER', margin, 16);
        doc.setFillColor(239, 68, 68);
        doc.rect(margin, 19, 40, 0.8, 'F');

        let cy = 26;
        chartCanvases.forEach(({ title, canvas }) => {
            const cH = Math.min((canvas.height / canvas.width) * contentW, 62);
            if (cy + cH + 10 > pageH - 12) {
                doc.addPage();
                doc.setFillColor(15, 23, 42);
                doc.rect(0, 0, pageW, pageH, 'F');
                cy = margin;
            }
            const imgData = canvas.toDataURL('image/png');
            doc.setFontSize(8.5);
            doc.setTextColor(148, 163, 184);
            doc.setFont('helvetica', 'normal');
            doc.text(title, margin, cy);
            cy += 4;
            doc.addImage(imgData, 'PNG', margin, cy, contentW, cH);
            cy += cH + 10;
        });

        doc.setFontSize(7.5);
        doc.setTextColor(71, 85, 105);
        doc.text('AfetIZ — Yapay Zeka Destekli Afet Yonetim Platformu', pageW / 2, pageH - 6, { align: 'center' });
    }

    // ── SAYFA 4: AI Analiz Raporu ───────────────────────
    if (aiReport) {
        doc.addPage();
        doc.setFillColor(15, 23, 42);
        doc.rect(0, 0, pageW, pageH, 'F');

        doc.setFontSize(13);
        doc.setTextColor(248, 250, 252);
        doc.setFont('helvetica', 'bold');
        doc.text('YAPAY ZEKA KRIZ DEGERLENDIRME RAPORU', margin, 16);
        doc.setFillColor(239, 68, 68);
        doc.rect(margin, 19, 70, 0.8, 'F');

        let ry = 28;
        const sections = aiReport.split(/\n(?=##|\n)/);

        for (const section of sections) {
            const trimmed = normTR(section.trim());
            if (!trimmed) continue;

            const lines = trimmed.split('\n');
            const firstLine = lines[0].trim();
            const isHeader = firstLine.startsWith('##') || (firstLine === firstLine.toUpperCase() && firstLine.length > 4);

            if (isHeader) {
                if (ry + 12 > pageH - 14) {
                    doc.addPage();
                    doc.setFillColor(15, 23, 42);
                    doc.rect(0, 0, pageW, pageH, 'F');
                    ry = margin;
                }
                ry += 3;
                doc.setFontSize(9.5);
                doc.setFont('helvetica', 'bold');
                doc.setTextColor(239, 68, 68);
                const headerText = firstLine.replace(/^#+\s*/, '').replace(/\*\*/g, '').toUpperCase();
                doc.text(headerText, margin, ry);
                doc.setFillColor(30, 41, 59);
                doc.rect(margin, ry + 1.5, contentW, 0.5, 'F');
                ry += 7;
                const bodyLines = lines.slice(1);
                for (const line of bodyLines) {
                    const clean = normTR(line.replace(/\*\*/g, '').replace(/^\s*[-•]\s*/, '• ').trim());
                    if (!clean) { ry += 2; continue; }
                    const wrapped = doc.splitTextToSize(clean, contentW);
                    doc.setFontSize(8.5);
                    doc.setFont('helvetica', 'normal');
                    doc.setTextColor(203, 213, 225);
                    for (const wl of wrapped) {
                        if (ry + 5 > pageH - 14) {
                            doc.addPage();
                            doc.setFillColor(15, 23, 42);
                            doc.rect(0, 0, pageW, pageH, 'F');
                            ry = margin;
                        }
                        doc.text(wl, margin, ry);
                        ry += 4.5;
                    }
                }
            } else {
                const fullText = normTR(lines.join(' ').replace(/\*\*/g, '').trim());
                const wrapped = doc.splitTextToSize(fullText, contentW);
                doc.setFontSize(8.5);
                doc.setFont('helvetica', 'normal');
                doc.setTextColor(203, 213, 225);
                for (const wl of wrapped) {
                    if (ry + 5 > pageH - 14) {
                        doc.addPage();
                        doc.setFillColor(15, 23, 42);
                        doc.rect(0, 0, pageW, pageH, 'F');
                        ry = margin;
                    }
                    doc.text(wl, margin, ry);
                    ry += 4.5;
                }
                ry += 2;
            }
        }

        doc.setFontSize(7.5);
        doc.setTextColor(71, 85, 105);
        doc.text('AfetIZ — Yapay Zeka Destekli Afet Yonetim Platformu', pageW / 2, pageH - 6, { align: 'center' });
    }

    // ── SAYFA 5: Kritik / Acil Müdahale Noktaları ──────
    doc.addPage();
    doc.setFillColor(15, 23, 42);
    doc.rect(0, 0, pageW, pageH, 'F');

    doc.setFontSize(13);
    doc.setTextColor(248, 250, 252);
    doc.setFont('helvetica', 'bold');
    doc.text('KRITIK VE ACIL MUDAHALE NOKTALARI', margin, 16);
    doc.setFillColor(239, 68, 68);
    doc.rect(margin, 19, 70, 0.8, 'F');

    const important = valid
        .filter(t => ['critical', 'high'].includes(t.analysis.map_priority))
        .sort((a, b) => (b.analysis.urgency_score || 0) - (a.analysis.urgency_score || 0));

    let ty = 26;
    const prioColors = { critical: [239, 68, 68], high: [249, 115, 22] };

    if (important.length === 0) {
        doc.setFontSize(9);
        doc.setTextColor(100, 116, 139);
        doc.text('Kritik veya acil seviyede kayit bulunamadi.', margin, ty);
    }

    important.forEach((tweet) => {
        const a = tweet.analysis;
        const [r, g, b] = prioColors[a.map_priority] || [250, 204, 21];
        const addr = normTR([a.street_address, a.neighborhood, a.district, a.city].filter(Boolean).join(' / ') || 'Adres bilinmiyor');
        const needs = normTR((a.need_types || []).map(n => NEED_LABELS[n] || n).join(', ') || '');
        const summaryText = normTR(a.summary || tweet.text || '').slice(0, 160);
        const summaryLines = doc.splitTextToSize(summaryText, contentW - 10);
        const rowH = 14 + summaryLines.length * 4.5;

        if (ty + rowH > pageH - 14) {
            doc.addPage();
            doc.setFillColor(15, 23, 42);
            doc.rect(0, 0, pageW, pageH, 'F');
            ty = margin;
        }

        doc.setFillColor(30, 41, 59);
        doc.roundedRect(margin, ty, contentW, rowH, 2, 2, 'F');
        doc.setFillColor(r, g, b);
        doc.rect(margin, ty, 2.5, rowH, 'F');

        doc.setFontSize(8.5);
        doc.setFont('helvetica', 'bold');
        doc.setTextColor(248, 250, 252);
        doc.text(addr, margin + 5, ty + 6);

        doc.setFontSize(7.5);
        doc.setFont('helvetica', 'normal');
        doc.setTextColor(r, g, b);
        doc.text(`Aciliyet: ${a.urgency_score}/5  |  ${needs}`, margin + 5, ty + 11);

        doc.setTextColor(148, 163, 184);
        summaryLines.forEach((wl, i) => {
            doc.text(wl, margin + 5, ty + 16 + i * 4.5);
        });

        ty += rowH + 3;
    });

    doc.setFontSize(7.5);
    doc.setTextColor(71, 85, 105);
    doc.text('AfetIZ — Yapay Zeka Destekli Afet Yonetim Platformu', pageW / 2, pageH - 6, { align: 'center' });

    // ── Kaydet ──
    const now = new Date();
    const dateStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    doc.save(`afetiz_raporu_${dateStr}.pdf`);
    onProgress('');
}
