/**
 * AfetİZ — D3.js Grafik Modülü
 *
 * Analiz sonuçlarından üç grafik üretir:
 *   1. İhtiyaç türü dağılımı (Donut)
 *   2. Şehir bazlı yoğunluk (Horizontal Bar)
 *   3. Aciliyet skoru dağılımı (Bar)
 */

// D3 CDN'den yüklenmeyecek, npm'den import edeceğiz
// Ancak bu projede vanilla Vite + CDN kullanıyoruz
// D3'ü dinamik olarak yükleyelim

let d3 = null;
let tooltipDiv = null;

const NEED_LABELS = {
    arama_kurtarma: 'Arama Kurtarma',
    saglik: 'Sağlık',
    su: 'Su',
    gida: 'Gıda',
    barinma: 'Barınma',
    yol_kapali: 'Yol Kapalı',
    yangin: 'Yangın',
    elektrik_iletisim: 'Elektrik/İletişim',
};

const CHART_COLORS = ['#ef4444', '#f97316', '#3b82f6', '#a855f7', '#10b981', '#facc15', '#ec4899', '#06b6d4'];

/**
 * D3.js'i yükle ve tooltip oluştur
 */
export async function initCharts() {
    // D3'ü CDN'den script tag ile yükle
    if (!window.d3) {
        await new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = 'https://d3js.org/d3.v7.min.js';
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }
    d3 = window.d3;

    // Tooltip oluştur
    tooltipDiv = d3.select('body').append('div')
        .attr('class', 'tooltip-d3')
        .style('opacity', 0);
}

/**
 * Tüm grafikleri güncelle
 * @param {Array} analyzedTweets - Backend'den gelen analiz sonuçları
 */
export function updateCharts(analyzedTweets) {
    if (!d3) return;

    const validTweets = analyzedTweets.filter(t => t.analysis);

    updateNeedTypeChart(validTweets);
    updateCityBarChart(validTweets);
    updateUrgencyChart(validTweets);
}

/** İhtiyaç türü dağılımı (Donut Chart) */
function updateNeedTypeChart(tweets) {
    const container = document.getElementById('need-type-chart');
    if (!container) return;
    container.innerHTML = '';

    // İhtiyaç türlerini say
    const needCounts = {};
    tweets.forEach(t => {
        (t.analysis.need_types || []).forEach(n => {
            needCounts[n] = (needCounts[n] || 0) + 1;
        });
    });

    const data = Object.entries(needCounts)
        .map(([key, val]) => ({ type: NEED_LABELS[key] || key, value: val }))
        .sort((a, b) => b.value - a.value);

    if (data.length === 0) {
        container.innerHTML = '<div style="color:#94a3b8;font-size:0.8rem;text-align:center;padding:2rem;">Henüz veri yok</div>';
        return;
    }

    const width = 500, height = 260;
    const svg = d3.select(container)
        .append('svg')
        .attr('viewBox', `0 0 ${width} ${height}`)
        .attr('preserveAspectRatio', 'xMidYMid meet')
        .append('g')
        .attr('transform', `translate(${width / 2 - 60}, ${height / 2})`);

    const radius = 95;
    const color = d3.scaleOrdinal().domain(data.map(d => d.type)).range(CHART_COLORS);
    const pie = d3.pie().value(d => d.value).sort(null);
    const arcGen = d3.arc().innerRadius(52).outerRadius(radius);
    const hoverArc = d3.arc().innerRadius(52).outerRadius(radius + 8);

    svg.selectAll('path')
        .data(pie(data))
        .enter()
        .append('path')
        .attr('d', arcGen)
        .attr('fill', d => color(d.data.type))
        .attr('stroke', '#0f172a')
        .attr('stroke-width', 2)
        .style('cursor', 'pointer')
        .on('mouseover', function (ev, d) {
            d3.select(this).transition().duration(150).attr('d', hoverArc);
            tooltipDiv.style('opacity', 1)
                .html(`<strong>${d.data.type}</strong>: ${d.data.value}`)
                .style('left', (ev.pageX + 12) + 'px')
                .style('top', (ev.pageY - 24) + 'px');
        })
        .on('mouseout', function () {
            d3.select(this).transition().duration(150).attr('d', arcGen);
            tooltipDiv.style('opacity', 0);
        });

    // Orta metin
    svg.append('text')
        .attr('text-anchor', 'middle')
        .attr('dy', '-0.3em')
        .attr('fill', '#f8fafc')
        .style('font-size', '1.6rem')
        .style('font-weight', '800')
        .text(data.reduce((s, d) => s + d.value, 0));

    svg.append('text')
        .attr('text-anchor', 'middle')
        .attr('dy', '1.2em')
        .attr('fill', '#94a3b8')
        .style('font-size', '0.6rem')
        .text('TOPLAM');

    // Legend
    const legend = svg.selectAll('.legend')
        .data(data.slice(0, 6))
        .enter()
        .append('g')
        .attr('transform', (d, i) => `translate(120, ${-60 + i * 20})`);

    legend.append('rect').attr('width', 10).attr('height', 10).attr('rx', 2).attr('fill', d => color(d.type));
    legend.append('text').attr('x', 16).attr('y', 9).text(d => `${d.type} (${d.value})`).attr('fill', '#cbd5e1').style('font-size', '10px');
}

/** Şehir bazlı tweet yoğunluğu (Horizontal Bar) */
function updateCityBarChart(tweets) {
    const container = document.getElementById('city-bar-chart');
    if (!container) return;
    container.innerHTML = '';

    const cityCounts = {};
    tweets.forEach(t => {
        const city = t.analysis.city || 'Bilinmiyor';
        cityCounts[city] = (cityCounts[city] || 0) + 1;
    });

    const data = Object.entries(cityCounts)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 7)
        .map(([name, count]) => ({ name, count }));

    if (data.length === 0) {
        container.innerHTML = '<div style="color:#94a3b8;font-size:0.8rem;text-align:center;padding:2rem;">Henüz veri yok</div>';
        return;
    }

    const margin = { top: 10, right: 30, bottom: 25, left: 90 };
    const width = 460, height = 240;
    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;

    const svg = d3.select(container)
        .append('svg')
        .attr('viewBox', `0 0 ${width} ${height}`)
        .attr('preserveAspectRatio', 'xMidYMid meet')
        .append('g')
        .attr('transform', `translate(${margin.left},${margin.top})`);

    const xScale = d3.scaleLinear().domain([0, d3.max(data, d => d.count)]).nice().range([0, innerW]);
    const yScale = d3.scaleBand().domain(data.map(d => d.name)).range([0, innerH]).padding(0.25);

    // Barlar
    svg.selectAll('.bar')
        .data(data)
        .enter()
        .append('rect')
        .attr('x', 0)
        .attr('y', d => yScale(d.name))
        .attr('width', 0)
        .attr('height', yScale.bandwidth())
        .attr('fill', '#3b82f6')
        .attr('rx', 5)
        .style('cursor', 'pointer')
        .on('mouseover', function (ev, d) {
            d3.select(this).attr('fill', '#60a5fa');
            tooltipDiv.style('opacity', 1).html(`${d.name}: <strong>${d.count}</strong> tweet`).style('left', (ev.pageX + 12) + 'px').style('top', (ev.pageY - 24) + 'px');
        })
        .on('mouseout', function () {
            d3.select(this).attr('fill', '#3b82f6');
            tooltipDiv.style('opacity', 0);
        })
        .transition()
        .duration(600)
        .delay((_, i) => i * 80)
        .attr('width', d => xScale(d.count));

    // Değer etiketleri
    svg.selectAll('.value-label')
        .data(data)
        .enter()
        .append('text')
        .attr('x', d => xScale(d.count) + 6)
        .attr('y', d => yScale(d.name) + yScale.bandwidth() / 2)
        .attr('dy', '0.35em')
        .attr('fill', '#94a3b8')
        .style('font-size', '10px')
        .style('font-weight', '600')
        .text(d => d.count);

    // Eksenler
    svg.append('g').call(d3.axisLeft(yScale)).attr('color', '#cbd5e1').style('font-size', '10px').select('.domain').remove();
    svg.append('g').attr('transform', `translate(0,${innerH})`).call(d3.axisBottom(xScale).ticks(5)).attr('color', '#64748b');
}

/** Aciliyet skoru dağılımı (Vertical Bar) */
function updateUrgencyChart(tweets) {
    const container = document.getElementById('urgency-chart');
    if (!container) return;
    container.innerHTML = '';

    const urgencyCounts = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 };
    tweets.forEach(t => {
        const score = t.analysis.urgency_score;
        if (score >= 1 && score <= 5) urgencyCounts[score]++;
    });

    const data = Object.entries(urgencyCounts).map(([score, count]) => ({ score: +score, count }));
    const urgencyColors = { 1: '#10b981', 2: '#22d3ee', 3: '#facc15', 4: '#f97316', 5: '#ef4444' };
    const urgencyLabels = { 1: 'Bilgi', 2: 'Düşük', 3: 'Orta', 4: 'Acil', 5: 'Çok Acil' };

    if (data.every(d => d.count === 0)) {
        container.innerHTML = '<div style="color:#94a3b8;font-size:0.8rem;text-align:center;padding:2rem;">Henüz veri yok</div>';
        return;
    }

    const margin = { top: 10, right: 20, bottom: 40, left: 40 };
    const width = 460, height = 260;
    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;

    const svg = d3.select(container)
        .append('svg')
        .attr('viewBox', `0 0 ${width} ${height}`)
        .attr('preserveAspectRatio', 'xMidYMid meet')
        .append('g')
        .attr('transform', `translate(${margin.left},${margin.top})`);

    const xScale = d3.scaleBand().domain(data.map(d => d.score)).range([0, innerW]).padding(0.3);
    const yScale = d3.scaleLinear().domain([0, d3.max(data, d => d.count) || 5]).nice().range([innerH, 0]);

    svg.selectAll('.bar')
        .data(data)
        .enter()
        .append('rect')
        .attr('x', d => xScale(d.score))
        .attr('y', innerH)
        .attr('width', xScale.bandwidth())
        .attr('height', 0)
        .attr('fill', d => urgencyColors[d.score])
        .attr('rx', 5)
        .on('mouseover', function (ev, d) {
            tooltipDiv.style('opacity', 1).html(`${urgencyLabels[d.score]}: <strong>${d.count}</strong>`).style('left', (ev.pageX + 12) + 'px').style('top', (ev.pageY - 24) + 'px');
        })
        .on('mouseout', () => tooltipDiv.style('opacity', 0))
        .transition()
        .duration(600)
        .delay((_, i) => i * 100)
        .attr('y', d => yScale(d.count))
        .attr('height', d => innerH - yScale(d.count));

    // X ekseni
    svg.append('g')
        .attr('transform', `translate(0,${innerH})`)
        .call(d3.axisBottom(xScale).tickFormat(d => urgencyLabels[d]))
        .attr('color', '#94a3b8')
        .style('font-size', '9px');

    // Y ekseni
    svg.append('g').call(d3.axisLeft(yScale).ticks(5)).attr('color', '#64748b');
}
