#!/usr/bin/env python3
"""
AfetIZ — Profesyonel Kriz Raporu Üreticisi
===========================================

Kullanım (API üzerinden):
    POST /export/full-pdf-report  →  afet_raporu.pdf

Kullanım (doğrudan):
    python report_generator.py                     # demo veriyle test
    python report_generator.py sonuclar.json       # JSON dosyasından

Gereksinimler:
    pip install weasyprint jinja2 pandas matplotlib seaborn Pillow

WeasyPrint kurulum notu:
    Linux  : sudo apt-get install libpango-1.0-0 libpangoft2-1.0-0 libgdk-pixbuf2.0-0
    macOS  : brew install pango
    Windows: https://doc.courtbouillon.org/weasyprint/stable/first_steps.html
"""

from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
from collections import defaultdict
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")                          # GUI olmadan render et
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd
import seaborn as sns
from jinja2 import Template
from PIL import Image, ImageDraw, ImageFont

# ─────────────────────────────────────────────────────────
# SABITLER
# ─────────────────────────────────────────────────────────

# Öncelik → renk eşlemeleri
PRIORITY_COLOR = {
    "critical": "#DC2626",   # kırmızı
    "high":     "#F97316",   # turuncu
    "medium":   "#FACC15",   # sarı
    "low":      "#10B981",   # yeşil
}

PRIORITY_LABEL = {
    "critical": "Kritik",
    "high":     "Yüksek",
    "medium":   "Orta",
    "low":      "Düşük",
}

# Aciliyet skoru → renk
URGENCY_COLOR = {5: "#7F1D1D", 4: "#F97316", 3: "#FACC15", 2: "#34D399", 1: "#94A3B8"}

NEED_LABEL = {
    "arama_kurtarma":   "Arama Kurtarma",
    "saglik":           "Sağlık",
    "su":               "Su",
    "gida":             "Gıda",
    "barinma":          "Barınma",
    "yol_kapali":       "Yol Kapalı",
    "yangin":           "Yangın",
    "elektrik_iletisim": "Elektrik / İletişim",
}

# Grafik renk paleti
CHART_PALETTE = ["#DC2626", "#F97316", "#3B82F6", "#A855F7",
                 "#10B981", "#FACC15", "#EC4899", "#06B6D4"]

# A4 fiziksel genişliği: 21 cm ≈ 8.27 inç; kenar boşlukları 0.75 inç × 2
CHART_WIDTH_IN = 6.8   # inç
CHART_DPI      = 150


# ─────────────────────────────────────────────────────────
# 1. VERİ İŞLEME
# ─────────────────────────────────────────────────────────

def _normalize(data: dict) -> dict:
    """
    AfetIZ /results API çıktısını veya serbest dict formatını
    rapor için standart bir yapıya dönüştürür.
    """

    # /results endpoint'i {"count": N, "tweets": [...]} döndürür
    tweets_raw: list[dict] = data.get("tweets", data.get("ihbar_listesi", []))

    ihbarlar: list[dict] = []
    for t in tweets_raw:
        ana = t.get("analysis") or {}
        ts  = t.get("trust_score") or {}
        auth = t.get("authenticity") or {}
        author = t.get("author") or {}

        ihbarlar.append({
            "tweet_id":         str(t.get("tweet_id", "")),
            "text":             str(t.get("text", "")),
            "il":               str(ana.get("city", t.get("il", "Bilinmiyor"))),
            "ilce":             str(ana.get("district", t.get("ilce", ""))),
            "mahalle":          str(ana.get("neighborhood", t.get("mahalle", ""))),
            "sokak":            str(ana.get("street_address", t.get("sokak", ""))),
            "kesin_konum":      bool(ana.get("has_precise_location", False)),
            "ihtiyac":          list(ana.get("need_types", t.get("ihtiyac", []))),
            "aciliyet":         int(ana.get("urgency_score", t.get("aciliyet", 3))),
            "oncelik":          str(ana.get("map_priority", t.get("oncelik", "medium"))),
            "ozet":             str(ana.get("summary", t.get("ozet", t.get("text", "")))),
            "guven":            float(ts.get("score", t.get("guven", 50.0))),
            "sahtelik":         (
                "Gerçek"          if auth.get("is_authentic") is True  else
                "Şüpheli"         if auth.get("is_authentic") is False else
                "Doğrulanmadı"
            ),
            "yazar":            str(author.get("username", t.get("yazar", ""))),
            "analyzed_at":      str(t.get("analyzed_at", "")),
        })

    # Özet istatistikler
    toplam = len(ihbarlar)
    kritik = sum(1 for i in ihbarlar if i["oncelik"] == "critical")
    yuksek = sum(1 for i in ihbarlar if i["oncelik"] == "high")
    orta   = sum(1 for i in ihbarlar if i["oncelik"] == "medium")
    dusuk  = sum(1 for i in ihbarlar if i["oncelik"] == "low")
    iller  = {i["il"] for i in ihbarlar if i["il"] not in ("Bilinmiyor", "")}

    return {
        "rapor_tarihi":   data.get("rapor_tarihi", datetime.now().strftime("%d.%m.%Y %H:%M")),
        "toplam_analiz":  data.get("toplam_analiz", toplam),
        "kritik_alarm":   data.get("kritik_alarm", kritik),
        "yuksek_alarm":   yuksek,
        "orta_alarm":     orta,
        "dusuk_alarm":    dusuk,
        "etkilenen_il":   data.get("etkilenen_il", len(iller)),
        "genel_risk":     (
            "ÇOK YÜKSEK" if kritik > 0 else
            "YÜKSEK"     if yuksek > 0 else
            "ORTA"       if orta   > 0 else "DÜŞÜK"
        ),
        "ihbarlar":       ihbarlar,
        "ai_rapor":       data.get("ai_rapor", ""),
    }


def _build_dataframe(ihbarlar: list[dict]) -> pd.DataFrame:
    """İhbar listesinden pandas DataFrame oluşturur."""
    if not ihbarlar:
        return pd.DataFrame()
    df = pd.DataFrame(ihbarlar)
    df["aciliyet"] = pd.to_numeric(df["aciliyet"], errors="coerce").fillna(3).astype(int)
    df["guven"]    = pd.to_numeric(df["guven"],    errors="coerce").fillna(50.0)
    return df


# ─────────────────────────────────────────────────────────
# 2. GRAFİK ÜRETICILER
# ─────────────────────────────────────────────────────────

def _fig_to_b64(fig: plt.Figure) -> str:
    """Matplotlib figürünü base64 PNG stringine dönüştürür."""
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=CHART_DPI, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    buf.seek(0)
    plt.close(fig)
    return base64.b64encode(buf.read()).decode("utf-8")


def chart_il_yogunluk(df: pd.DataFrame) -> str:
    """
    Yatay bar chart: il bazlı tweet sayısı.
    Her bar, o ildeki max aciliyet skoruna göre renklendirilir.
    """
    if df.empty:
        return ""

    # İl başına: tweet sayısı ve max aciliyet
    grp = df.groupby("il").agg(
        sayi=("tweet_id", "count"),
        max_ac=("aciliyet", "max"),
    ).sort_values("sayi", ascending=True).tail(12)

    colors = [URGENCY_COLOR.get(int(v), "#94A3B8") for v in grp["max_ac"]]

    fig, ax = plt.subplots(figsize=(CHART_WIDTH_IN, max(3.2, len(grp) * 0.55)),
                           facecolor="#F8FAFC")
    ax.set_facecolor("#F8FAFC")

    bars = ax.barh(grp.index, grp["sayi"], color=colors, edgecolor="white",
                   linewidth=0.6, height=0.65)

    # Değer etiketi
    for bar in bars:
        w = bar.get_width()
        ax.text(w + 0.05, bar.get_y() + bar.get_height() / 2,
                f" {int(w)}", va="center", ha="left",
                fontsize=9, color="#334155", fontweight="bold")

    ax.set_xlabel("Tweet / Alarm Sayısı", fontsize=9, color="#475569", labelpad=6)
    ax.set_title("İl Bazlı Alarm Dağılımı", fontsize=11, fontweight="bold",
                 color="#1A365D", pad=10)
    ax.tick_params(axis="y", labelsize=9, colors="#334155")
    ax.tick_params(axis="x", labelsize=8, colors="#94A3B8")
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.spines["bottom"].set_color("#E2E8F0")
    ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))

    # Legend: aciliyet renkleri
    legend_items = [
        mpatches.Patch(color=URGENCY_COLOR[5], label="Aciliyet 5 – Çok Kritik"),
        mpatches.Patch(color=URGENCY_COLOR[4], label="Aciliyet 4 – Acil"),
        mpatches.Patch(color=URGENCY_COLOR[3], label="Aciliyet 3 – Orta"),
        mpatches.Patch(color=URGENCY_COLOR[2], label="Aciliyet 1-2 – Düşük"),
    ]
    ax.legend(handles=legend_items, fontsize=7.5, loc="lower right",
              framealpha=0.7, edgecolor="#E2E8F0")

    fig.tight_layout()
    return _fig_to_b64(fig)


def chart_ihtiyac_pasta(df: pd.DataFrame) -> str:
    """Pasta grafik: ihtiyaç türü dağılımı."""
    if df.empty:
        return ""

    counts: dict[str, int] = defaultdict(int)
    for ihtiyaclar in df["ihtiyac"]:
        if isinstance(ihtiyaclar, list):
            for n in ihtiyaclar:
                counts[n] += 1
        elif isinstance(ihtiyaclar, str) and ihtiyaclar:
            counts[ihtiyaclar] += 1

    if not counts:
        return ""

    labels  = [NEED_LABEL.get(k, k) for k in counts]
    values  = list(counts.values())
    colors  = CHART_PALETTE[: len(labels)]

    fig, ax = plt.subplots(figsize=(5.0, 3.8), facecolor="#F8FAFC")
    ax.set_facecolor("#F8FAFC")

    wedges, texts, autotexts = ax.pie(
        values,
        labels=None,
        colors=colors,
        autopct="%1.0f%%",
        startangle=90,
        wedgeprops={"edgecolor": "white", "linewidth": 1.5},
        pctdistance=0.78,
    )
    for at in autotexts:
        at.set_fontsize(8)
        at.set_color("white")
        at.set_fontweight("bold")

    ax.legend(
        wedges, [f"{l} ({v})" for l, v in zip(labels, values)],
        loc="lower center", bbox_to_anchor=(0.5, -0.22),
        fontsize=7.5, ncol=2, framealpha=0.0,
        labelcolor="#334155",
    )
    ax.set_title("İhtiyaç Türleri Dağılımı", fontsize=11, fontweight="bold",
                 color="#1A365D", pad=8)
    fig.tight_layout()
    return _fig_to_b64(fig)


def chart_aciliyet_dagilim(df: pd.DataFrame) -> str:
    """Yatay bar chart: öncelik seviyesi dağılımı."""
    if df.empty:
        return ""

    priority_order = ["critical", "high", "medium", "low"]
    counts = df["oncelik"].value_counts().reindex(priority_order, fill_value=0)
    labels = [PRIORITY_LABEL.get(p, p) for p in counts.index]
    colors = [PRIORITY_COLOR.get(p, "#94A3B8") for p in counts.index]

    fig, ax = plt.subplots(figsize=(CHART_WIDTH_IN, 2.6), facecolor="#F8FAFC")
    ax.set_facecolor("#F8FAFC")

    bars = ax.barh(labels[::-1], counts.values[::-1],
                   color=colors[::-1], edgecolor="white",
                   linewidth=0.6, height=0.55)

    for bar in bars:
        w = bar.get_width()
        ax.text(w + 0.05, bar.get_y() + bar.get_height() / 2,
                f" {int(w)}", va="center", ha="left",
                fontsize=10, color="#1A365D", fontweight="bold")

    ax.set_xlabel("Alarm Sayısı", fontsize=9, color="#475569", labelpad=6)
    ax.set_title("Öncelik Seviyesi Dağılımı", fontsize=11, fontweight="bold",
                 color="#1A365D", pad=8)
    ax.tick_params(axis="y", labelsize=10, colors="#334155")
    ax.tick_params(axis="x", labelsize=8, colors="#94A3B8")
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.spines["bottom"].set_color("#E2E8F0")
    ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    fig.tight_layout()
    return _fig_to_b64(fig)


def chart_risk_gauge(risk_label: str) -> str:
    """
    Risk seviyesini gösteren gösterge (gauge) grafiği.
    Kapak sayfası için üretilir.
    """
    levels      = ["DÜŞÜK", "ORTA", "YÜKSEK", "ÇOK YÜKSEK"]
    level_colors = ["#10B981", "#FACC15", "#F97316", "#DC2626"]
    try:
        idx = levels.index(risk_label)
    except ValueError:
        idx = 3  # varsayılan: çok yüksek

    # Yarım daire gauge
    fig, ax = plt.subplots(figsize=(4.0, 2.4), facecolor="white",
                           subplot_kw={"aspect": "equal"})
    ax.set_facecolor("white")
    ax.axis("off")

    theta_total = 180  # derece
    segment     = theta_total / len(levels)

    for i, (lvl, clr) in enumerate(zip(levels, level_colors)):
        start = 180 - (i + 1) * segment
        wedge = mpatches.Wedge(
            center=(0.5, 0.1), r=0.42,
            theta1=start, theta2=start + segment,
            width=0.16, facecolor=clr, edgecolor="white", linewidth=2,
        )
        ax.add_patch(wedge)

    # İğne
    import numpy as np
    angle_deg = 180 - (idx + 0.5) * segment
    angle_rad = np.radians(angle_deg)
    ax.annotate(
        "", xy=(0.5 + 0.30 * np.cos(angle_rad), 0.1 + 0.30 * np.sin(angle_rad)),
        xytext=(0.5, 0.1),
        arrowprops=dict(arrowstyle="-|>", color="#1A365D", lw=2.5),
    )
    ax.plot(0.5, 0.1, "o", markersize=8, color="#1A365D", zorder=5)

    ax.text(0.5, -0.15, risk_label, ha="center", va="center",
            fontsize=14, fontweight="bold", color=level_colors[idx])
    ax.text(0.5, -0.30, "Genel Risk Seviyesi", ha="center", va="center",
            fontsize=8, color="#64748B")

    ax.set_xlim(0, 1)
    ax.set_ylim(-0.4, 0.55)
    fig.tight_layout(pad=0.2)
    return _fig_to_b64(fig)


# ─────────────────────────────────────────────────────────
# 3. HTML ŞABLONU
# ─────────────────────────────────────────────────────────

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<title>AfetIZ — Kriz Raporu {{ rapor_tarihi }}</title>
<style>
/* ── TEMEL RESET ── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

/* ── SAYFA AYARLARI (WeasyPrint @page) ── */
@page {
    size: A4 portrait;
    margin: 1in 0.75in 1in 0.75in;
    @bottom-center {
        content: "Sayfa " counter(page) " / " counter(pages);
        font-size: 8pt;
        color: #94A3B8;
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    }
    @top-right {
        content: "AfetIZ — Gizli Kriz Raporu";
        font-size: 7.5pt;
        color: #CBD5E1;
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    }
}

/* ── GLOBAL TİPOGRAFİ ── */
body {
    font-family: 'Helvetica Neue', Helvetica, 'Segoe UI', Arial, sans-serif;
    font-size: 11pt;
    color: #1E293B;
    background: #F8FAFC;
    line-height: 1.55;
}

/* ── SAYFA KIRILMASI ── */
.page-break { page-break-after: always; }

/* ── BAŞLIK HİYERARŞİSİ ── */
h1 {
    font-size: 26pt;
    font-weight: 900;
    color: #0F172A;
    letter-spacing: -0.5px;
    margin-bottom: 8px;
}
h2 {
    font-size: 14pt;
    font-weight: 700;
    color: #1A365D;
    border-left: 5px solid #DC2626;
    padding-left: 10px;
    margin: 22px 0 12px;
}
h3 {
    font-size: 11pt;
    font-weight: 700;
    color: #334155;
    margin: 14px 0 6px;
}

/* ── KAPAK SAYFASI ── */
.cover {
    text-align: center;
    padding-top: 60px;
}
.cover-logo {
    font-size: 52pt;
    font-weight: 900;
    color: #0F172A;
    letter-spacing: -2px;
    line-height: 1;
}
.cover-logo span { color: #DC2626; }
.cover-subtitle {
    font-size: 13pt;
    color: #475569;
    margin-top: 6px;
    letter-spacing: 3px;
    text-transform: uppercase;
}
.cover-divider {
    width: 80px;
    height: 4px;
    background: linear-gradient(90deg, #DC2626, #F97316);
    margin: 28px auto;
    border-radius: 2px;
}
.cover-date {
    font-size: 11pt;
    color: #64748B;
    margin-top: 8px;
}
.cover-gauge {
    margin: 40px auto 0;
    max-width: 320px;
}
.cover-gauge img { width: 100%; }
.cover-badge-row {
    display: flex;
    justify-content: center;
    gap: 18px;
    margin-top: 48px;
    flex-wrap: wrap;
}
.cover-badge {
    padding: 10px 24px;
    border-radius: 6px;
    font-size: 10pt;
    font-weight: 700;
    letter-spacing: 0.5px;
}
.cover-badge.critical { background: #DC2626; color: #fff; }
.cover-badge.info     { background: #EFF6FF; color: #1D4ED8; border: 1px solid #BFDBFE; }

/* ── KPI KARTLARI ── */
.kpi-row {
    display: flex;
    gap: 14px;
    margin: 18px 0;
}
.kpi-card {
    flex: 1;
    background: #fff;
    border-radius: 10px;
    padding: 18px 14px 14px;
    border: 1px solid #E2E8F0;
    text-align: center;
    border-top: 4px solid #E2E8F0;
}
.kpi-card.red    { border-top-color: #DC2626; }
.kpi-card.orange { border-top-color: #F97316; }
.kpi-card.blue   { border-top-color: #3B82F6; }
.kpi-card.purple { border-top-color: #A855F7; }
.kpi-card.green  { border-top-color: #10B981; }
.kpi-number {
    font-size: 34pt;
    font-weight: 900;
    line-height: 1;
    margin-bottom: 4px;
}
.kpi-card.red    .kpi-number { color: #DC2626; }
.kpi-card.orange .kpi-number { color: #F97316; }
.kpi-card.blue   .kpi-number { color: #3B82F6; }
.kpi-card.purple .kpi-number { color: #A855F7; }
.kpi-card.green  .kpi-number { color: #10B981; }
.kpi-label {
    font-size: 7.5pt;
    font-weight: 700;
    color: #94A3B8;
    text-transform: uppercase;
    letter-spacing: 0.8px;
}

/* ── RİSK ROZETİ ── */
.risk-badge {
    display: inline-block;
    padding: 3px 12px;
    border-radius: 4px;
    font-size: 9pt;
    font-weight: 700;
    letter-spacing: 1px;
    text-transform: uppercase;
    color: #fff;
}
.risk-critical { background: #DC2626; }
.risk-high     { background: #F97316; }
.risk-medium   { background: #FACC15; color: #1A1A1A; }
.risk-low      { background: #10B981; }

/* ── ÖZET METNİ ── */
.summary-box {
    background: #fff;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    padding: 16px 18px;
    font-size: 10.5pt;
    line-height: 1.7;
    color: #334155;
    margin-top: 14px;
}
.hl-critical { color: #DC2626; font-weight: 700; }
.hl-city     { color: #1D4ED8; font-weight: 700; }
.hl-score    { color: #F97316; font-weight: 700; }

/* ── GRAFİK ALANLARI ── */
.chart-section { margin: 18px 0; }
.chart-title {
    font-size: 10pt;
    font-weight: 700;
    color: #475569;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    margin-bottom: 8px;
    padding-bottom: 4px;
    border-bottom: 1px solid #E2E8F0;
}
.chart-img {
    width: 100%;
    border-radius: 6px;
    border: 1px solid #E2E8F0;
}
.charts-grid {
    display: flex;
    gap: 14px;
    align-items: flex-start;
}
.charts-grid .chart-left  { flex: 3; }
.charts-grid .chart-right { flex: 2; }

/* ── RİSK KARTLARI (Bölgesel Analiz) ── */
.risk-card {
    background: #fff;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    overflow: hidden;
    margin-bottom: 14px;
    page-break-inside: avoid;
}
.risk-card-header {
    padding: 10px 16px;
    font-size: 11.5pt;
    font-weight: 800;
    color: #fff;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.risk-card-header.critical { background: #DC2626; }
.risk-card-header.high     { background: #F97316; }
.risk-card-header.medium   { background: #FACC15; color: #1A1A1A; }
.risk-card-header.low      { background: #10B981; }
.risk-card-body {
    padding: 12px 16px;
    font-size: 9.5pt;
    color: #334155;
}
.risk-row {
    display: flex;
    gap: 6px;
    margin-bottom: 5px;
    align-items: flex-start;
}
.risk-key {
    font-weight: 700;
    color: #64748B;
    min-width: 95px;
    flex-shrink: 0;
    font-size: 8.5pt;
    text-transform: uppercase;
    letter-spacing: 0.3px;
}
.risk-val { color: #1E293B; }
.need-pill {
    display: inline-block;
    background: #EFF6FF;
    color: #1D4ED8;
    border: 1px solid #BFDBFE;
    border-radius: 4px;
    padding: 1px 7px;
    font-size: 8pt;
    font-weight: 600;
    margin: 1px 2px;
}
.need-pill.critical-need {
    background: #FEF2F2;
    color: #DC2626;
    border-color: #FECACA;
}

/* ── MÜdAHALE ÖNERİLERİ ── */
.mudahale-list {
    list-style: none;
    margin-top: 8px;
}
.mudahale-list li {
    display: flex;
    gap: 10px;
    align-items: flex-start;
    padding: 7px 12px;
    margin-bottom: 5px;
    background: #F8FAFC;
    border-radius: 6px;
    border: 1px solid #E2E8F0;
    font-size: 9.5pt;
    page-break-inside: avoid;
}
.mudahale-list li .icon {
    flex-shrink: 0;
    width: 18px;
    height: 18px;
    background: #DBEAFE;
    color: #1D4ED8;
    border-radius: 4px;
    font-size: 10pt;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
}
.mudahale-list li .icon.red { background: #FEE2E2; color: #DC2626; }
.mudahale-list li .icon.orange { background: #FFEDD5; color: #F97316; }

/* ── HAM VERİ TABLOSU ── */
.data-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 8.5pt;
    background: #fff;
    border-radius: 8px;
    overflow: hidden;
    border: 1px solid #E2E8F0;
}
.data-table thead tr {
    background: #1A365D;
    color: #fff;
}
.data-table th {
    padding: 9px 10px;
    text-align: left;
    font-weight: 700;
    letter-spacing: 0.4px;
    font-size: 8pt;
    text-transform: uppercase;
}
.data-table td {
    padding: 7px 10px;
    border-bottom: 1px solid #F1F5F9;
    color: #334155;
    vertical-align: top;
}
.data-table tbody tr:nth-child(even) td { background: #F8FAFC; }
.data-table tbody tr:hover td { background: #F1F5F9; }

/* Aciliyet 5 → kırmızı arka plan */
.urgency-5 td { background: #FEF2F2 !important; }
.urgency-5-badge {
    background: #DC2626;
    color: #fff;
    padding: 2px 7px;
    border-radius: 4px;
    font-weight: 700;
    font-size: 8pt;
}
.urgency-4-badge { background: #FED7AA; color: #92400E; padding: 2px 7px; border-radius: 4px; font-weight: 700; font-size: 8pt; }
.urgency-3-badge { background: #FEF9C3; color: #854D0E; padding: 2px 7px; border-radius: 4px; font-size: 8pt; }
.urgency-low-badge { background: #DCFCE7; color: #166534; padding: 2px 7px; border-radius: 4px; font-size: 8pt; }

.unverified { color: #DC2626; font-style: italic; font-weight: 700; }
.warn-icon  { color: #DC2626; font-weight: 900; margin-right: 2px; }

/* ── AI RAPOR BÖLÜMÜ ── */
.ai-report {
    background: #fff;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    padding: 16px 18px;
    font-size: 9.5pt;
    line-height: 1.75;
    color: #334155;
    white-space: pre-wrap;
    word-wrap: break-word;
}

/* ── FOOTER BANDI ── */
.section-footer {
    font-size: 7.5pt;
    color: #94A3B8;
    text-align: right;
    margin-top: 14px;
    padding-top: 6px;
    border-top: 1px solid #E2E8F0;
}
</style>
</head>
<body>

{# ════════════════════════════════════════════════════════ #}
{# SAYFA 1: KAPAK                                          #}
{# ════════════════════════════════════════════════════════ #}
<div class="cover page-break">
    <div class="cover-logo">AFET<span>IZ</span></div>
    <div class="cover-subtitle">Kriz İzleme &amp; Afet Yönetim Platformu</div>
    <div class="cover-divider"></div>

    <h1 style="font-size:20pt; margin-bottom:4px;">AFET ve KRİZ RAPORU</h1>
    <div class="cover-date">Oluşturulma Tarihi: <strong>{{ rapor_tarihi }}</strong></div>

    {%- if gauge_img %}
    <div class="cover-gauge">
        <img src="data:image/png;base64,{{ gauge_img }}" alt="Risk Göstergesi">
    </div>
    {%- endif %}

    <div class="cover-badge-row">
        <div class="cover-badge critical">⚠ {{ genel_risk }} RİSK</div>
        <div class="cover-badge info">📊 {{ toplam_analiz }} Tweet Analiz Edildi</div>
        <div class="cover-badge info">🗺 {{ etkilenen_il }} İl Etkilendi</div>
    </div>

    <div style="margin-top:60px; color:#94A3B8; font-size:8pt;">
        GİZLİLİK DERECESİ: HİZMETE ÖZEL — Yetkisiz kopyalama ve dağıtım yasaktır.
    </div>
</div>

{# ════════════════════════════════════════════════════════ #}
{# SAYFA 2: YÖNETİCİ ÖZETİ                                #}
{# ════════════════════════════════════════════════════════ #}
<div class="page-break">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
        <h2 style="margin:0; border:none; padding:0; font-size:16pt; color:#0F172A;">
            YÖNETİCİ ÖZETİ
        </h2>
        <span class="risk-badge risk-critical">● KRİTİK</span>
    </div>
    <div style="height:3px; background:linear-gradient(90deg,#DC2626,#F97316,transparent); margin-bottom:20px; border-radius:2px;"></div>

    {# KPI Kartları #}
    <div class="kpi-row">
        <div class="kpi-card red">
            <div class="kpi-number">{{ toplam_analiz }}</div>
            <div class="kpi-label">Toplam Analiz</div>
        </div>
        <div class="kpi-card orange">
            <div class="kpi-number">{{ kritik_alarm }}</div>
            <div class="kpi-label">Kritik Alarm</div>
        </div>
        <div class="kpi-card purple">
            <div class="kpi-number">{{ yuksek_alarm }}</div>
            <div class="kpi-label">Yüksek Öncelikli</div>
        </div>
        <div class="kpi-card blue">
            <div class="kpi-number">{{ etkilenen_il }}</div>
            <div class="kpi-label">Etkilenen İl</div>
        </div>
        <div class="kpi-card green">
            <div class="kpi-number">{{ orta_alarm + dusuk_alarm }}</div>
            <div class="kpi-label">Orta / Düşük</div>
        </div>
    </div>

    {# Özet Metni #}
    <div class="summary-box">
        <strong>Durum Değerlendirmesi:</strong> Bu rapor, <strong>{{ rapor_tarihi }}</strong> tarihinde
        AfetIZ yapay zeka platformu tarafından otomatik olarak üretilmiştir. Toplam
        <span class="hl-score">{{ toplam_analiz }}</span> tweet analiz edilmiş;
        <span class="hl-critical">{{ kritik_alarm }} kritik</span> ve
        <span class="hl-score">{{ yuksek_alarm }} yüksek öncelikli</span> alarm tespit edilmiştir.
        Etkilenen bölge sayısı <strong>{{ etkilenen_il }}</strong>'dir.
        {%- if kritik_alarm > 0 %}
        <strong>Acil koordinasyon ve kaynak tahsisi gereklidir.</strong>
        {%- endif %}
    </div>

    {# AI Raporu varsa kısa özet #}
    {%- if ai_rapor %}
    <h2>YAPAY ZEKA ANALİZ ÖZETİ</h2>
    <div class="ai-report">{{ ai_rapor[:1200] }}{% if ai_rapor|length > 1200 %}...

[Devamı için son sayfaya bakınız]{% endif %}</div>
    {%- endif %}

    <div class="section-footer">AfetIZ — {{ rapor_tarihi }}</div>
</div>

{# ════════════════════════════════════════════════════════ #}
{# SAYFA 3: DURUM PANOSU (DASHBOARD)                       #}
{# ════════════════════════════════════════════════════════ #}
<div class="page-break">
    <h2>DURUM PANOSU — ANALİTİK GÖRSELLER</h2>

    {# Grafik 1: İl Yoğunluk Bar Chart #}
    {%- if chart_il %}
    <div class="chart-section">
        <div class="chart-title">▌ Bölüm 1: İl Bazlı Alarm ve Tweet Yoğunluğu</div>
        <img class="chart-img" src="data:image/png;base64,{{ chart_il }}" alt="İl Grafik">
    </div>
    {%- endif %}

    {# Grafik 2 ve 3: yan yana #}
    <div class="charts-grid">
        {%- if chart_pasta %}
        <div class="chart-left">
            <div class="chart-section">
                <div class="chart-title">▌ Bölüm 2: İhtiyaç Türleri Dağılımı</div>
                <img class="chart-img" src="data:image/png;base64,{{ chart_pasta }}" alt="İhtiyaç Pasta">
            </div>
        </div>
        {%- endif %}
        {%- if chart_aciliyet %}
        <div class="chart-right">
            <div class="chart-section">
                <div class="chart-title">▌ Bölüm 3: Öncelik Dağılımı</div>
                <img class="chart-img" src="data:image/png;base64,{{ chart_aciliyet }}" alt="Aciliyet Grafik">
            </div>
        </div>
        {%- endif %}
    </div>

    <div class="section-footer">AfetIZ — {{ rapor_tarihi }}</div>
</div>

{# ════════════════════════════════════════════════════════ #}
{# SAYFA 4: BÖLGESEL RİSK ANALİZİ                         #}
{# ════════════════════════════════════════════════════════ #}
<div class="page-break">
    <h2>BÖLGESEL RİSK ANALİZİ VE MÜDAHALE PLANI</h2>

    {%- for sehir in sehir_riskleri %}
    <div class="risk-card">
        <div class="risk-card-header {{ sehir.oncelik_css }}">
            <span>📍 {{ sehir.il }}
                {%- if sehir.ilce %} — {{ sehir.ilce }}{%- endif %}
            </span>
            <span>
                <span style="font-size:9pt; opacity:0.9;">Alarm:</span>
                {{ sehir.alarm_sayisi }}
                &nbsp;|&nbsp;
                <span style="font-size:9pt; opacity:0.9;">Maks Aciliyet:</span>
                {{ sehir.max_aciliyet }}/5
            </span>
        </div>
        <div class="risk-card-body">
            <div class="risk-row">
                <span class="risk-key">Aciliyet Skoru</span>
                <span class="risk-val">
                    <strong>{{ sehir.max_aciliyet }}/5</strong>
                    {%- if sehir.max_aciliyet == 5 %}
                    &nbsp;<span class="risk-badge risk-critical">ÇOK KRİTİK</span>
                    {%- elif sehir.max_aciliyet >= 4 %}
                    &nbsp;<span class="risk-badge risk-high">ACİL</span>
                    {%- endif %}
                </span>
            </div>
            <div class="risk-row">
                <span class="risk-key">İhtiyaç Türleri</span>
                <span class="risk-val">
                    {%- for n in sehir.ihtiyaclar %}
                    <span class="need-pill {{ 'critical-need' if n in ['arama_kurtarma','saglik'] else '' }}">
                        {{ n | replace('_', ' ') | title }}
                    </span>
                    {%- endfor %}
                </span>
            </div>
            {%- if sehir.ozet %}
            <div class="risk-row">
                <span class="risk-key">Durum Özeti</span>
                <span class="risk-val" style="font-style:italic;">{{ sehir.ozet }}</span>
            </div>
            {%- endif %}
            {%- if sehir.kesin_adresler %}
            <div class="risk-row">
                <span class="risk-key">Kesin Adresler</span>
                <span class="risk-val">
                    {%- for adres in sehir.kesin_adresler %}
                    📌 {{ adres }}<br>
                    {%- endfor %}
                </span>
            </div>
            {%- endif %}
        </div>
    </div>
    {%- endfor %}

    {# Müdahale Önerileri #}
    <h2>ACİL MÜDAHALE ÖNERİLERİ</h2>
    <ul class="mudahale-list">
        {%- for oneri in mudahale_onerileri %}
        <li>
            <span class="icon {{ oneri.renk }}">{{ loop.index }}</span>
            <span>{{ oneri.metin }}</span>
        </li>
        {%- endfor %}
    </ul>

    <div class="section-footer">AfetIZ — {{ rapor_tarihi }}</div>
</div>

{# ════════════════════════════════════════════════════════ #}
{# SAYFA 5: HAM VERİ — DETAYLI LOKASYONLAR                #}
{# ════════════════════════════════════════════════════════ #}
<div>
    <h2>HAM VERİ — TÜM İHBARLAR ve DETAYLI LOKASYONLAR</h2>
    <p style="font-size:8.5pt; color:#64748B; margin-bottom:10px;">
        Toplam <strong>{{ ihbarlar | length }}</strong> ihbar kaydı.
        Kırmızı arka plan ile işaretlenen satırlar aciliyet seviyesi 5 olan kritik ihbarlardır.
    </p>

    <table class="data-table">
        <thead>
            <tr>
                <th>#</th>
                <th>Lokasyon</th>
                <th>Adres</th>
                <th>Aciliyet</th>
                <th>İhtiyaç Türü</th>
                <th>Güven</th>
                <th>Doğrulama</th>
            </tr>
        </thead>
        <tbody>
            {%- for ihbar in ihbarlar %}
            <tr class="{{ 'urgency-5' if ihbar.aciliyet == 5 else '' }}">
                <td style="color:#94A3B8; font-size:7.5pt;">{{ loop.index }}</td>
                <td>
                    <strong>{{ ihbar.il }}</strong>
                    {%- if ihbar.ilce %}<br><span style="font-size:8pt; color:#64748B;">{{ ihbar.ilce }}</span>{%- endif %}
                    {%- if ihbar.mahalle %}<br><span style="font-size:7.5pt; color:#94A3B8;">{{ ihbar.mahalle }}</span>{%- endif %}
                </td>
                <td style="font-size:8pt; color:#475569;">
                    {%- if ihbar.sokak %}
                    📌 {{ ihbar.sokak }}
                    {%- elif ihbar.il == 'Bilinmiyor' %}
                    <span class="unverified"><span class="warn-icon">!</span>Adres Bilinmiyor</span>
                    {%- else %}
                    <span style="color:#94A3B8;">—</span>
                    {%- endif %}
                </td>
                <td style="text-align:center; white-space:nowrap;">
                    {%- if ihbar.aciliyet == 5 %}
                    <span class="urgency-5-badge">5/5 ⚠</span>
                    {%- elif ihbar.aciliyet == 4 %}
                    <span class="urgency-4-badge">4/5</span>
                    {%- elif ihbar.aciliyet == 3 %}
                    <span class="urgency-3-badge">3/5</span>
                    {%- else %}
                    <span class="urgency-low-badge">{{ ihbar.aciliyet }}/5</span>
                    {%- endif %}
                </td>
                <td>
                    {%- for n in ihbar.ihtiyac %}
                    <span class="need-pill">{{ n | replace('_', ' ') | title }}</span>
                    {%- endfor %}
                </td>
                <td style="text-align:center; font-size:8pt;">
                    {%- if ihbar.guven >= 70 %}
                    <span style="color:#16A34A; font-weight:700;">{{ ihbar.guven | int }}%</span>
                    {%- elif ihbar.guven >= 40 %}
                    <span style="color:#D97706; font-weight:700;">{{ ihbar.guven | int }}%</span>
                    {%- else %}
                    <span style="color:#DC2626; font-weight:700;">{{ ihbar.guven | int }}%</span>
                    {%- endif %}
                </td>
                <td style="font-size:8pt;">
                    {%- if ihbar.sahtelik == 'Gerçek' %}
                    <span style="color:#16A34A; font-weight:700;">✓ Gerçek</span>
                    {%- elif ihbar.sahtelik == 'Şüpheli' %}
                    <span class="unverified"><span class="warn-icon">!</span>Şüpheli</span>
                    {%- else %}
                    <span style="color:#94A3B8;">Kontrol Edilmedi</span>
                    {%- endif %}
                </td>
            </tr>
            {%- endfor %}
        </tbody>
    </table>

    {# AI Raporunun Devamı #}
    {%- if ai_rapor and ai_rapor|length > 1200 %}
    <h2 style="margin-top:24px;">YAPAY ZEKA TAM KRİZ DEĞERLENDİRMESİ</h2>
    <div class="ai-report">{{ ai_rapor }}</div>
    {%- endif %}

    <div class="section-footer">AfetIZ — {{ rapor_tarihi }} &nbsp;|&nbsp; Bu rapor yapay zeka destekli olarak üretilmiştir.</div>
</div>

</body>
</html>
"""


# ─────────────────────────────────────────────────────────
# 4. ŞEHRE GÖRE RİSK KARTI VERİSİ HAZIRLA
# ─────────────────────────────────────────────────────────

def _build_sehir_riskleri(df: pd.DataFrame) -> list[dict]:
    """
    DataFrame'den şehir bazlı risk kartı verilerini hesaplar.
    Çıktı: Jinja2 şablonunda kullanılacak sözlük listesi.
    """
    if df.empty:
        return []

    results = []
    for il, grp in df.groupby("il"):
        if il in ("Bilinmiyor", ""):
            continue

        max_ac   = int(grp["aciliyet"].max())
        alarm_n  = len(grp)
        ozet     = grp.sort_values("aciliyet", ascending=False).iloc[0]["ozet"]

        # Tüm ihtiyaç türlerini topla (tekrarsız)
        ihtiyaclar = []
        seen = set()
        for ihtiyac_list in grp["ihtiyac"]:
            lst = ihtiyac_list if isinstance(ihtiyac_list, list) else []
            for n in lst:
                if n not in seen:
                    seen.add(n)
                    ihtiyaclar.append(n)

        # Kesin adresleri topla
        kesin_adr = grp[grp["kesin_konum"] == True]["sokak"].dropna().tolist()
        kesin_adr = [a for a in kesin_adr if a]

        # İlçe bilgisi (en sık geçen)
        ilce = ""
        if "ilce" in grp.columns:
            ilce_counts = grp["ilce"].dropna().value_counts()
            if not ilce_counts.empty:
                ilce = str(ilce_counts.index[0])

        # Öncelik CSS sınıfı
        if max_ac == 5:
            css = "critical"
        elif max_ac == 4:
            css = "high"
        elif max_ac == 3:
            css = "medium"
        else:
            css = "low"

        results.append({
            "il":           il,
            "ilce":         ilce,
            "alarm_sayisi": alarm_n,
            "max_aciliyet": max_ac,
            "ihtiyaclar":   ihtiyaclar[:8],
            "ozet":         str(ozet)[:200] if ozet else "",
            "kesin_adresler": kesin_adr[:4],
            "oncelik_css":  css,
        })

    # Büyük aciliyetten küçüğe sırala
    results.sort(key=lambda x: (-x["max_aciliyet"], -x["alarm_sayisi"]))
    return results


def _default_mudahale(data: dict) -> list[dict]:
    """
    Veri yapısına göre varsayılan müdahale önerileri listesi oluşturur.
    Her öneriye bir renk sınıfı atanır (kırmızı > turuncu > varsayılan).
    """
    kritik = data.get("kritik_alarm", 0)
    iller  = data.get("etkilenen_il", 0)
    ihb    = data.get("ihbarlar", [])

    # En sık geçen ihtiyaç türleri
    need_counts: dict[str, int] = defaultdict(int)
    for i in ihb:
        for n in (i.get("ihtiyac") or []):
            need_counts[n] += 1
    top_needs = sorted(need_counts, key=lambda x: -need_counts[x])[:3]

    oneris = []

    if kritik > 0:
        oneris.append({
            "metin": f"Kritik ({kritik} alarm) bölgelere AFAD ve arama-kurtarma ekipleri derhal yönlendirilmeli.",
            "renk": "red",
        })

    if "saglik" in top_needs or "arama_kurtarma" in top_needs:
        oneris.append({
            "metin": "Tüm etkilenen illerde 112 koordineli sağlık ve tahliye operasyonu başlatılmalı.",
            "renk": "red",
        })

    if "su" in top_needs:
        oneris.append({
            "metin": "Su sıkıntısı çekilen bölgelere acil su tankeri ve içme suyu tedariki sağlanmalı.",
            "renk": "orange",
        })

    if "barinma" in top_needs:
        oneris.append({
            "metin": "Barınma ihtiyacı olan vatandaşlar için çadır kenti veya geçici konaklama alanları kurulmalı.",
            "renk": "orange",
        })

    if "yol_kapali" in top_needs:
        oneris.append({
            "metin": "Kapalı yollar için alternatif güzergahlar hazırlanmalı; ağır iş makineleri sevk edilmeli.",
            "renk": "orange",
        })

    if "elektrik_iletisim" in top_needs:
        oneris.append({
            "metin": "Elektrik ve iletişim altyapısı hasar tespiti yapılmalı; seyyar enerji üniteleri konuşlandırılmalı.",
            "renk": "",
        })

    oneris += [
        {
            "metin": f"Etkilenen {iller} ilde anlık durum tespiti için drone ve uydu görüntüsü alınmalı.",
            "renk": "",
        },
        {
            "metin": "Sosyal medya izleme sistemi 7/24 aktif tutularak yeni ihbarlar gerçek zamanlı değerlendirmeli.",
            "renk": "",
        },
        {
            "metin": "Yerel yönetimler, valilikler ve Kızılay koordinasyon toplantısı 2 saatte bir yapılmalı.",
            "renk": "",
        },
        {
            "metin": "Kesin adresi doğrulanan noktalara (has_precise_location=True) öncelikli ekip gönderilmeli.",
            "renk": "",
        },
    ]

    return oneris[:10]


# ─────────────────────────────────────────────────────────
# 5. ANA FONKSİYON
# ─────────────────────────────────────────────────────────

def rapor_olustur(
    data: dict,
    output_path: str = "afet_raporu.pdf",
    ai_rapor: str = "",
) -> str:
    """
    Afet kriz raporunu PDF olarak oluşturur.

    Args:
        data:        AfetIZ API /results çıktısı veya serbest dict.
        output_path: Kaydedilecek PDF dosyasının yolu.
        ai_rapor:    (Opsiyonel) Gemini tarafından üretilmiş metin raporu.

    Returns:
        Kaydedilen PDF dosyasının mutlak yolu.
    """

    # WeasyPrint kurulu mu kontrol et
    try:
        from weasyprint import HTML, CSS
    except ImportError:
        raise ImportError(
            "WeasyPrint kurulu değil.\n"
            "Kurulum: pip install weasyprint\n"
            "Sistem bağımlılıkları için: https://doc.courtbouillon.org/weasyprint/"
        )

    print("[AfetIZ] Veri normalleştiriliyor...")
    norm        = _normalize(data)
    norm["ai_rapor"] = ai_rapor or data.get("ai_rapor", "")
    ihbarlar    = norm["ihbarlar"]
    df          = _build_dataframe(ihbarlar)

    # ── Grafikleri üret ──────────────────────────────────
    print("[AfetIZ] Grafikler üretiliyor...")
    gauge_img      = chart_risk_gauge(norm["genel_risk"])
    chart_il       = chart_il_yogunluk(df)
    chart_pasta    = chart_ihtiyac_pasta(df)
    chart_aciliyet = chart_aciliyet_dagilim(df)

    # ── Şehir risk kartları ──────────────────────────────
    print("[AfetIZ] Şehir risk analizi yapılıyor...")
    sehir_riskleri    = _build_sehir_riskleri(df)
    mudahale_onerileri = _default_mudahale(norm)

    # ── Jinja2 HTML render ───────────────────────────────
    print("[AfetIZ] HTML şablonu render ediliyor...")
    template = Template(HTML_TEMPLATE)
    html_str = template.render(
        rapor_tarihi       = norm["rapor_tarihi"],
        toplam_analiz      = norm["toplam_analiz"],
        kritik_alarm       = norm["kritik_alarm"],
        yuksek_alarm       = norm["yuksek_alarm"],
        orta_alarm         = norm["orta_alarm"],
        dusuk_alarm        = norm["dusuk_alarm"],
        etkilenen_il       = norm["etkilenen_il"],
        genel_risk         = norm["genel_risk"],
        ai_rapor           = norm["ai_rapor"],
        ihbarlar           = ihbarlar,
        sehir_riskleri     = sehir_riskleri,
        mudahale_onerileri = mudahale_onerileri,
        gauge_img          = gauge_img,
        chart_il           = chart_il,
        chart_pasta        = chart_pasta,
        chart_aciliyet     = chart_aciliyet,
    )

    # ── WeasyPrint ile PDF'e dönüştür ────────────────────
    print("[AfetIZ] PDF oluşturuluyor (WeasyPrint)...")
    output_path = str(Path(output_path).resolve())

    HTML(string=html_str, base_url=".").write_pdf(output_path)

    print(f"[AfetIZ] ✅ Rapor kaydedildi: {output_path}")
    return output_path


# ─────────────────────────────────────────────────────────
# 6. DEMO VERİSİ (TEST İÇİN)
# ─────────────────────────────────────────────────────────

DEMO_DATA = {
    "rapor_tarihi": datetime.now().strftime("%d.%m.%Y %H:%M"),
    "tweets": [
        {
            "tweet_id": "t001", "text": "Hatay Antakya Cumhuriyet Mah. Gül Sk. No:12 enkaz altındayız, kanama var, acil yardım!",
            "analysis": {"city": "Hatay", "district": "Antakya", "neighborhood": "Cumhuriyet Mah.", "street_address": "Gül Sk. No:12",
                         "has_precise_location": True, "need_types": ["arama_kurtarma", "saglik"],
                         "urgency_score": 5, "confidence": 0.95, "summary": "Enkaz altında yaralı, kanama var.", "map_priority": "critical"},
            "trust_score": {"score": 88, "explanation": "Güvenilir kaynak"}, "authenticity": {"is_authentic": True},
            "author": {"username": "afetzede01", "account_age_days": 730, "followers": 1200},
        },
        {
            "tweet_id": "t002", "text": "Kahramanmaraş merkez 2 gündür su yok, gıda da bitti",
            "analysis": {"city": "Kahramanmaraş", "district": "Merkez", "neighborhood": "", "street_address": "",
                         "has_precise_location": False, "need_types": ["su", "gida"],
                         "urgency_score": 4, "confidence": 0.88, "summary": "Su ve gıda yok.", "map_priority": "high"},
            "trust_score": {"score": 70, "explanation": "Orta güven"}, "authenticity": {"is_authentic": None},
            "author": {"username": "user_maras", "account_age_days": 400, "followers": 300},
        },
        {
            "tweet_id": "t003", "text": "Gaziantep Şehitkamil yol kapandı araçlar geçemiyor elektrikler yok",
            "analysis": {"city": "Gaziantep", "district": "Şehitkamil", "neighborhood": "", "street_address": "",
                         "has_precise_location": False, "need_types": ["yol_kapali", "elektrik_iletisim"],
                         "urgency_score": 3, "confidence": 0.80, "summary": "Yol kapalı, elektrik yok.", "map_priority": "medium"},
            "trust_score": {"score": 55, "explanation": "Hesap yeni"}, "authenticity": {"is_authentic": None},
            "author": {"username": "gzp_haber", "account_age_days": 90, "followers": 50},
        },
        {
            "tweet_id": "t004", "text": "Hatay Iskenderun liman bölgesinde yangın var, acil!",
            "analysis": {"city": "Hatay", "district": "İskenderun", "neighborhood": "Liman", "street_address": "",
                         "has_precise_location": False, "need_types": ["yangin", "arama_kurtarma"],
                         "urgency_score": 5, "confidence": 0.91, "summary": "Liman bölgesinde aktif yangın.", "map_priority": "critical"},
            "trust_score": {"score": 92, "explanation": "Doğrulandı"}, "authenticity": {"is_authentic": True},
            "author": {"username": "iskenderun_haber", "account_age_days": 1500, "followers": 8000},
        },
        {
            "tweet_id": "t005", "text": "Adıyaman Besni köyünde barınma yok, çadır lazım",
            "analysis": {"city": "Adıyaman", "district": "Besni", "neighborhood": "", "street_address": "",
                         "has_precise_location": False, "need_types": ["barinma"],
                         "urgency_score": 3, "confidence": 0.75, "summary": "Barınma ihtiyacı.", "map_priority": "medium"},
            "trust_score": {"score": 45, "explanation": "Profil eski ama pasif"}, "authenticity": {"is_authentic": False},
            "author": {"username": "anon_kullanici", "account_age_days": 30, "followers": 12},
        },
        {
            "tweet_id": "t006", "text": "Malatya Yeşilyurt sağlık ocağı çöktü, yaralılar var",
            "analysis": {"city": "Malatya", "district": "Yeşilyurt", "neighborhood": "", "street_address": "Yeşilyurt Sağlık Ocağı",
                         "has_precise_location": True, "need_types": ["saglik", "arama_kurtarma"],
                         "urgency_score": 4, "confidence": 0.87, "summary": "Sağlık ocağı çöktü, yaralı var.", "map_priority": "high"},
            "trust_score": {"score": 75, "explanation": "Orta-yüksek güven"}, "authenticity": {"is_authentic": None},
            "author": {"username": "malatya_son_dakika", "account_age_days": 600, "followers": 2200},
        },
        {
            "tweet_id": "t007", "text": "Bilinmeyen bir lokasyon sanki deprem oldu gib geldi",
            "analysis": {"city": "Bilinmiyor", "district": "", "neighborhood": "", "street_address": "",
                         "has_precise_location": False, "need_types": [],
                         "urgency_score": 1, "confidence": 0.20, "summary": "Belirsiz ihbar.", "map_priority": "low"},
            "trust_score": {"score": 15, "explanation": "Güvenilir değil"}, "authenticity": {"is_authentic": False},
            "author": {"username": "anonim99", "account_age_days": 5, "followers": 3},
        },
    ],
}


# ─────────────────────────────────────────────────────────
# 7. CLI ÇALIŞTIRICISI
# ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # JSON dosyasından veri yükle
        json_path = sys.argv[1]
        with open(json_path, "r", encoding="utf-8") as f:
            veri = json.load(f)
        print(f"[AfetIZ] {json_path} dosyasından veri yüklendi.")
    else:
        print("[AfetIZ] Demo verisi kullanılıyor...")
        veri = DEMO_DATA

    output = sys.argv[2] if len(sys.argv) > 2 else "afet_raporu.pdf"
    rapor_olustur(veri, output_path=output)
