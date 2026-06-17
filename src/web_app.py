# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Web dashboard for France Travail offers and market trends."""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template_string, request

from src.trend_aggregation import aggregate_trends


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_OFFERS_PATH = PROJECT_ROOT / "data" / "raw" / "offres_france_travail.json"
PROCESSED_TRENDS_PATH = PROJECT_ROOT / "data" / "processed" / "tendances.json"
PROCESSED_CONTEXT_PATH = PROJECT_ROOT / "data" / "processed" / "metier_context_t3_2025.csv"
DEFAULT_PERIOD = 30
DEFAULT_TOP_N = 10
DEFAULT_PORT = 8000
DEFAULT_HOST = "127.0.0.1"


def _normalize_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().lower()


def _parse_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    candidates = (text, text.replace("Z", ""), text.replace("/", "-"))
    for candidate in candidates:
        try:
            return datetime.fromisoformat(candidate).date()
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def _format_date(value: object) -> str:
    parsed = _parse_date(value)
    return parsed.isoformat() if parsed else ""


def _extract_territory(raw_offer: dict[str, Any]) -> str:
    lieu = raw_offer.get("lieuTravail")
    if isinstance(lieu, dict):
        territory = (
            lieu.get("libelle")
            or lieu.get("commune")
            or lieu.get("codePostal")
        )
        if territory:
            return territory
    return raw_offer.get("territoire") or raw_offer.get("intitule") or ""


def _extract_metier(raw_offer: dict[str, Any]) -> str:
    return (
        raw_offer.get("romeLibelle")
        or raw_offer.get("appellationlibelle")
        or raw_offer.get("intitule")
        or ""
    )


def _extract_contrat(raw_offer: dict[str, Any]) -> str:
    return raw_offer.get("typeContratLibelle") or raw_offer.get("typeContrat") or ""


def _extract_niveau(raw_offer: dict[str, Any]) -> str:
    experience = _normalize_text(raw_offer.get("experienceLibelle") or raw_offer.get("experienceExige"))
    if any(token in experience for token in ("senior", "expert", "lead", "5 ans", "6 ans", "7 ans", "8 ans")):
        return "senior"
    if any(token in experience for token in ("junior", "debutant", "0 an", "1 an", "2 ans", "sans experience")):
        return "junior"
    if experience:
        return "intermediaire"
    return ""


def _extract_competences(raw_offer: dict[str, Any]) -> list[str]:
    competences: list[str] = []
    for item in raw_offer.get("competences") or []:
        if isinstance(item, dict):
            label = item.get("libelle") or item.get("code")
        else:
            label = item
        if label is None:
            continue
        text = re.sub(r"\s+", " ", str(label)).strip()
        if text:
            competences.append(text)
    return competences


def normalize_offer(raw_offer: dict[str, Any]) -> dict[str, Any]:
    return {
        "id_offre": raw_offer.get("id") or raw_offer.get("id_offre") or "",
        "date": _format_date(raw_offer.get("dateActualisation") or raw_offer.get("dateCreation") or raw_offer.get("date")),
        "territoire": _extract_territory(raw_offer),
        "metier": _extract_metier(raw_offer),
        "niveau": _extract_niveau(raw_offer),
        "contrat": _extract_contrat(raw_offer),
        "competences": _extract_competences(raw_offer),
        "entreprise": (raw_offer.get("entreprise") or {}).get("nom") if isinstance(raw_offer.get("entreprise"), dict) else "",
        "description": raw_offer.get("description") or "",
        "intitule": raw_offer.get("intitule") or "",
    }


def load_raw_offers(path: Path = RAW_OFFERS_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Fichier d'offres introuvable: {path}")
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, list):
        raise ValueError("Le fichier d'offres brut doit contenir une liste JSON.")
    return [offer for offer in payload if isinstance(offer, dict)]


def _offer_matches_territory(offer: dict[str, Any], territoire: str | None) -> bool:
    if not territoire:
        return True
    offer_territory = _normalize_text(offer.get("territoire"))
    target = _normalize_text(territoire)
    if not offer_territory or not target:
        return False
    return target == offer_territory or target in offer_territory or offer_territory in target


def _offer_in_period(offer: dict[str, Any], cutoff: date) -> bool:
    parsed = _parse_date(offer.get("date"))
    if parsed is None:
        return True
    return parsed >= cutoff


def filter_offers(offers: list[dict[str, Any]], territoire: str | None, periode_jours: int) -> list[dict[str, Any]]:
    normalized = [normalize_offer(offer) for offer in offers]
    reference_dates = [parsed for parsed in (_parse_date(offer.get("date")) for offer in normalized) if parsed is not None]
    reference_date = max(reference_dates) if reference_dates else date.today()
    cutoff = date.fromordinal(reference_date.toordinal() - max(periode_jours, 0))

    filtered = [
        offer
        for offer in normalized
        if _offer_matches_territory(offer, territoire) and _offer_in_period(offer, cutoff)
    ]
    filtered.sort(key=lambda item: item.get("date") or "", reverse=True)
    return filtered


def load_market_context_rows(path: Path = PROCESSED_CONTEXT_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = [row for row in reader if row.get("domaine")]
    return rows[:12]


def load_trends_snapshot(path: Path = PROCESSED_TRENDS_PATH) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    return payload if isinstance(payload, dict) else None


def _format_percentage(count: int, total: int) -> str:
    if total <= 0:
        return "0,0 %"
    return f"{(count / total) * 100:.1f}".replace('.', ',') + " %"


def build_ranking_entries(data: dict[str, Any] | None, total_offers: int, limit: int) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if not isinstance(data, dict):
        return entries
    for label, raw_count in data.items():
        try:
            count = int(raw_count)
        except (TypeError, ValueError):
            continue
        if count <= 0:
            continue
        entries.append({
            'nom': str(label),
            'count': count,
            'pourcentage': _format_percentage(count, total_offers),
        })
    entries.sort(key=lambda item: (-item['count'], _normalize_text(item['nom'])))
    return entries[:max(limit, 1)]


def build_state(territoire: str | None, periode_jours: int, top_n: int = DEFAULT_TOP_N) -> dict[str, Any]:
    raw_offers = load_raw_offers()
    offers = filter_offers(raw_offers, territoire, periode_jours)
    trends = aggregate_trends(offers, territoire=territoire, periode_jours=periode_jours)
    snapshot = load_trends_snapshot()
    ranking_source = snapshot if snapshot and not territoire and periode_jours == DEFAULT_PERIOD else trends
    market_context = load_market_context_rows()
    territoire_options = sorted(
        {offer["territoire"] for offer in (normalize_offer(raw) for raw in raw_offers) if offer.get("territoire")},
        key=lambda value: value.lower(),
    )
    total_offers = int(ranking_source.get("nombre_offres") or trends.get("nombre_offres") or len(offers))
    top_limit = max(top_n, 1)
    return {
        "territoire": territoire,
        "periode_jours": periode_jours,
        "top_n": top_limit,
        "nombre_offres_brutes": len(raw_offers),
        "nombre_offres_filtrees": len(offers),
        "trends": trends,
        "ranking_source": ranking_source,
        "top_metiers": build_ranking_entries(ranking_source.get("metiers"), total_offers, top_limit),
        "top_competences": build_ranking_entries(ranking_source.get("competences"), total_offers, top_limit),
        "offers": offers[:20],
        "territoire_options": territoire_options,
        "market_context": market_context,
    }


HTML_TEMPLATE = """
<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TrendRadar IA - France Travail</title>
  <style>
    :root {
      --bg: #f4f7fb;
      --surface: #ffffff;
      --surface-alt: #eef4fb;
      --text: #132033;
      --muted: #5a6a7f;
      --line: #d7e0ea;
      --accent: #1866d1;
      --accent-2: #0f8b8d;
      --accent-soft: #dcecff;
      --danger: #bb3e3e;
      --shadow: 0 12px 28px rgba(19, 32, 51, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, "Segoe UI", system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
    }
    header {
      padding: 24px 28px 18px;
      background: linear-gradient(135deg, #123055, #184f8f 65%, #176a9b);
      color: white;
    }
    header h1 {
      margin: 0;
      font-size: 28px;
      line-height: 1.15;
    }
    header p {
      margin: 8px 0 0;
      color: rgba(255, 255, 255, 0.82);
      max-width: 900px;
    }
    .shell { padding: 18px 22px 28px; }
    .filters, .summary, .grid-section, .panel {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 10px;
      box-shadow: var(--shadow);
    }
    .filters {
      display: grid;
      grid-template-columns: 1.2fr 0.6fr 0.4fr auto;
      gap: 12px;
      padding: 14px;
      align-items: end;
      margin-bottom: 16px;
    }
    .field label {
      display: block;
      font-size: 12px;
      font-weight: 700;
      color: var(--muted);
      margin-bottom: 6px;
      text-transform: uppercase;
      letter-spacing: 0.02em;
    }
    .field input {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 11px 12px;
      font: inherit;
      background: white;
      color: var(--text);
    }
    button {
      border: 0;
      background: var(--accent);
      color: white;
      border-radius: 8px;
      padding: 11px 16px;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
    }
    button:hover { filter: brightness(1.02); }
    .summary {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      padding: 14px;
      margin-bottom: 16px;
    }
    .metric {
      background: var(--surface-alt);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }
    .metric .label {
      font-size: 12px;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: 8px;
      font-weight: 700;
    }
    .metric .value {
      font-size: 28px;
      font-weight: 800;
      line-height: 1;
    }
    .metric .caption {
      margin-top: 8px;
      color: var(--muted);
      font-size: 13px;
    }
    .grid {
      display: grid;
      grid-template-columns: 1fr 1.15fr;
      gap: 16px;
      align-items: start;
    }
    .panel { padding: 16px; }
    .trend-grid {
      display: grid;
      grid-template-columns: 1fr;
      gap: 12px;
      margin: 12px 0 10px;
    }
    .detail-section { margin-top: 12px; }
    .detail-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      margin: 12px 0 10px;
    }
    .trend-panel {
      background: var(--surface-alt);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
    }
    .trend-panel h3 {
      margin: 0;
      font-size: 15px;
    }
    .trend-list {
      display: grid;
      gap: 10px;
    }
    .trend-row {
      display: grid;
      gap: 6px;
    }
    .trend-head {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px;
      align-items: baseline;
    }
    .trend-label {
      font-size: 14px;
      font-weight: 600;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .trend-stats {
      color: var(--muted);
      font-size: 13px;
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }
    .trend-track {
      height: 10px;
      border-radius: 999px;
      background: #e8eef5;
      overflow: hidden;
    }
    .trend-fill {
      height: 100%;
      border-radius: inherit;
      background: linear-gradient(90deg, var(--accent), var(--accent-2));
    }
    .trend-empty {
      color: var(--muted);
      padding: 8px 0 2px;
    }
    .rankings-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      margin: 12px 0 10px;
    }
    .ranking-panel {
      background: var(--surface-alt);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
    }
    .ranking-panel h3 {
      margin: 0;
      font-size: 15px;
    }
    .ranking-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    .ranking-table th, .ranking-table td {
      padding: 8px 0;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }
    .ranking-table th {
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.02em;
    }
    .ranking-value { text-align: right; font-variant-numeric: tabular-nums; }
    .ranking-empty { color: var(--muted); padding: 10px 0 2px; }
    .market-context-block { margin-top: 10px; }
    .panel h2 {
      margin: 0 0 12px;
      font-size: 18px;
    }
    .bars { display: grid; gap: 10px; }
    .bar-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 72px;
      gap: 12px;
      align-items: center;
    }
    .bar-label {
      font-size: 14px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .bar-track {
      height: 12px;
      border-radius: 999px;
      background: #e8eef5;
      overflow: hidden;
      margin-top: 6px;
    }
    .bar-fill {
      height: 100%;
      border-radius: inherit;
      background: linear-gradient(90deg, var(--accent), var(--accent-2));
    }
    .bar-value {
      text-align: right;
      color: var(--muted);
      font-weight: 700;
      font-variant-numeric: tabular-nums;
    }
    .offers table {
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }
    .offers th, .offers td {
      text-align: left;
      padding: 10px 8px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
    }
    .offers th {
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.02em;
      position: sticky;
      top: 0;
      background: var(--surface);
      z-index: 1;
    }
    .chips { display: flex; gap: 6px; flex-wrap: wrap; }
    .chip {
      display: inline-flex;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 4px 9px;
      background: #f7faff;
      color: var(--text);
      font-size: 12px;
      font-weight: 600;
    }
    .offer-title { font-weight: 700; margin-bottom: 4px; }
    .offer-company, .offer-meta, .offer-desc { color: var(--muted); font-size: 13px; }
    .offer-desc {
      display: -webkit-box;
      -webkit-line-clamp: 3;
      -webkit-box-orient: vertical;
      overflow: hidden;
      max-width: 860px;
    }
    .market-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }
    .market-table th, .market-table td {
      padding: 8px 6px;
      border-bottom: 1px solid var(--line);
      text-align: left;
    }
    .market-table th {
      color: var(--muted);
      text-transform: uppercase;
      font-size: 12px;
    }
    .empty { color: var(--muted); padding: 10px 0; }
    .subhead {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 10px;
    }
    .subhead small { color: var(--muted); }
    @media (max-width: 1100px) {
      .filters { grid-template-columns: 1fr 1fr; }
      .summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .grid { grid-template-columns: 1fr; }
      .rankings-grid { grid-template-columns: 1fr; }
      .detail-grid { grid-template-columns: 1fr; }
    }
    @media (max-width: 720px) {
      header, .shell { padding-left: 14px; padding-right: 14px; }
      .filters { grid-template-columns: 1fr; }
      .summary { grid-template-columns: 1fr; }
      .offers table { display: block; overflow-x: auto; }
      .ranking-table { display: block; overflow-x: auto; }
    }
  </style>
</head>
<body>
  <header>
    <h1>TrendRadar IA</h1>
    <p>Interface de lecture des offres France Travail et des tendances marché calculées à partir des offres extraites et normalisées.</p>
  </header>
  <main class="shell">
    <form class="filters" id="filters">
      <div class="field">
        <label for="territoire">Territoire</label>
        <input id="territoire" name="territoire" list="territoire-list" placeholder="Tous territoires">
        <datalist id="territoire-list"></datalist>
      </div>
      <div class="field">
        <label for="periode">Période en jours</label>
        <input id="periode" name="periode" type="number" min="1" step="1" value="30">
      </div>
      <div class="field">
        <label>&nbsp;</label>
        <button type="submit">Actualiser</button>
      </div>
      <div class="field">
        <label for="top-n">Top affichés</label>
        <input id="top-n" name="top_n" type="number" min="1" step="1" value="10">
      </div>
      <div class="field">
        <label>&nbsp;</label>
        <button type="button" id="reset" style="background:#0f8b8d;">Réinitialiser</button>
      </div>
    </form>

    <section class="summary" id="summary"></section>

    <section class="grid">
      <section class="panel">
        <div class="subhead">
          <h2>Tendances marché</h2>
          <small id="trends-caption"></small>
        </div>
        <section class="trend-grid">
          <section class="trend-panel">
            <div class="subhead">
              <h3>Tendances marché — Compétences</h3>
              <small id="trend-competences-caption"></small>
            </div>
            <div id="trend-competences"></div>
          </section>
          <section class="trend-panel">
            <div class="subhead">
              <h3>Tendances marché — Nature des contrats</h3>
              <small id="trend-contrats-caption"></small>
            </div>
            <div id="trend-contrats"></div>
          </section>
          <section class="trend-panel">
            <div class="subhead">
              <h3>Tendances marché — Ancienneté demandée</h3>
              <small id="trend-niveaux-caption"></small>
            </div>
            <div id="trend-niveaux"></div>
          </section>
        </section>
        <section class="rankings-grid">
          <section class="ranking-panel">
            <div class="subhead">
              <h3>Top intitulés de poste</h3>
              <small id="metiers-caption"></small>
            </div>
            <table class="ranking-table" id="top-metiers"></table>
          </section>
          <section class="ranking-panel">
            <div class="subhead">
              <h3>Top compétences</h3>
              <small id="competences-caption"></small>
            </div>
            <table class="ranking-table" id="top-competences"></table>
          </section>
        </section>
        <section class="detail-section">
          <div class="subhead">
            <h2 style="margin: 0; font-size: 18px;">Aperçu détaillé des tendances</h2>
            <small>Top 20 par défaut</small>
          </div>
          <section class="detail-grid">
            <section class="trend-panel">
              <div class="subhead"><h3>Compétences</h3><small></small></div>
              <div id="detail-competences"></div>
            </section>
            <section class="trend-panel">
              <div class="subhead"><h3>Métiers</h3><small></small></div>
              <div id="detail-metiers"></div>
            </section>
            <section class="trend-panel">
              <div class="subhead"><h3>Nature des contrats</h3><small></small></div>
              <div id="detail-contrats"></div>
            </section>
            <section class="trend-panel">
              <div class="subhead"><h3>Ancienneté demandée</h3><small></small></div>
              <div id="detail-niveaux"></div>
            </section>
          </section>
        </section>
        <section class="market-context-block">
          <h2 style="margin-top: 0;">Contexte marché France Travail</h2>
          <table class="market-table" id="market-context"></table>
        </section>
      </section>

      <section class="panel offers">
        <div class="subhead">
          <h2>Offres filtrées</h2>
          <small id="offers-caption"></small>
        </div>
        <div style="overflow-x:auto; max-height: 82vh;">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Offre</th>
                <th>Territoire</th>
                <th>Niveau</th>
                <th>Contrat</th>
                <th>Compétences</th>
              </tr>
            </thead>
            <tbody id="offers-body"></tbody>
          </table>
        </div>
      </section>
    </section>
  </main>

  <script>
    const summary = document.getElementById('summary');
    const trendCompetences = document.getElementById('trend-competences');
    const trendContrats = document.getElementById('trend-contrats');
    const trendNiveaux = document.getElementById('trend-niveaux');
    const detailCompetences = document.getElementById('detail-competences');
    const detailMetiers = document.getElementById('detail-metiers');
    const detailContrats = document.getElementById('detail-contrats');
    const detailNiveaux = document.getElementById('detail-niveaux');
    const marketContext = document.getElementById('market-context');
    const offersBody = document.getElementById('offers-body');
    const topMetiers = document.getElementById('top-metiers');
    const topCompetences = document.getElementById('top-competences');
    const metiersCaption = document.getElementById('metiers-caption');
    const competencesCaption = document.getElementById('competences-caption');
    const trendCompetencesCaption = document.getElementById('trend-competences-caption');
    const trendContratsCaption = document.getElementById('trend-contrats-caption');
    const trendNiveauxCaption = document.getElementById('trend-niveaux-caption');
    const territoryInput = document.getElementById('territoire');
    const periodInput = document.getElementById('periode');
    const topNInput = document.getElementById('top-n');
    const territoryList = document.getElementById('territoire-list');
    const trendsCaption = document.getElementById('trends-caption');
    const offersCaption = document.getElementById('offers-caption');
    const form = document.getElementById('filters');
    const resetButton = document.getElementById('reset');

    function escapeHtml(text) {
      return String(text ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
    }

    function renderSummary(state) {
      const t = state.trends;
      summary.innerHTML = [
        ['Offres brutes', state.nombre_offres_brutes, `${state.nombre_offres_filtrees} retenues`],
        ['Offres filtrées', state.nombre_offres_filtrees, `${t.periode_jours} jours`],
        ['Compétences', Object.keys(t.competences || {}).length, 'fréquences comptées'],
        ['Métiers', Object.keys(t.metiers || {}).length, 'fréquences comptées'],
      ].map(([label, value, caption]) => `
        <div class="metric">
          <div class="label">${label}</div>
          <div class="value">${value}</div>
          <div class="caption">${caption}</div>
        </div>
      `).join('');
      trendsCaption.textContent = state.territoire ? `Territoire ${state.territoire}` : 'Tous territoires';
      trendCompetencesCaption.textContent = `Top ${state.top_n}`;
      trendContratsCaption.textContent = `Top ${state.top_n}`;
      trendNiveauxCaption.textContent = `Top ${state.top_n}`;
      metiersCaption.textContent = `Top ${state.top_n}`;
      competencesCaption.textContent = `Top ${state.top_n}`;
      offersCaption.textContent = `${state.offers.length} offres affichées`;
    }

    function sortEntriesByCount(data) {
      return Object.entries(data || {})
        .map(([label, count]) => [String(label), Number(count)])
        .filter(([label, count]) => label.trim() && Number.isFinite(count) && count > 0)
        .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'fr', { sensitivity: 'base' }));
    }

    function isLikelyCompetenceNoise(label) {
      const text = String(label ?? '').trim();
      if (!text || text.length > 80) return true;
      if (text.indexOf(String.fromCharCode(10)) >= 0 || text.includes('.') || text.includes('!') || text.includes('?') || text.includes(';') || text.includes(':')) return true;
      if (text.split(' ').filter(Boolean).length > 12) return true;
      const lowered = text.toLowerCase();
      return [
        'vous apprendrez',
        'vous serez',
        'formation',
        'mission',
        'objectif',
        'capacité à',
        'capacite a',
        'maîtriser',
        'maitriser',
        'savoir faire',
      ].some(fragment => lowered.includes(fragment));
    }

    function formatPercentage(count, totalOffers) {
      return totalOffers > 0 ? ((count / totalOffers) * 100).toFixed(1).replace('.', ',') : '0,0';
    }

    function renderTrendBlock(title, data, totalOffers, limit) {
      const isCompetenceBlock = title.toLowerCase().includes('compétences');
      const entries = sortEntriesByCount(data).filter(([label]) => !isCompetenceBlock || !isLikelyCompetenceNoise(label)).slice(0, Math.max(limit, 1));
      if (!entries.length) {
        return '<div class="trend-empty">Aucune donnée disponible pour cette catégorie.</div>';
      }
      const max = Math.max(...entries.map(([, count]) => count));
      const rows = entries.map(([label, count]) => {
        const width = max ? Math.max(8, (count / max) * 100) : 0;
        const percentage = formatPercentage(count, totalOffers);
        return `
          <div class="trend-row">
            <div class="trend-head">
              <div class="trend-label" title="${escapeHtml(label)}">${escapeHtml(label)}</div>
              <div class="trend-stats">${count} offres · ${percentage} %</div>
            </div>
            <div class="trend-track"><div class="trend-fill" style="width:${width}%"></div></div>
          </div>
        `;
      }).join('');
      return `<div class="trend-list">${rows}</div>`;
    }

    function renderRankingTable(container, data, totalOffers, emptyLabel, limit) {
      const entries = Object.entries(data || {})
        .map(([label, count]) => [label, Number(count)])
        .filter(([, count]) => Number.isFinite(count) && count > 0)
        .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'fr', { sensitivity: 'base' }))
        .slice(0, Math.max(limit, 1));

      if (!entries.length) {
        container.innerHTML = `<tbody><tr><td colspan="3" class="ranking-empty">${emptyLabel}</td></tr></tbody>`;
        return;
      }

      const rows = entries.map(([label, count]) => {
        const percentage = totalOffers > 0 ? ((count / totalOffers) * 100).toFixed(1).replace('.', ',') : '0,0';
        return `<tr>
          <td>${escapeHtml(label)}</td>
          <td class="ranking-value">${count}</td>
          <td class="ranking-value">${percentage} %</td>
        </tr>`;
      }).join('');

      container.innerHTML = `
        <thead>
          <tr>
            <th>Nom</th>
            <th class="ranking-value">Offres</th>
            <th class="ranking-value">Part</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      `;
    }

    function renderMarketContext(rows) {
      if (!rows.length) {
        marketContext.innerHTML = '<tr><td class="empty">Aucun contexte marché disponible.</td></tr>';
        return;
      }
      const headers = Object.keys(rows[0]).slice(0, 4);
      marketContext.innerHTML = `
        <thead><tr>${headers.map(h => `<th>${escapeHtml(h)}</th>`).join('')}</tr></thead>
        <tbody>
          ${rows.map(row => `
            <tr>${headers.map(header => `<td>${escapeHtml(row[header] ?? '')}</td>`).join('')}</tr>
          `).join('')}
        </tbody>
      `;
    }

    function renderOffers(offers) {
      if (!offers.length) {
        offersBody.innerHTML = '<tr><td colspan="6" class="empty">Aucune offre ne correspond aux filtres.</td></tr>';
        return;
      }
      offersBody.innerHTML = offers.map(offer => {
        const competences = (offer.competences || []).map(c => `<span class="chip">${escapeHtml(c)}</span>`).join(' ');
        const description = offer.description ? escapeHtml(offer.description) : '<span class="empty">Aucune description</span>';
        return `
          <tr>
            <td>${escapeHtml(offer.date || '')}</td>
            <td>
              <div class="offer-title">${escapeHtml(offer.intitule || offer.metier || '')}</div>
              <div class="offer-company">${escapeHtml(offer.entreprise || '')}</div>
              <div class="offer-desc">${description}</div>
            </td>
            <td>${escapeHtml(offer.territoire || '')}</td>
            <td>${escapeHtml(offer.niveau || '')}</td>
            <td>${escapeHtml(offer.contrat || '')}</td>
            <td><div class="chips">${competences || '<span class="empty">Aucune compétence</span>'}</div></td>
          </tr>
        `;
      }).join('');
    }

    function populateTerritories(options) {
      territoryList.innerHTML = options.map(value => `<option value="${escapeHtml(value)}"></option>`).join('');
    }

    async function loadState() {
      const params = new URLSearchParams();
      if (territoryInput.value.trim()) params.set('territoire', territoryInput.value.trim());
      params.set('periode', periodInput.value || '30');
      params.set('top_n', topNInput.value || '10');
      const response = await fetch(`/api/state?${params.toString()}`);
      if (!response.ok) throw new Error('Erreur lors du chargement des données');
      const state = await response.json();
      renderSummary(state);
      trendCompetences.innerHTML = renderTrendBlock('Compétences', state.trends.competences || {}, state.trends.nombre_offres || 0, state.top_n || 10);
      trendContrats.innerHTML = renderTrendBlock('Nature des contrats', state.trends.contrats || {}, state.trends.nombre_offres || 0, state.top_n || 10);
      trendNiveaux.innerHTML = renderTrendBlock('Ancienneté demandée', state.trends.niveau || {}, state.trends.nombre_offres || 0, state.top_n || 10);
      detailCompetences.innerHTML = renderTrendBlock('Compétences', state.trends.competences || {}, state.trends.nombre_offres || 0, Math.max(state.top_n || 10, 20));
      detailMetiers.innerHTML = renderTrendBlock('Métiers', state.trends.metiers || {}, state.trends.nombre_offres || 0, Math.max(state.top_n || 10, 20));
      detailContrats.innerHTML = renderTrendBlock('Nature des contrats', state.trends.contrats || {}, state.trends.nombre_offres || 0, Math.max(state.top_n || 10, 20));
      detailNiveaux.innerHTML = renderTrendBlock('Ancienneté demandée', state.trends.niveau || {}, state.trends.nombre_offres || 0, Math.max(state.top_n || 10, 20));
      renderRankingTable(topMetiers, state.top_metiers || {}, state.trends.nombre_offres || 0, 'Aucun intitulé de poste disponible', state.top_n || 10);
      renderRankingTable(topCompetences, state.top_competences || {}, state.trends.nombre_offres || 0, 'Aucune compétence disponible', state.top_n || 10);
      renderMarketContext(state.market_context || []);
      renderOffers(state.offers || []);
      populateTerritories(state.territoire_options || []);
    }

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      await loadState();
    });

    resetButton.addEventListener('click', async () => {
      territoryInput.value = '';
      periodInput.value = 30;
      topNInput.value = 10;
      await loadState();
    });

    loadState().catch(err => {
      summary.innerHTML = `<div class="metric" style="grid-column:1/-1;border-color:var(--danger);color:var(--danger);">${escapeHtml(err.message)}</div>`;
    });
  </script>
</body>
</html>
"""


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index():
        return render_template_string(HTML_TEMPLATE)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/api/state")
    def api_state():
        territoire = request.args.get("territoire") or None
        try:
            periode = int(request.args.get("periode", DEFAULT_PERIOD))
        except ValueError:
            periode = DEFAULT_PERIOD
        try:
            top_n = int(request.args.get("top_n", DEFAULT_TOP_N))
        except ValueError:
            top_n = DEFAULT_TOP_N
        state = build_state(territoire, periode, top_n=top_n)
        return jsonify(state)

    @app.get("/api/offers")
    def api_offers():
        territoire = request.args.get("territoire") or None
        try:
            periode = int(request.args.get("periode", DEFAULT_PERIOD))
        except ValueError:
            periode = DEFAULT_PERIOD
        try:
            top_n = int(request.args.get("top_n", DEFAULT_TOP_N))
        except ValueError:
            top_n = DEFAULT_TOP_N
        state = build_state(territoire, periode, top_n=top_n)
        return jsonify(state["offers"])

    @app.get("/api/trends")
    def api_trends():
        territoire = request.args.get("territoire") or None
        try:
            periode = int(request.args.get("periode", DEFAULT_PERIOD))
        except ValueError:
            periode = DEFAULT_PERIOD
        try:
            top_n = int(request.args.get("top_n", DEFAULT_TOP_N))
        except ValueError:
            top_n = DEFAULT_TOP_N
        state = build_state(territoire, periode, top_n=top_n)
        return jsonify(state["trends"])

    return app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="France Travail offers and trends web dashboard.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--debug", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    app = create_app()
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
