# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Web dashboard comparing France Travail and Indeed offers."""

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

from src.offer_normalization import normalize_offers
from src.source_comparison import compare_sources
from src.web_app import filter_offers as filter_france_travail_offers
from src.web_app import load_raw_offers, normalize_offer


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEED_PATH = PROJECT_ROOT / "data" / "samples" / "offres_indeed_sample.json"
DEFAULT_PERIOD = 30
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8001
PROCESSED_CONTEXT_PATH = PROJECT_ROOT / "data" / "processed" / "metier_context_t3_2025.csv"


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


def load_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def load_market_context_rows(path: Path = PROCESSED_CONTEXT_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = [row for row in reader if row.get("domaine")]
    return rows[:10]


def filter_normalized_offers(offers: list[dict[str, Any]], territoire: str | None, periode_jours: int) -> list[dict[str, Any]]:
    reference_dates = [parsed for parsed in (_parse_date(offer.get("date")) for offer in offers) if parsed is not None]
    reference_date = max(reference_dates) if reference_dates else date.today()
    cutoff = date.fromordinal(reference_date.toordinal() - max(periode_jours, 0))
    filtered = []
    target = _normalize_text(territoire) if territoire else ""
    for offer in offers:
        offer_date = _parse_date(offer.get("date"))
        if offer_date is not None and offer_date < cutoff:
            continue
        if territoire:
            territory_value = _normalize_text(offer.get("territoire"))
            if not territory_value or (target not in territory_value and territory_value not in target):
                continue
        filtered.append(offer)
    filtered.sort(key=lambda item: item.get("date") or "", reverse=True)
    return filtered


def normalize_indeed_offers(indeed_raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return normalize_offers(indeed_raw, "indeed")


def _top_rows(data: dict[str, int], limit: int = 10) -> list[dict[str, Any]]:
    return [{"label": key, "count": value} for key, value in list(data.items())[:limit]]


def build_state(territoire: str | None, periode_jours: int, indeed_path: Path = DEFAULT_INDEED_PATH) -> dict[str, Any]:
    raw_offers = load_raw_offers()
    france_travail_offers = filter_france_travail_offers(raw_offers, territoire, periode_jours)
    france_travail_trends = compare_sources(france_travail_offers, [], territoire=territoire, periode_jours=periode_jours)["france_travail"]

    indeed_raw = load_json_list(indeed_path)
    indeed_normalized = normalize_indeed_offers(indeed_raw)
    indeed_filtered = filter_normalized_offers(indeed_normalized, territoire, periode_jours)
    indeed_trends = compare_sources([], indeed_filtered, territoire=territoire, periode_jours=periode_jours)["indeed"]

    comparison = compare_sources(france_travail_offers, indeed_filtered, territoire=territoire, periode_jours=periode_jours)
    market_context = load_market_context_rows()

    territoire_options = sorted(
        {offer["territoire"] for offer in (normalize_offer(raw) for raw in raw_offers) if offer.get("territoire")},
        key=lambda value: value.lower(),
    )

    return {
        "territoire": territoire,
        "periode_jours": periode_jours,
        "indeed_path": str(indeed_path),
        "indeed_count": len(indeed_raw),
        "nombre_offres_ft": len(france_travail_offers),
        "nombre_offres_indeed": len(indeed_filtered),
        "france_travail": france_travail_trends,
        "indeed": indeed_trends,
        "comparison": comparison,
        "market_context": market_context,
        "territoire_options": territoire_options,
        "offers_ft": france_travail_offers[:20],
        "offers_indeed": indeed_filtered[:20],
    }


HTML_TEMPLATE = """
<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TrendRadar IA - Comparaison France Travail / Indeed</title>
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
    header h1 { margin: 0; font-size: 28px; line-height: 1.15; }
    header p { margin: 8px 0 0; color: rgba(255, 255, 255, 0.82); max-width: 920px; }
    .shell { padding: 18px 22px 28px; }
    .filters, .summary, .panel {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 10px;
      box-shadow: var(--shadow);
    }
    .filters {
      display: grid;
      grid-template-columns: 1fr 0.8fr 0.5fr auto;
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
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      align-items: start;
    }
    .panel { padding: 16px; }
    .panel h2 {
      margin: 0 0 12px;
      font-size: 18px;
    }
    .subhead {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 10px;
    }
    .subhead small { color: var(--muted); }
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
    .market-table, .offers-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }
    .market-table th, .market-table td,
    .offers-table th, .offers-table td {
      padding: 8px 6px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }
    .market-table th, .offers-table th {
      color: var(--muted);
      text-transform: uppercase;
      font-size: 12px;
    }
    .offer-columns {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
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
    .empty { color: var(--muted); padding: 10px 0; }
    .offer-title { font-weight: 700; margin-bottom: 4px; }
    .offer-company, .offer-desc { color: var(--muted); font-size: 13px; }
    .offer-desc {
      display: -webkit-box;
      -webkit-line-clamp: 3;
      -webkit-box-orient: vertical;
      overflow: hidden;
      max-width: 860px;
    }
    @media (max-width: 1100px) {
      .filters { grid-template-columns: 1fr 1fr; }
      .summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .grid, .offer-columns { grid-template-columns: 1fr; }
    }
    @media (max-width: 720px) {
      header, .shell { padding-left: 14px; padding-right: 14px; }
      .filters { grid-template-columns: 1fr; }
      .summary { grid-template-columns: 1fr; }
      .offers-table { display: block; overflow-x: auto; }
    }
  </style>
</head>
<body>
  <header>
    <h1>TrendRadar IA</h1>
    <p>Comparaison des offres France Travail et Indeed sur une même fenêtre temporelle et un même territoire.</p>
  </header>
  <main class="shell">
    <form class="filters" id="filters">
      <div class="field">
        <label for="territoire">Territoire</label>
        <input id="territoire" list="territoire-list" placeholder="Tous territoires">
        <datalist id="territoire-list"></datalist>
      </div>
      <div class="field">
        <label for="indeed">Indeed JSON</label>
        <input id="indeed" value="data/samples/offres_indeed_sample.json">
      </div>
      <div class="field">
        <label for="periode">Période en jours</label>
        <input id="periode" type="number" min="1" step="1" value="30">
      </div>
      <div class="field">
        <label>&nbsp;</label>
        <button type="submit">Actualiser</button>
      </div>
    </form>

    <section class="summary" id="summary"></section>

    <section class="grid">
      <section class="panel">
        <div class="subhead">
          <h2>France Travail</h2>
          <small id="ft-caption"></small>
        </div>
        <div class="bars" id="ft-competences"></div>
        <div style="height: 14px"></div>
        <div class="bars" id="ft-metiers"></div>
        <div style="height: 14px"></div>
        <div class="bars" id="ft-niveaux"></div>
        <div style="height: 14px"></div>
        <div class="bars" id="ft-contrats"></div>
      </section>

      <section class="panel">
        <div class="subhead">
          <h2>Indeed</h2>
          <small id="indeed-caption"></small>
        </div>
        <div class="bars" id="indeed-competences"></div>
        <div style="height: 14px"></div>
        <div class="bars" id="indeed-metiers"></div>
        <div style="height: 14px"></div>
        <div class="bars" id="indeed-niveaux"></div>
        <div style="height: 14px"></div>
        <div class="bars" id="indeed-contrats"></div>
      </section>
    </section>

    <section class="panel" style="margin-top:16px;">
      <div class="subhead">
        <h2>Comparaison</h2>
        <small id="comparison-caption"></small>
      </div>
      <div class="grid" style="grid-template-columns: repeat(4, minmax(0, 1fr));">
        <div class="metric"><div class="label">Écart offres</div><div class="value" id="delta-offers"></div><div class="caption">France Travail - Indeed</div></div>
        <div class="metric"><div class="label">Compétences communes</div><div class="value" id="common-skills-count"></div><div class="caption">termes partagés</div></div>
        <div class="metric"><div class="label">FT exclusives</div><div class="value" id="ft-exclusive-count"></div><div class="caption">compétences distinctes</div></div>
        <div class="metric"><div class="label">Indeed exclusives</div><div class="value" id="indeed-exclusive-count"></div><div class="caption">compétences distinctes</div></div>
      </div>
      <div style="height: 14px"></div>
      <div class="offer-columns">
        <div>
          <h3 style="margin:0 0 10px;">Compétences communes</h3>
          <div class="bars" id="common-skills"></div>
        </div>
        <div>
          <h3 style="margin:0 0 10px;">Compétences FT exclusives</h3>
          <div class="bars" id="ft-exclusive"></div>
        </div>
      </div>
      <div style="height: 14px"></div>
      <div>
        <h3 style="margin:0 0 10px;">Compétences Indeed exclusives</h3>
        <div class="bars" id="indeed-exclusive"></div>
      </div>
    </section>

    <section class="panel" style="margin-top:16px;">
      <div class="subhead">
        <h2>Offres filtrées</h2>
        <small id="offers-caption"></small>
      </div>
      <div class="offer-columns">
        <div>
          <h3 style="margin:0 0 10px;">France Travail</h3>
          <div style="overflow-x:auto; max-height: 72vh;">
            <table class="offers-table">
              <thead>
                <tr><th>Date</th><th>Offre</th><th>Territoire</th><th>Niveau</th><th>Contrat</th><th>Compétences</th></tr>
              </thead>
              <tbody id="offers-ft"></tbody>
            </table>
          </div>
        </div>
        <div>
          <h3 style="margin:0 0 10px;">Indeed</h3>
          <div style="overflow-x:auto; max-height: 72vh;">
            <table class="offers-table">
              <thead>
                <tr><th>Date</th><th>Offre</th><th>Territoire</th><th>Niveau</th><th>Contrat</th><th>Compétences</th></tr>
              </thead>
              <tbody id="offers-indeed"></tbody>
            </table>
          </div>
        </div>
      </div>
    </section>

    <section class="panel" style="margin-top:16px;">
      <div class="subhead">
        <h2>Contexte marché France Travail</h2>
        <small>Depuis le CSV agrégé T3 2025</small>
      </div>
      <table class="market-table" id="market-context"></table>
    </section>
  </main>

  <script>
    const summary = document.getElementById('summary');
    const territoryInput = document.getElementById('territoire');
    const indeedInput = document.getElementById('indeed');
    const periodInput = document.getElementById('periode');
    const territoryList = document.getElementById('territoire-list');
    const form = document.getElementById('filters');
    const offersCaption = document.getElementById('offers-caption');

    const ftCaption = document.getElementById('ft-caption');
    const indeedCaption = document.getElementById('indeed-caption');
    const comparisonCaption = document.getElementById('comparison-caption');
    const deltaOffers = document.getElementById('delta-offers');
    const commonSkillsCount = document.getElementById('common-skills-count');
    const ftExclusiveCount = document.getElementById('ft-exclusive-count');
    const indeedExclusiveCount = document.getElementById('indeed-exclusive-count');
    const commonSkills = document.getElementById('common-skills');
    const ftExclusive = document.getElementById('ft-exclusive');
    const indeedExclusive = document.getElementById('indeed-exclusive');

    const ftCompetences = document.getElementById('ft-competences');
    const ftMetiers = document.getElementById('ft-metiers');
    const ftNiveaux = document.getElementById('ft-niveaux');
    const ftContrats = document.getElementById('ft-contrats');
    const indeedCompetences = document.getElementById('indeed-competences');
    const indeedMetiers = document.getElementById('indeed-metiers');
    const indeedNiveaux = document.getElementById('indeed-niveaux');
    const indeedContrats = document.getElementById('indeed-contrats');
    const offersFt = document.getElementById('offers-ft');
    const offersIndeed = document.getElementById('offers-indeed');
    const marketContext = document.getElementById('market-context');

    function escapeHtml(text) {
      return String(text ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
    }

    function renderMetricRow(container, label, value, caption) {
      container.innerHTML += `
        <div class="metric">
          <div class="label">${label}</div>
          <div class="value">${value}</div>
          <div class="caption">${caption}</div>
        </div>
      `;
    }

    function renderSummary(state) {
      summary.innerHTML = '';
      renderMetricRow(summary, 'Offres FT', state.nombre_offres_ft, `${state.periode_jours} jours`);
      renderMetricRow(summary, 'Offres Indeed', state.nombre_offres_indeed, `${state.indeed_count} chargées`);
      renderMetricRow(summary, 'Écart', state.comparison ? state.comparison.comparaison.ecart_nombre_offres : 0, 'France Travail - Indeed');
      renderMetricRow(summary, 'Contexte', state.market_context.length, 'lignes T3 2025');
      ftCaption.textContent = state.territoire ? `Territoire ${state.territoire}` : 'Tous territoires';
      indeedCaption.textContent = state.indeed_path;
      comparisonCaption.textContent = state.territoire ? `Comparaison sur ${state.territoire}` : 'Comparaison globale';
      offersCaption.textContent = `${state.offers_ft.length} FT / ${state.offers_indeed.length} Indeed affichées`;
    }

    function renderBars(container, data, emptyLabel) {
      const entries = Object.entries(data || {});
      if (!entries.length) {
        container.innerHTML = `<div class="empty">${emptyLabel}</div>`;
        return;
      }
      const max = Math.max(...entries.map(([, count]) => count));
      container.innerHTML = entries.slice(0, 12).map(([label, count]) => {
        const width = max ? Math.max(8, (count / max) * 100) : 0;
        return `
          <div>
            <div class="bar-row">
              <div class="bar-label" title="${escapeHtml(label)}">${escapeHtml(label)}</div>
              <div class="bar-value">${count}</div>
            </div>
            <div class="bar-track"><div class="bar-fill" style="width:${width}%"></div></div>
          </div>
        `;
      }).join('');
    }

    function renderComparison(state) {
      const comparison = state.comparison;
      if (!comparison) {
        deltaOffers.textContent = '0';
        commonSkillsCount.textContent = '0';
        ftExclusiveCount.textContent = '0';
        indeedExclusiveCount.textContent = '0';
        commonSkills.innerHTML = '<div class="empty">Aucune comparaison disponible.</div>';
        ftExclusive.innerHTML = '<div class="empty">Aucune comparaison disponible.</div>';
        indeedExclusive.innerHTML = '<div class="empty">Aucune comparaison disponible.</div>';
        return;
      }
      deltaOffers.textContent = comparison.comparaison.ecart_nombre_offres;
      commonSkillsCount.textContent = Object.keys(comparison.comparaison.competences_communes || {}).length;
      ftExclusiveCount.textContent = Object.keys(comparison.comparaison.competences_fr_exclusives || {}).length;
      indeedExclusiveCount.textContent = Object.keys(comparison.comparaison.competences_indeed_exclusives || {}).length;
      renderBars(commonSkills, comparison.comparaison.competences_communes || {}, 'Aucune compétence commune');
      renderBars(ftExclusive, comparison.comparaison.competences_fr_exclusives || {}, 'Aucune compétence FT exclusive');
      renderBars(indeedExclusive, comparison.comparaison.competences_indeed_exclusives || {}, 'Aucune compétence Indeed exclusive');
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

    function renderOffers(container, offers) {
      if (!offers.length) {
        container.innerHTML = '<tr><td colspan="6" class="empty">Aucune offre ne correspond aux filtres.</td></tr>';
        return;
      }
      container.innerHTML = offers.map(offer => {
        const competences = (offer.competences || []).map(c => `<span class="chip">${escapeHtml(c)}</span>`).join(' ');
        const description = offer.description ? escapeHtml(offer.description) : '<span class="empty">Aucune description</span>';
        return `
          <tr>
            <td>${escapeHtml(offer.date || '')}</td>
            <td>
              <div class="offer-title">${escapeHtml(offer.intitule || offer.titre || offer.metier || '')}</div>
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
      if (indeedInput.value.trim()) params.set('indeed', indeedInput.value.trim());
      params.set('periode', periodInput.value || '30');
      const response = await fetch(`/api/state?${params.toString()}`);
      if (!response.ok) throw new Error('Erreur lors du chargement des données');
      const state = await response.json();
      renderSummary(state);
      renderBars(ftCompetences, state.france_travail.competences || {}, 'Aucune compétence FT');
      renderBars(ftMetiers, state.france_travail.metiers || {}, 'Aucun métier FT');
      renderBars(ftNiveaux, state.france_travail.niveau || {}, 'Aucun niveau FT');
      renderBars(ftContrats, state.france_travail.contrats || {}, 'Aucun contrat FT');
      renderBars(indeedCompetences, state.indeed.competences || {}, 'Aucune compétence Indeed');
      renderBars(indeedMetiers, state.indeed.metiers || {}, 'Aucun métier Indeed');
      renderBars(indeedNiveaux, state.indeed.niveau || {}, 'Aucun niveau Indeed');
      renderBars(indeedContrats, state.indeed.contrats || {}, 'Aucun contrat Indeed');
      renderComparison(state);
      renderOffers(offersFt, state.offers_ft || []);
      renderOffers(offersIndeed, state.offers_indeed || []);
      renderMarketContext(state.market_context || []);
      populateTerritories(state.territoire_options || []);
    }

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      await loadState();
    });

    loadState().catch(err => {
      summary.innerHTML = `<div class="metric" style="grid-column:1/-1;border-color:var(--danger);color:var(--danger);"><div class="label">Erreur</div><div class="value">X</div><div class="caption">${escapeHtml(err.message)}</div></div>`;
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

    @app.get("/api/state")
    def api_state():
        territoire = request.args.get("territoire") or None
        indeed = request.args.get("indeed") or str(DEFAULT_INDEED_PATH)
        try:
            periode = int(request.args.get("periode", DEFAULT_PERIOD))
        except ValueError:
            periode = DEFAULT_PERIOD
        return jsonify(build_state(territoire, periode, Path(indeed)))

    return app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="France Travail / Indeed comparison dashboard.")
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
