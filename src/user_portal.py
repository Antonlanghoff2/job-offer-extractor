# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Private user portal for TrendRadar IA.

This module keeps the authenticated user space separate from the public
trend dashboards. It uses the repository's SQLite persistence helper instead
of adding a heavier ORM/auth stack that is not installed in the current
environment.
"""

from __future__ import annotations

import functools
import json
import os
import re
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Dict, List, Optional, Tuple

from flask import Blueprint, current_app, g, redirect, render_template, render_template_string, request, session, send_file, url_for
from markupsafe import escape
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from src.db import execute, fetch_all, fetch_one, init_app as init_db_teardown, init_db, transaction, utcnow_iso
from src.offer_normalization import normalize_text
from src.matching.weights import DEFAULT_MATCHING_WEIGHTS, MATCHING_WEIGHT_KEYS, validate_matching_weights
from src.services.cv_parser import parse_cv_file
from src.services.formation_recommendation import build_recommendation_context
from src.services.matching_service import compute_match, normalize_skill_name
from src.services.offer_repository import get_available_territories, load_normalized_offers
from src.cache_reader import (
    get_precomputed_offers,
    get_precomputed_matches,
    get_precomputed_trends,
    get_territory_options as get_cached_territory_options,
    get_cache_status,
    has_precomputed_data,
    get_last_refresh_time,
)
from src.presentation.offer_view_model import (
    CACHE_SCHEMA_VERSION,
    OfferViewModel,
    build_match_view_model,
    build_offer_view_model,
    debug_offer_payload,
    is_debug_mode,
    normalize_criterion_scores,
    resolve_offer_location,
    resolve_offer_title,
    resolve_offer_url,
)

try:  # pragma: no cover - imported by Flask when installed
    from flask import flash
except Exception:  # pragma: no cover
    def flash(message: str, category: str = "message") -> None:
        session.setdefault("_flashes", []).append((category, message))


user_portal_bp = Blueprint("user_portal", __name__)

UPLOAD_FOLDER_NAME = "uploads"
CV_FOLDER_NAME = "cv"
ALLOWED_EXTENSIONS = {".pdf", ".docx"}
DEFAULT_MAX_UPLOAD_BYTES = 8 * 1024 * 1024
DEFAULT_COMPATIBILITY_THRESHOLD = 60
DEFAULT_LIMIT = 20
MAX_CARD_COUNT = 50

REMOTE_OPTIONS = (
    ("indifferent", "Indifférent"),
    ("presentiel", "Présentiel"),
    ("hybride", "Hybride"),
    ("teletravail", "Télétravail"),
)
CONTRACT_OPTIONS = (
    ("", "Indifférent"),
    ("CDI", "CDI"),
    ("CDD", "CDD"),
    ("Alternance", "Alternance"),
    ("Stage", "Stage"),
    ("Freelance", "Freelance"),
)
SKILL_LEVELS = ("debutant", "intermediaire", "avance", "expert")
SOURCES = ("manual", "cv")

BASE_TEMPLATE = """
<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ title }} - TrendRadar IA</title>
  <style>
    :root {
      --bg: #eef3f8;
      --surface: #ffffff;
      --surface-soft: #f5f8fc;
      --text: #142033;
      --muted: #5b6b80;
      --line: #d8e2ec;
      --accent: #1d63d8;
      --accent-2: #0d8f8a;
      --danger: #bb3e3e;
      --success: #13795b;
      --shadow: 0 14px 34px rgba(20, 32, 51, 0.09);
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; padding: 0; }
    body {
      background: linear-gradient(180deg, #edf3f9 0%, #f7f9fc 100%);
      color: var(--text);
      font-family: Inter, "Segoe UI", system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
    }
    a { color: inherit; }
    .site-header {
      background: linear-gradient(135deg, #102843 0%, #1b4d84 60%, #16667f 100%);
      color: white;
      box-shadow: 0 10px 24px rgba(16, 40, 67, 0.18);
    }
    .site-header__inner {
      max-width: 1320px;
      margin: 0 auto;
      padding: 20px 20px 16px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
    }
    .brand__link {
      color: white;
      text-decoration: none;
      font-size: 1.35rem;
      font-weight: 800;
      letter-spacing: 0.01em;
    }
    .brand__subtitle {
      margin: 4px 0 0;
      color: rgba(255, 255, 255, 0.82);
      font-size: 0.95rem;
    }
    .header-actions {
      display: flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    .main-nav {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    .main-nav__link {
      text-decoration: none;
      color: rgba(255, 255, 255, 0.92);
      border: 1px solid rgba(255, 255, 255, 0.24);
      border-radius: 999px;
      padding: 9px 14px;
      font-size: 0.95rem;
      font-weight: 700;
      transition: background-color 0.2s ease, color 0.2s ease, border-color 0.2s ease;
    }
    .main-nav__link:hover,
    .main-nav__link.active {
      background: rgba(255, 255, 255, 0.15);
      border-color: rgba(255, 255, 255, 0.45);
    }
    .account-menu {
      position: relative;
    }
    .account-menu > summary {
      list-style: none;
    }
    .account-menu > summary::-webkit-details-marker {
      display: none;
    }
    .account-menu__summary {
      cursor: pointer;
      user-select: none;
      color: white;
      border: 1px solid rgba(255, 255, 255, 0.28);
      border-radius: 999px;
      padding: 9px 14px;
      font-size: 0.95rem;
      font-weight: 800;
      background: rgba(255, 255, 255, 0.06);
    }
    .account-menu__summary::after {
      content: '▾';
      display: inline-block;
      margin-left: 8px;
      font-size: 0.72rem;
      opacity: 0.8;
    }
    .account-menu[open] .account-menu__summary,
    .account-menu__summary:hover {
      background: rgba(255, 255, 255, 0.15);
      border-color: rgba(255, 255, 255, 0.45);
    }
    .account-menu__panel {
      position: absolute;
      right: 0;
      top: calc(100% + 10px);
      min-width: 220px;
      display: grid;
      padding: 8px;
      gap: 4px;
      background: rgba(16, 40, 67, 0.98);
      border: 1px solid rgba(255, 255, 255, 0.16);
      border-radius: 16px;
      box-shadow: 0 18px 38px rgba(7, 20, 34, 0.28);
      z-index: 20;
    }
    .account-menu__panel a {
      color: white;
      text-decoration: none;
      padding: 10px 12px;
      border-radius: 10px;
      font-size: 0.94rem;
      font-weight: 700;
    }
    .account-menu__panel a:hover {
      background: rgba(255, 255, 255, 0.12);
    }
    .page-shell {
      max-width: 1320px;
      margin: 0 auto;
      padding: 22px 20px 42px;
    }
    .matching-weights {
      grid-column: 1 / -1;
      margin-top: 14px;
      border: 1px solid rgba(29, 99, 216, 0.12);
      background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
      padding: 16px;
      border-radius: 16px;
    }
    .matching-weights__head {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 16px;
      margin-bottom: 10px;
    }
    .matching-weights__head h2 { margin: 0 0 4px; font-size: 1.05rem; }
    .matching-weights__total { text-align: right; font-size: 0.92rem; color: var(--muted); }
    .matching-weights__total strong { display: block; margin-top: 4px; color: var(--text); font-size: 1.15rem; }
    .matching-weights__message { margin: 10px 0 14px; }
    .matching-weights__grid { display: grid; gap: 12px; }
    .weight-row { display: grid; gap: 8px; padding: 12px; border: 1px solid var(--line); border-radius: 14px; background: white; }
    .weight-row__label { display: flex; justify-content: space-between; gap: 10px; align-items: baseline; }
    .weight-row__label label { font-weight: 800; color: var(--text); }
    .weight-row__label strong { color: var(--accent); font-variant-numeric: tabular-nums; }
    .weight-row__controls { display: grid; grid-template-columns: minmax(0, 1fr) 92px; gap: 10px; align-items: center; }
    .weight-row__controls input[type="range"] { width: 100%; }
    .weight-row__controls input[type="number"] { width: 100%; padding: 10px 12px; border: 1px solid var(--line); border-radius: 10px; font: inherit; }
    .matching-weights__actions { margin-top: 14px; display: flex; justify-content: flex-end; }
    .profile-edit-grid { display: grid; gap: 16px; }
    .profile-edit-list { margin-top: 16px; }
    .profile-edit-list .panel { margin-bottom: 0; }
    .profile-edit-list .panel + .panel { margin-top: 16px; }
    .panel, .status, .card, .list-item {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 10px;
      box-shadow: var(--shadow);
    }
    .panel { padding: 16px; margin-bottom: 16px; }
    .status {
      border-left: 4px solid var(--accent);
      padding: 12px 14px;
      margin-bottom: 16px;
    }
    .status.error { border-left-color: var(--danger); background: #fff7f7; color: var(--danger); }
    .status.success { border-left-color: var(--success); background: #f5fcf8; color: var(--success); }
    .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
    .grid-3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
    .field { display: grid; gap: 6px; margin-bottom: 12px; }
    .field label {
      font-size: 12px;
      font-weight: 800;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.02em;
    }
    .field input, .field select, .field textarea {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px 12px;
      font: inherit;
      background: white;
      color: var(--text);
    }
    .field textarea { min-height: 112px; resize: vertical; }
    .actions { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      padding: 10px 14px;
      border-radius: 8px;
      border: 0;
      background: var(--accent);
      color: white;
      text-decoration: none;
      font-weight: 700;
      cursor: pointer;
    }
    .btn.secondary { background: #e8eef5; color: var(--text); }
    .btn.danger { background: var(--danger); }
    .muted { color: var(--muted); }
    .cards { display: grid; gap: 12px; }
    .card { padding: 14px; }
    .card h3 { margin: 0 0 6px; }
    .meta { color: var(--muted); font-size: 13px; display: flex; flex-wrap: wrap; gap: 10px; margin: 8px 0; }
    .chips { display: flex; flex-wrap: wrap; gap: 6px; }
    .chip {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 4px 9px;
      background: #f7faff;
      font-size: 12px;
      font-weight: 700;
    }
    table { width: 100%; border-collapse: collapse; }
    th, td { padding: 8px 6px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
    th { color: var(--muted); text-transform: uppercase; font-size: 11px; letter-spacing: 0.02em; }
    .small { font-size: 13px; }
    .auth-wrap { max-width: 560px; margin: 0 auto; }
    .dash-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 16px; }
    .metric { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 14px; box-shadow: var(--shadow); }
    .metric .label { font-size: 12px; font-weight: 800; color: var(--muted); text-transform: uppercase; }
    .metric .value { font-size: 28px; font-weight: 900; margin-top: 8px; }
    .offer-grid { display: grid; gap: 12px; }
    .offer-card { border: 1px solid var(--line); border-radius: 10px; background: white; padding: 14px; box-shadow: 0 8px 22px rgba(19, 32, 51, 0.05); }
    .offer-title { margin: 0 0 4px; font-size: 16px; font-weight: 800; }
    .explain { margin-top: 10px; padding: 10px 12px; background: #f7fbff; border: 1px solid var(--line); border-radius: 8px; }
    .pairs { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
    @media (max-width: 920px) {
      .grid, .grid-3, .pairs, .dash-grid { grid-template-columns: 1fr; }
    }
    .score-ring {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 64px;
      height: 64px;
      border-radius: 50%;
      font-size: 1.25rem;
      font-weight: 800;
      flex-shrink: 0;
      color: white;
    }
    .score-ring--high { background: linear-gradient(135deg, #13795b, #1a9d74); }
    .score-ring--mid { background: linear-gradient(135deg, #c78a1e, #e0a82e); }
    .score-ring--low { background: linear-gradient(135deg, #bb3e3e, #d45555); }
    .score-detail-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
      gap: 10px;
      margin: 12px 0;
    }
    .score-bar-item {
      display: grid;
      gap: 4px;
    }
    .score-bar-item__head {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      font-size: 0.85rem;
    }
    .score-bar-item__label {
      font-weight: 700;
      color: var(--text);
    }
    .score-bar-item__value {
      font-weight: 800;
      font-variant-numeric: tabular-nums;
      color: var(--muted);
    }
    .score-bar-track {
      height: 8px;
      border-radius: 999px;
      background: #e8eef5;
      overflow: hidden;
    }
    .score-bar-fill {
      height: 100%;
      border-radius: inherit;
      transition: width 0.3s ease;
    }
    .score-bar-fill--high { background: linear-gradient(90deg, #13795b, #1a9d74); }
    .score-bar-fill--mid { background: linear-gradient(90deg, #c78a1e, #e0a82e); }
    .score-bar-fill--low { background: linear-gradient(90deg, #bb3e3e, #d45555); }
    .score-bar-fill--absent { background: #d8e2ec; }
    .skill-tag {
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 4px 10px;
      font-size: 0.82rem;
      font-weight: 700;
    }
    .skill-tag--match {
      background: #e8f7f0;
      color: #13795b;
      border: 1px solid #b8e4d0;
    }
    .skill-tag--missing {
      background: #fdf0f0;
      color: #bb3e3e;
      border: 1px solid #f0c4c4;
    }
    .offer-card__header {
      display: flex;
      align-items: flex-start;
      gap: 16px;
      margin-bottom: 12px;
    }
    .offer-card__header-text {
      flex: 1;
      min-width: 0;
    }
    .offer-card__detail-link {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      color: var(--accent);
      font-weight: 700;
      font-size: 0.9rem;
      text-decoration: none;
      margin-top: 8px;
    }
    .offer-card__detail-link:hover {
      text-decoration: underline;
    }
    .criterion-reason {
      font-size: 0.82rem;
      color: var(--muted);
      font-style: italic;
    }
    @media (max-width: 1100px) {
      .site-header__inner {
        align-items: flex-start;
      }
      .header-actions {
        width: 100%;
        justify-content: space-between;
      }
      .account-menu__panel {
        right: auto;
        left: 0;
      }
    }
    @media (max-width: 720px) {
      .header-actions {
        justify-content: flex-start;
      }
      .main-nav {
        width: 100%;
        justify-content: flex-start;
      }
      .account-menu {
        width: 100%;
      }
      .account-menu__summary {
        width: 100%;
        text-align: center;
      }
      .account-menu__panel {
        width: 100%;
        position: static;
        margin-top: 10px;
      }
    }
  </style>
</head>
<body>
  <header class="site-header">
    <div class="site-header__inner">
      <div class="brand">
        <a class="brand__link" href="{{ url_for('index') }}">TrendRadar IA</a>
        <p class="brand__subtitle">Espace utilisateur privé, recommandations et import contrôlé du CV</p>
      </div>
      <div class="header-actions">
        <nav class="main-nav" aria-label="Navigation principale">
          <a class="main-nav__link{% if active_page == 'search' %} active{% endif %}" href="{{ url_for('index') }}">Recherche d'offres</a>
          <a class="main-nav__link{% if active_page == 'territory_trends' %} active{% endif %}" href="{{ url_for('territory_trends') }}">Tendances par territoire</a>
        </nav>
        <details class="account-menu">
          <summary class="account-menu__summary">Mon compte</summary>
          <div class="account-menu__panel" role="menu" aria-label="Menu Mon compte">
            <a role="menuitem" href="{{ url_for('user_portal.profile') }}">Mon profil</a>
            <a role="menuitem" href="{{ url_for('user_portal.upload_cv') }}">Mon CV</a>
            <a role="menuitem" href="{{ url_for('user_portal.recommendations') }}">Mes offres</a>
            <a role="menuitem" href="{{ url_for('user_portal.training_recommendation') }}">Recommandation formation</a>
            <a role="menuitem" href="{{ url_for('user_portal.dashboard') }}">Mon tableau de bord</a>
            <a role="menuitem" href="{{ url_for('user_portal.logout') }}">Déconnexion</a>
          </div>
        </details>
      </div>
    </div>
  </header>
  <main class="page-shell">
    {% if message %}
    <div class="status {{ message_category or '' }}">{{ message }}</div>
    {% endif %}
    {{ content|safe }}
  </main>
  <script src="{{ url_for('static', filename='js/matching_weights.js') }}"></script>
</body>
</html>
"""


def _ensure_app_config(app) -> None:
    app.config.setdefault("MAX_CONTENT_LENGTH", DEFAULT_MAX_UPLOAD_BYTES)
    app.config.setdefault(
        "UPLOAD_FOLDER",
        str(Path(app.instance_path) / UPLOAD_FOLDER_NAME),
    )
    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")
    secret_key = app.config.get("SECRET_KEY") or os.getenv("SECRET_KEY", "trendradar-dev-secret")
    app.config["SECRET_KEY"] = secret_key
    app.secret_key = secret_key


def _db_path() -> Path:
    return Path(current_app.config.get("UPLOAD_FOLDER")).parent / "trendradar.sqlite"


def _uploads_root() -> Path:
    root = Path(current_app.config.get("UPLOAD_FOLDER"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _current_user_id() -> Optional[int]:
    user_id = session.get("user_id")
    if isinstance(user_id, int):
        return user_id
    if isinstance(user_id, str) and user_id.isdigit():
        return int(user_id)
    return None


def _get_user(user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    user_id = user_id if user_id is not None else _current_user_id()
    if not user_id:
        return None
    row = fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))
    return dict(row) if row else None


def _login_user(user_id: int) -> None:
    session.clear()
    session["user_id"] = int(user_id)
    session["csrf_token"] = uuid.uuid4().hex


def _logout_user() -> None:
    session.pop("user_id", None)
    session.pop("csrf_token", None)
    session.pop("pending_cv_import", None)


def _require_login() -> Optional[int]:
    user_id = _current_user_id()
    if not user_id:
        flash("Connectez-vous pour accéder à cet espace.", "error")
        return None
    return user_id


def login_required(view: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(view)
    def wrapper(*args: Any, **kwargs: Any):
        user_id = _require_login()
        if user_id is None:
            return redirect(url_for("user_portal.login", next=request.path))
        g.current_user = _get_user(user_id)
        return view(*args, **kwargs)

    return wrapper


def _csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = uuid.uuid4().hex
        session["csrf_token"] = token
    return str(token)


def _check_csrf() -> bool:
    if request.method != "POST":
        return True
    submitted = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    return bool(submitted and submitted == session.get("csrf_token"))


def _csrf_error() -> Optional[str]:
    return None if _check_csrf() else "Jeton CSRF invalide ou manquant."


def _normalize_string(value: object) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalize_lookup(value: object) -> str:
    return normalize_text(value)


def _parse_int(value: object, minimum: Optional[int] = None, maximum: Optional[int] = None) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    if minimum is not None and parsed < minimum:
        return None
    if maximum is not None and parsed > maximum:
        return None
    return parsed


def _parse_float(value: object) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def _parse_date(value: object) -> Optional[str]:
    text = _normalize_string(value)
    if not text:
        return None
    for candidate in (text, text.replace("/", "-"), text.replace("Z", "")):
        try:
            return datetime.fromisoformat(candidate).date().isoformat()
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def _allowed_file(filename: str) -> bool:
    return Path(filename.lower()).suffix in ALLOWED_EXTENSIONS


def _safe_upload_path(user_id: int, filename: str) -> Path:
    safe_name = secure_filename(filename) or f"cv-{uuid.uuid4().hex}{Path(filename).suffix.lower()}"
    user_dir = _uploads_root() / CV_FOLDER_NAME / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir / f"{uuid.uuid4().hex}-{safe_name}"


def _load_local_offers() -> List[Dict[str, Any]]:
    from src.web_app import load_raw_offers

    try:
        return load_raw_offers()
    except Exception:
        return []


def _normalize_offer(raw_offer: Dict[str, Any]) -> Dict[str, Any]:
    from src.services.offer_normalization import normalize_offer_for_matching

    return normalize_offer_for_matching(raw_offer, source=raw_offer.get("source") or "France Travail")


def _offer_fallback_url(offer: Dict[str, Any], offer_identifier: Optional[str] = None) -> Optional[str]:
    url = offer.get("url_originale") or offer.get("url")
    if url:
        return str(url)
    identifier = offer_identifier or offer.get("source_identifier") or offer.get("id") or offer.get("id_offre")
    if identifier:
        identifier_text = str(identifier)
        source_name = normalize_text(offer.get("source") or "")
        if source_name in {"", "france travail", "france_travail", "francetravail"}:
            return f"https://candidat.francetravail.fr/offres/recherche/detail/{identifier_text}"
        return url_for("user_portal.recommendation_detail", offer_id=identifier_text)
    return None


def _assemble_profile(user_id: int) -> Dict[str, Any]:
    profile_row = fetch_one("SELECT * FROM user_profiles WHERE user_id = ?", (user_id,))
    desired_jobs = [
        {
            "id": row["id"],
            "job_title": row["job_title"],
            "normalized_job_title": row["normalized_job_title"],
        }
        for row in fetch_all("SELECT * FROM desired_jobs WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    ]
    skills = [
        dict(row)
        for row in fetch_all(
            """
            SELECT us.*, s.name, s.normalized_name
            FROM user_skills us
            JOIN skills s ON s.id = us.skill_id
            WHERE us.user_id = ?
            ORDER BY s.normalized_name ASC
            """,
            (user_id,),
        )
    ]
    diplomas = [dict(row) for row in fetch_all("SELECT * FROM diplomas WHERE user_id = ? ORDER BY graduation_year DESC, created_at DESC", (user_id,))]
    experiences = [dict(row) for row in fetch_all("SELECT * FROM experiences WHERE user_id = ? ORDER BY start_date DESC, created_at DESC", (user_id,))]
    experience_skills = defaultdict(list)
    for row in fetch_all(
        """
        SELECT es.experience_id, s.name
        FROM experience_skills es
        JOIN skills s ON s.id = es.skill_id
        JOIN experiences e ON e.id = es.experience_id
        WHERE e.user_id = ?
        """,
        (user_id,),
    ):
        experience_skills[int(row["experience_id"])].append(row["name"])
    cv_row = fetch_one("SELECT * FROM user_cvs WHERE user_id = ?", (user_id,))
    if profile_row:
        profile = dict(profile_row)
    else:
        profile = {
            "first_name": "",
            "last_name": "",
            "city": "",
            "postal_code": "",
            "department": "",
            "search_radius_km": None,
            "contract_preference": "",
            "remote_preference": "indifferent",
            "minimum_salary": None,
            "availability": "",
            "summary": "",
        }
    profile.update(
        {
            "desired_jobs": desired_jobs,
            "skills": skills,
            "diplomas": diplomas,
            "experiences": [
                {**experience, "skills": experience_skills.get(int(experience["id"]), [])}
                for experience in experiences
            ],
            "cv": dict(cv_row) if cv_row else None,
        }
    )
    return profile


def _skill_payload_from_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": row.get("name") or row.get("skill_name") or "",
        "normalized_name": row.get("normalized_name") or normalize_skill_name(row.get("name") or row.get("skill_name") or ""),
        "level": row.get("level") or "",
        "years_experience": row.get("years_experience"),
        "source": row.get("source") or "manual",
    }


def _format_skill_table_item(row: Dict[str, Any]) -> Dict[str, Any]:
    payload = _skill_payload_from_row(row)
    name = payload["name"] or payload["normalized_name"] or row.get("nom") or row.get("skill_name") or "Compétence sans nom"
    years_value = payload["years_experience"]
    if years_value in (None, ""):
        years_display = "—"
    else:
        try:
            years_display = str(round(float(years_value), 1)).rstrip("0").rstrip(".")
        except Exception:
            years_display = str(years_value)
    level = payload["level"] or "Niveau non renseigné"
    source = payload["source"] or "manual"
    return {
        **row,
        "name": name,
        "level": level,
        "years_experience": years_display,
        "source": source,
        "normalized_name": payload["normalized_name"] or normalize_skill_name(name),
    }


def _store_skill(user_id: int, name: str, level: Optional[str], years_experience: Optional[float], source: str) -> None:
    normalized = normalize_skill_name(name)
    if not normalized:
        return
    now = utcnow_iso()
    with transaction() as conn:
        skill_row = conn.execute("SELECT id, name FROM skills WHERE normalized_name = ?", (normalized,)).fetchone()
        if skill_row:
            skill_id = int(skill_row["id"])
            conn.execute(
                "UPDATE skills SET name = ?, updated_at = ? WHERE id = ?",
                (_normalize_string(name) or skill_row["name"], now, skill_id),
            )
        else:
            cursor = conn.execute(
                "INSERT INTO skills(name, normalized_name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (_normalize_string(name), normalized, now, now),
            )
            skill_id = int(cursor.lastrowid)
        existing = conn.execute(
            "SELECT id FROM user_skills WHERE user_id = ? AND skill_id = ? AND source = ?",
            (user_id, skill_id, source),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE user_skills SET level = ?, years_experience = ?, updated_at = ? WHERE id = ?",
                (_normalize_string(level), years_experience, now, int(existing["id"])),
            )
        else:
            conn.execute(
                """
                INSERT INTO user_skills(user_id, skill_id, level, years_experience, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, skill_id, _normalize_string(level), years_experience, source, now, now),
            )


def _update_desired_jobs(user_id: int, jobs: Iterable[str]) -> None:
    now = utcnow_iso()
    with transaction() as conn:
        conn.execute("DELETE FROM desired_jobs WHERE user_id = ?", (user_id,))
        for job_title in jobs:
            clean = _normalize_string(job_title)
            if not clean:
                continue
            conn.execute(
                """
                INSERT INTO desired_jobs(user_id, job_title, normalized_job_title, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, clean, _normalize_lookup(clean), now, now),
            )


def _parse_multi_values(raw_value: object) -> List[str]:
    if raw_value in (None, ""):
        return []
    values = []
    for part in re.split(r"[,\n;|]", str(raw_value)):
        text = _normalize_string(part)
        if text:
            values.append(text)
    return values


def _current_matching_weights() -> Dict[str, float]:
    stored = session.get("matching_weights")
    normalized, error = validate_matching_weights(stored) if isinstance(stored, dict) else (dict(DEFAULT_MATCHING_WEIGHTS), "")
    if error:
        return dict(DEFAULT_MATCHING_WEIGHTS)
    return normalized


def _save_matching_weights_from_form(form) -> Optional[str]:
    candidate = {key: form.get(f"matching_weights_{key}") for key in MATCHING_WEIGHT_KEYS}
    normalized, error = validate_matching_weights(candidate)
    if error:
        return error
    session["matching_weights"] = normalized
    return None


def _render_page(title: str, content: str, *, message: Optional[str] = None, message_category: Optional[str] = None, **context: Any):
    return render_template_string(
        BASE_TEMPLATE,
        title=title,
        content=content,
        message=message,
        message_category=message_category,
        csrf_token=_csrf_token,
        escape=escape,
        **context,
    )


def _auth_block(form_action: str, title: str, submit_label: str, next_url: str = "", error: Optional[str] = None) -> str:
    return render_template_string(
        """
        <section class="auth-wrap panel">
          <h2>{{ title }}</h2>
          {% if error %}<div class="status error">{{ error }}</div>{% endif %}
          <form method="post" action="{{ form_action }}">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            {% if next_url %}<input type="hidden" name="next" value="{{ next_url }}">{% endif %}
            <div class="field">
              <label for="email">Email</label>
              <input id="email" name="email" type="email" required>
            </div>
            <div class="field">
              <label for="password">Mot de passe</label>
              <input id="password" name="password" type="password" required>
            </div>
            <div class="actions">
              <button class="btn" type="submit">{{ submit_label }}</button>
            </div>
          </form>
          <p class="muted small">
            {% if form_action.endswith('/login') %}
            Pas encore de compte ? <a href="{{ url_for('user_portal.register') }}">Créer un compte</a>
            {% else %}
            Déjà inscrit ? <a href="{{ url_for('user_portal.login') }}">Se connecter</a>
            {% endif %}
          </p>
        </section>
        """,
        title=title,
        form_action=form_action,
        submit_label=submit_label,
        next_url=next_url,
        error=error,
        csrf_token=_csrf_token,
    )


def _profile_form(profile: Dict[str, Any], desired_jobs_text: str, matching_weights: Dict[str, float], matching_weights_error: Optional[str] = None) -> str:
    return render_template_string(
        """
        <section class="panel">
          <h2>Mon profil</h2>
          <form method="post" class="profile-edit-grid" data-matching-weights-form data-default-weights='{{ default_matching_weights|tojson }}'>
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <div class="grid">
              <div class="field"><label>Prénom</label><input name="first_name" value="{{ profile.first_name or '' }}"></div>
              <div class="field"><label>Nom</label><input name="last_name" value="{{ profile.last_name or '' }}"></div>
              <div class="field"><label>Ville</label><input name="city" value="{{ profile.city or '' }}"></div>
              <div class="field"><label>Code postal</label><input name="postal_code" value="{{ profile.postal_code or '' }}"></div>
              <div class="field"><label>Département</label><input name="department" value="{{ profile.department or '' }}"></div>
              <div class="field"><label>Rayon de recherche (km)</label><input name="search_radius_km" type="number" min="0" value="{{ profile.search_radius_km or '' }}"></div>
              <div class="field"><label>Type de contrat recherché</label>
                <select name="contract_preference">
                  {% for value, label in contract_options %}
                  <option value="{{ value }}" {% if (profile.contract_preference or '') == value %}selected{% endif %}>{{ label }}</option>
                  {% endfor %}
                </select>
              </div>
              <div class="field"><label>Préférence télétravail</label>
                <select name="remote_preference">
                  {% for value, label in remote_options %}
                  <option value="{{ value }}" {% if (profile.remote_preference or 'indifferent') == value %}selected{% endif %}>{{ label }}</option>
                  {% endfor %}
                </select>
              </div>
              <div class="field"><label>Salaire minimum</label><input name="minimum_salary" type="number" min="0" value="{{ profile.minimum_salary or '' }}"></div>
            </div>
            <div class="field"><label>Métiers recherchés</label><textarea name="desired_jobs">{{ desired_jobs_text }}</textarea></div>
            <div class="field"><label>Disponibilité</label><input name="availability" value="{{ profile.availability or '' }}"></div>
            <div class="field"><label>Présentation professionnelle</label><textarea name="summary">{{ profile.summary or '' }}</textarea></div>

            <section class="matching-weights" aria-labelledby="matching-weights-title">
              <div class="matching-weights__head">
                <div>
                  <h2 id="matching-weights-title">Personnaliser les critères de matching</h2>
                  <p class="muted">Ces pondérations s’appliquent aux pages Mes offres et Mon tableau de bord.</p>
                </div>
                <div class="matching-weights__total">
                  <span>Total des pondérations :</span>
                  <strong data-weights-total>100 %</strong>
                </div>
              </div>
              {% if matching_weights_error %}
              <div class="matching-weights__message alert alert--error" data-weights-message>{{ matching_weights_error }}</div>
              {% else %}
              <div class="matching-weights__message muted" data-weights-message>Le total des pondérations doit être égal à 100 %.</div>
              {% endif %}
              <div class="matching-weights__grid">
                {% set matching_weight_fields = [
                  ('competences', 'Compétences'),
                  ('metier', 'Métier ou intitulé'),
                  ('experience', 'Expérience'),
                  ('diplome', 'Diplôme'),
                  ('localisation', 'Localisation'),
                  ('contrat', 'Contrat'),
                  ('teletravail', 'Télétravail'),
                  ('salaire', 'Salaire')
                ] %}
                {% for key, label in matching_weight_fields %}
                {% set value = matching_weights[key] %}
                <div class="weight-row" data-weight-row data-weight-key="{{ key }}">
                  <div class="weight-row__label">
                    <label for="weight-{{ key }}">{{ label }}</label>
                    <strong><span data-weight-display="{{ key }}">{{ '%.0f'|format(value) }}</span> %</strong>
                  </div>
                  <div class="weight-row__controls">
                    <input id="weight-{{ key }}" type="range" min="0" max="100" step="1" value="{{ '%.0f'|format(value) }}" data-weight-range="{{ key }}">
                    <input type="number" min="0" max="100" step="1" value="{{ '%.0f'|format(value) }}" data-weight-number="{{ key }}" name="matching_weights_{{ key }}">
                  </div>
                </div>
                {% endfor %}
              </div>
              <div class="matching-weights__actions">
                <button type="button" class="btn secondary" data-weights-reset>Réinitialiser les pondérations</button>
              </div>
            </section>

            <div class="actions"><button class="btn" type="submit" data-search-submit>Enregistrer</button></div>
          </form>
        </section>
        """,
        profile=profile,
        desired_jobs_text=desired_jobs_text,
        remote_options=REMOTE_OPTIONS,
        contract_options=CONTRACT_OPTIONS,
        matching_weights=matching_weights,
        matching_weights_error=matching_weights_error,
        default_matching_weights=DEFAULT_MATCHING_WEIGHTS,
        csrf_token=_csrf_token,
    )


def _profile_privacy_block(profile: Dict[str, Any]) -> str:
    return render_template_string(
        """
        <section class="panel privacy-panel">
          <div class="profile-summary__header">
            <div>
              <h2>Vie privée et RGPD</h2>
              <p class="muted">Vous pouvez exporter vos données personnelles ou supprimer définitivement votre compte et toutes les données associées.</p>
            </div>
          </div>
          <div class="actions privacy-panel__actions">
            <a class="btn secondary" href="{{ url_for('user_portal.export_data') }}">Exporter mes données</a>
            <form method="post" action="{{ url_for('user_portal.delete_account') }}" onsubmit="return confirm('Supprimer définitivement votre compte et toutes vos données ?');">
              <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
              <button class="btn danger" type="submit">Supprimer mon compte</button>
            </form>
          </div>
          <p class="muted">Sont supprimés: profil, compétences, formations, expériences, CV importé et correspondances enregistrées.</p>
        </section>
        """
    )


def _profile_summary_block(profile: Dict[str, Any]) -> str:
    return render_template_string(
        """
        <section class="panel profile-summary">
          <div class="profile-summary__header">
            <div>
              <h2>Mes compétences et mes formations</h2>
              <p class="muted">Résumé en lecture seule des éléments déjà enregistrés.</p>
            </div>
          </div>
          <div class="grid">
            <div class="profile-summary__box">
              <h3>Compétences</h3>
              {% if profile.skills %}
              <div class="chips">
                {% for skill in profile.skills %}
                <span class="chip">{{ skill.name or skill.normalized_name }}</span>
                {% endfor %}
              </div>
              {% else %}
              <div class="muted">Aucune compétence enregistrée.</div>
              {% endif %}
            </div>
            <div class="profile-summary__box">
              <h3>Formations</h3>
              {% if profile.diplomas %}
              <ul class="profile-summary__list">
                {% for diploma in profile.diplomas %}
                <li>
                  <strong>{{ diploma.title }}</strong>
                  <span class="muted">{{ diploma.level or 'Niveau non renseigné' }}{% if diploma.institution %} · {{ diploma.institution }}{% endif %}</span>
                </li>
                {% endfor %}
              </ul>
              {% else %}
              <div class="muted">Aucune formation enregistrée.</div>
              {% endif %}
            </div>
          </div>
        </section>
        """,
        profile=profile,
    )


def _list_section(title: str, items: List[Dict[str, Any]], columns: List[Tuple[str, str]], add_url: str, empty_label: str) -> str:
    return render_template_string(
        """
        <section class="panel">
          <div class="actions" style="justify-content: space-between;">
            <h2 style="margin: 0;">{{ title }}</h2>
            <a class="btn secondary" href="{{ add_url }}">Ajouter</a>
          </div>
          {% if items %}
          <table>
            <thead>
              <tr>
                {% for header, _ in columns %}<th>{{ header }}</th>{% endfor %}
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {% for item in items %}
              <tr>
                {% for _, key in columns %}
                <td>{{ item[key] if item.get(key) not in (None, '') else '' }}</td>
                {% endfor %}
                <td class="actions">
                  <a class="btn secondary" href="{{ item['_edit_url'] }}">Modifier</a>
                  <form method="post" action="{{ item['_delete_url'] }}" onsubmit="return confirm('Supprimer cet élément ?');">
                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                    <button class="btn danger" type="submit">Supprimer</button>
                  </form>
                </td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
          {% else %}
          <div class="muted">{{ empty_label }}</div>
          {% endif %}
        </section>
        """,
        title=title,
        items=items,
        columns=columns,
        add_url=add_url,
        empty_label=empty_label,
        csrf_token=_csrf_token,
    )


def _validate_required_csrf() -> Optional[str]:
    return _csrf_error()


def _create_or_update_user(email: str, password: str) -> int:
    now = utcnow_iso()
    password_hash = generate_password_hash(password)
    with transaction() as conn:
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            raise ValueError("Un compte existe déjà avec cet email.")
        cursor = conn.execute(
            "INSERT INTO users(email, password_hash, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (email, password_hash, now, now),
        )
        return int(cursor.lastrowid)


def _authenticate_user(email: str, password: str) -> Optional[int]:
    row = fetch_one("SELECT * FROM users WHERE email = ?", (email,))
    if not row:
        return None
    if not check_password_hash(row["password_hash"], password):
        return None
    execute("UPDATE users SET updated_at = ? WHERE id = ?", (utcnow_iso(), row["id"]))
    return int(row["id"])


def _save_profile(user_id: int) -> None:
    now = utcnow_iso()
    fields = {
        "first_name": _normalize_string(request.form.get("first_name")),
        "last_name": _normalize_string(request.form.get("last_name")),
        "city": _normalize_string(request.form.get("city")),
        "postal_code": _normalize_string(request.form.get("postal_code")),
        "department": _normalize_string(request.form.get("department")),
        "search_radius_km": _parse_int(request.form.get("search_radius_km"), 0, 500),
        "contract_preference": _normalize_string(request.form.get("contract_preference")),
        "remote_preference": request.form.get("remote_preference") or "indifferent",
        "minimum_salary": _parse_int(request.form.get("minimum_salary"), 0),
        "availability": _normalize_string(request.form.get("availability")),
        "summary": _normalize_string(request.form.get("summary")),
    }
    desired_jobs = _parse_multi_values(request.form.get("desired_jobs"))
    with transaction() as conn:
        existing = conn.execute("SELECT id FROM user_profiles WHERE user_id = ?", (user_id,)).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE user_profiles
                SET first_name = ?, last_name = ?, city = ?, postal_code = ?, department = ?,
                    search_radius_km = ?, contract_preference = ?, remote_preference = ?, minimum_salary = ?, availability = ?,
                    summary = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (
                    fields["first_name"],
                    fields["last_name"],
                    fields["city"],
                    fields["postal_code"],
                    fields["department"],
                    fields["search_radius_km"],
                    fields["contract_preference"],
                    fields["remote_preference"],
                    fields["minimum_salary"],
                    fields["availability"],
                    fields["summary"],
                    now,
                    user_id,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO user_profiles(
                    user_id, first_name, last_name, city, postal_code, department,
                    search_radius_km, contract_preference, remote_preference, minimum_salary, availability,
                    summary, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    fields["first_name"],
                    fields["last_name"],
                    fields["city"],
                    fields["postal_code"],
                    fields["department"],
                    fields["search_radius_km"],
                    fields["contract_preference"],
                    fields["remote_preference"],
                    fields["minimum_salary"],
                    fields["availability"],
                    fields["summary"],
                    now,
                    now,
                ),
            )
    _update_desired_jobs(user_id, desired_jobs)


def _render_skill_form(skill: Optional[Dict[str, Any]] = None) -> str:
    skill = skill or {"name": "", "level": "", "years_experience": "", "source": "manual"}
    return render_template_string(
        """
        <section class="panel">
          <h2>{{ title }}</h2>
          <form method="post">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <div class="grid">
              <div class="field"><label>Nom</label><input name="name" value="{{ skill.name }}"></div>
              <div class="field"><label>Niveau</label>
                <select name="level">
                  <option value="">--</option>
                  {% for value in levels %}<option value="{{ value }}" {% if skill.level == value %}selected{% endif %}>{{ value }}</option>{% endfor %}
                </select>
              </div>
              <div class="field"><label>Années d'expérience</label><input name="years_experience" type="number" min="0" step="0.5" value="{{ skill.years_experience }}"></div>
              <div class="field"><label>Source</label>
                <select name="source">
                  {% for value in sources %}<option value="{{ value }}" {% if skill.source == value %}selected{% endif %}>{{ value }}</option>{% endfor %}
                </select>
              </div>
            </div>
            <div class="actions"><button class="btn" type="submit">{{ submit_label }}</button></div>
          </form>
        </section>
        """,
        title="Compétence" if skill.get("name") else "Ajouter une compétence",
        skill=skill,
        levels=SKILL_LEVELS,
        sources=SOURCES,
        submit_label="Enregistrer",
        csrf_token=_csrf_token,
    )


def _render_diploma_form(diploma: Optional[Dict[str, Any]] = None) -> str:
    diploma = diploma or {"title": "", "level": "", "institution": "", "speciality": "", "graduation_year": "", "description": "", "source": "manual"}
    return render_template_string(
        """
        <section class="panel">
          <h2>{{ title }}</h2>
          <form method="post">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <div class="grid">
              <div class="field"><label>Intitulé</label><input name="title" value="{{ diploma.title }}"></div>
              <div class="field"><label>Niveau</label><input name="level" value="{{ diploma.level }}"></div>
              <div class="field"><label>Établissement</label><input name="institution" value="{{ diploma.institution }}"></div>
              <div class="field"><label>Spécialité</label><input name="speciality" value="{{ diploma.speciality }}"></div>
              <div class="field"><label>Année d'obtention</label><input name="graduation_year" type="number" min="1900" max="2100" value="{{ diploma.graduation_year }}"></div>
              <div class="field"><label>Source</label>
                <select name="source">
                  {% for value in sources %}<option value="{{ value }}" {% if diploma.source == value %}selected{% endif %}>{{ value }}</option>{% endfor %}
                </select>
              </div>
            </div>
            <div class="field"><label>Description</label><textarea name="description">{{ diploma.description }}</textarea></div>
            <div class="actions"><button class="btn" type="submit">{{ submit_label }}</button></div>
          </form>
        </section>
        """,
        title="Diplôme" if diploma.get("title") else "Ajouter un diplôme",
        diploma=diploma,
        sources=SOURCES,
        submit_label="Enregistrer",
        csrf_token=_csrf_token,
    )


def _render_experience_form(experience: Optional[Dict[str, Any]] = None) -> str:
    experience = experience or {"job_title": "", "company": "", "city": "", "start_date": "", "end_date": "", "is_current": 0, "description": "", "source": "manual"}
    return render_template_string(
        """
        <section class="panel">
          <h2>{{ title }}</h2>
          <form method="post">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <div class="grid">
              <div class="field"><label>Intitulé du poste</label><input name="job_title" value="{{ experience.job_title }}"></div>
              <div class="field"><label>Entreprise</label><input name="company" value="{{ experience.company }}"></div>
              <div class="field"><label>Ville</label><input name="city" value="{{ experience.city }}"></div>
              <div class="field"><label>Date de début</label><input name="start_date" type="date" value="{{ experience.start_date }}"></div>
              <div class="field"><label>Date de fin</label><input name="end_date" type="date" value="{{ experience.end_date }}"></div>
              <div class="field"><label>Source</label>
                <select name="source">
                  {% for value in sources %}<option value="{{ value }}" {% if experience.source == value %}selected{% endif %}>{{ value }}</option>{% endfor %}
                </select>
              </div>
            </div>
            <div class="field"><label><input type="checkbox" name="is_current" value="1" {% if experience.is_current %}checked{% endif %}> Poste actuel</label></div>
            <div class="field"><label>Description</label><textarea name="description">{{ experience.description }}</textarea></div>
            <div class="field"><label>Compétences associées</label><textarea name="skills">{{ experience.skills_text or '' }}</textarea></div>
            <div class="actions"><button class="btn" type="submit">{{ submit_label }}</button></div>
          </form>
        </section>
        """,
        title="Expérience" if experience.get("job_title") else "Ajouter une expérience",
        experience=experience,
        sources=SOURCES,
        submit_label="Enregistrer",
        csrf_token=_csrf_token,
    )


def _store_experience(user_id: int) -> None:
    now = utcnow_iso()
    job_title = _normalize_string(request.form.get("job_title"))
    if not job_title:
        raise ValueError("Le titre du poste est obligatoire.")
    company = _normalize_string(request.form.get("company"))
    city = _normalize_string(request.form.get("city"))
    start_date = _parse_date(request.form.get("start_date"))
    end_date = _parse_date(request.form.get("end_date"))
    is_current = 1 if request.form.get("is_current") else 0
    description = _normalize_string(request.form.get("description"))
    source = request.form.get("source") or "manual"
    with transaction() as conn:
        cursor = conn.execute(
            """
            INSERT INTO experiences(
                user_id, job_title, company, city, start_date, end_date, is_current, description, source, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, job_title, company, city, start_date, end_date, is_current, description, source, now, now),
        )
        experience_id = int(cursor.lastrowid)
        skill_names = _parse_multi_values(request.form.get("skills"))
        for skill_name in skill_names:
            normalized = normalize_skill_name(skill_name)
            if not normalized:
                continue
            skill_row = conn.execute("SELECT id FROM skills WHERE normalized_name = ?", (normalized,)).fetchone()
            if skill_row:
                skill_id = int(skill_row["id"])
            else:
                skill_cursor = conn.execute(
                    "INSERT INTO skills(name, normalized_name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (skill_name, normalized, now, now),
                )
                skill_id = int(skill_cursor.lastrowid)
            conn.execute(
                "INSERT OR IGNORE INTO experience_skills(experience_id, skill_id) VALUES (?, ?)",
                (experience_id, skill_id),
            )


def _list_view_items(user_id: int, table: str) -> List[Dict[str, Any]]:
    rows = fetch_all(f"SELECT * FROM {table} WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    return [dict(row) for row in rows]


def _profile_skill_items(user_id: int) -> List[Dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT us.*, s.name, s.normalized_name
        FROM user_skills us
        JOIN skills s ON s.id = us.skill_id
        WHERE us.user_id = ?
        ORDER BY s.normalized_name ASC
        """,
        (user_id,),
    )
    return [_format_skill_table_item(dict(row)) for row in rows]


def _item_map(items: List[Dict[str, Any]], edit_route: str, delete_route: str) -> List[Dict[str, Any]]:
    mapped = []
    for item in items:
        item = dict(item)
        item["_edit_url"] = url_for(edit_route, item_id=item["id"])
        item["_delete_url"] = url_for(delete_route, item_id=item["id"])
        mapped.append(item)
    return mapped


def _delete_owned_row(table: str, item_id: int, user_id: int) -> None:
    with transaction() as conn:
        conn.execute(f"DELETE FROM {table} WHERE id = ? AND user_id = ?", (item_id, user_id))


def _calculate_duration_years(start_date: Optional[str], end_date: Optional[str], is_current: int) -> Optional[float]:
    try:
        start = date.fromisoformat(start_date) if start_date else None
        if not start:
            return None
        end = date.today() if is_current else date.fromisoformat(end_date) if end_date else date.today()
        return round(max((end - start).days / 365.25, 0.0), 2)
    except Exception:
        return None


def _profile_dict(user_id: int) -> Dict[str, Any]:
    profile = _assemble_profile(user_id)
    profile_row = {k: profile.get(k) for k in ("first_name", "last_name", "city", "postal_code", "department", "search_radius_km", "remote_preference", "minimum_salary", "availability", "summary")}
    profile_row["desired_jobs_text"] = "\n".join(item["job_title"] for item in profile["desired_jobs"])
    return profile_row


def _store_cv(user_id: int, file_storage) -> Dict[str, Any]:
    if not file_storage or not file_storage.filename:
        raise ValueError("Aucun fichier fourni.")
    filename = secure_filename(file_storage.filename)
    if not filename or not _allowed_file(filename):
        raise ValueError("Format de fichier interdit. Utilise un PDF ou un DOCX.")
    path = _safe_upload_path(user_id, filename)
    file_storage.save(path)
    max_content_length = int(current_app.config.get("MAX_CONTENT_LENGTH") or DEFAULT_MAX_UPLOAD_BYTES)
    if path.stat().st_size > max_content_length:
        path.unlink(missing_ok=True)
        raise ValueError("Le fichier dépasse la taille maximale autorisée.")
    try:
        parsed = parse_cv_file(path)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    pending = {
        "stored_filename": path.name,
        "stored_path": str(path),
        "original_filename": filename,
        "mime_type": file_storage.mimetype or "",
        "structured": parsed.structured,
        "message": parsed.message,
        "uploaded_at": utcnow_iso(),
    }
    session["pending_cv_import"] = pending
    return pending


def _save_cv_confirmation(user_id: int, pending: Dict[str, Any]) -> None:
    path = Path(pending["stored_path"])
    if not path.exists():
        raise ValueError("Le fichier du CV est introuvable.")
    parsed = parse_cv_file(path)
    extracted_text = parsed.text
    now = utcnow_iso()
    with transaction() as conn:
        existing = conn.execute("SELECT id FROM user_cvs WHERE user_id = ?", (user_id,)).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE user_cvs
                SET original_filename = ?, stored_filename = ?, mime_type = ?, uploaded_at = ?, extracted_text = ?
                WHERE user_id = ?
                """,
                (pending["original_filename"], pending["stored_filename"], pending["mime_type"], now, extracted_text, user_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO user_cvs(user_id, original_filename, stored_filename, mime_type, uploaded_at, extracted_text)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, pending["original_filename"], pending["stored_filename"], pending["mime_type"], now, extracted_text),
            )
        conn.execute("DELETE FROM user_skills WHERE user_id = ? AND source = ?", (user_id, "cv"))
        conn.execute("DELETE FROM diplomas WHERE user_id = ? AND source = ?", (user_id, "cv"))
        conn.execute("DELETE FROM experiences WHERE user_id = ? AND source = ?", (user_id, "cv"))
    structured = pending.get("structured") or {}
    for skill in structured.get("competences", []):
        _store_skill(user_id, skill.get("nom", ""), None, None, "cv")
    for formation in structured.get("formations", []):
        now = utcnow_iso()
        annee = formation.get("annee")
        if annee is None:
            date_like = formation.get("date_fin") or formation.get("date_debut")
            annee = int(str(date_like)[:4]) if isinstance(date_like, str) and len(str(date_like)) >= 4 and str(date_like)[:4].isdigit() else None
        with transaction() as conn:
            conn.execute(
                """
                INSERT INTO diplomas(user_id, title, level, institution, speciality, graduation_year, description, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    formation.get("intitule") or "",
                    formation.get("niveau"),
                    formation.get("etablissement"),
                    None,
                    annee,
                    formation.get("description") or "",
                    "cv",
                    now,
                    now,
                ),
            )
    for experience in structured.get("experiences_professionnelles", []):
        now = utcnow_iso()
        with transaction() as conn:
            conn.execute(
                """
                INSERT INTO experiences(user_id, job_title, company, city, start_date, end_date, is_current, description, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    experience.get("poste") or "",
                    experience.get("entreprise"),
                    experience.get("lieu"),
                    _normalize_cv_date_value(experience.get("date_debut")),
                    _normalize_cv_date_value(experience.get("date_fin")),
                    1 if not experience.get("date_fin") else 0,
                    experience.get("description") or "",
                    "cv",
                    now,
                    now,
                ),
            )
    session.pop("pending_cv_import", None)


def _clear_cv_file(user_id: int) -> None:
    row = fetch_one("SELECT * FROM user_cvs WHERE user_id = ?", (user_id,))
    if not row:
        return
    path = _uploads_root() / CV_FOLDER_NAME / str(user_id) / row["stored_filename"]
    path.unlink(missing_ok=True)
    execute("DELETE FROM user_cvs WHERE user_id = ?", (user_id,))


def _extract_indexed_entries(form, collection: str) -> List[Dict[str, Any]]:
    pattern = re.compile(rf"^{re.escape(collection)}\[(\d+)\]\[([^\]]+)\]$")
    grouped: Dict[int, Dict[str, Any]] = {}
    for key in form.keys():
        match = pattern.match(key)
        if not match:
            continue
        index = int(match.group(1))
        field = match.group(2)
        grouped.setdefault(index, {})[field] = form.get(key)
    return [grouped[index] for index in sorted(grouped)]


def _normalize_cv_date_value(value: object) -> Optional[str]:
    text = _normalize_string(value)
    if not text:
        return None
    if re.fullmatch(r"(19|20)\d{2}", text):
        return text
    parsed = _parse_date(text)
    return parsed or text


def _rebuild_cv_payload_from_form(form) -> Dict[str, Any]:
    competences = []
    for item in _extract_indexed_entries(form, "competences"):
        nom = _normalize_string(item.get("nom"))
        if not nom:
            continue
        formation_source = _normalize_string(item.get("formation_source"))
        competences.append({
            "nom": nom,
            "categorie": _normalize_string(item.get("categorie")) or None,
            "source": _normalize_string(item.get("source")) or "explicite",
            "texte_source": _normalize_string(item.get("texte_source")),
            "confiance": _parse_float(item.get("confiance")) or 0.0,
            **({"formation_source": formation_source} if formation_source else {}),
        })
    if not competences:
        legacy_names = form.getlist("skill_name")
        legacy_levels = form.getlist("skill_level")
        legacy_years = form.getlist("skill_years")
        for index, name in enumerate(legacy_names):
            clean = _normalize_string(name)
            if not clean:
                continue
            competences.append({
                "nom": clean,
                "categorie": _normalize_string(legacy_levels[index]) if index < len(legacy_levels) and _normalize_string(legacy_levels[index]) else None,
                "source": "explicite",
                "texte_source": clean,
                "confiance": 0.0,
            })

    formations = []
    for item in _extract_indexed_entries(form, "formations"):
        intitule = _normalize_string(item.get("intitule"))
        etablissement = _normalize_string(item.get("etablissement"))
        niveau = _normalize_string(item.get("niveau"))
        date_debut = _normalize_cv_date_value(item.get("date_debut"))
        date_fin = _normalize_cv_date_value(item.get("date_fin"))
        annee = _parse_int(item.get("annee"), 1900, 2100)
        description = _normalize_string(item.get("description"))
        texte_source = _normalize_string(item.get("texte_source"))
        confiance = _parse_float(item.get("confiance")) or 0.0
        if not any([intitule, etablissement, niveau, date_debut, date_fin, annee, description, texte_source]):
            continue
        formations.append({
            "intitule": intitule,
            "etablissement": etablissement or None,
            "niveau": niveau or None,
            "date_debut": date_debut,
            "date_fin": date_fin,
            "annee": annee,
            "description": description or None,
            "texte_source": texte_source,
            "confiance": confiance,
        })
    if not formations:
        legacy_titles = form.getlist("diploma_title")
        legacy_levels = form.getlist("diploma_level")
        legacy_schools = form.getlist("diploma_school")
        legacy_years = form.getlist("diploma_year")
        for index, title in enumerate(legacy_titles):
            clean = _normalize_string(title)
            if not clean:
                continue
            formations.append({
                "intitule": clean,
                "etablissement": _normalize_string(legacy_schools[index]) if index < len(legacy_schools) else None,
                "niveau": _normalize_string(legacy_levels[index]) if index < len(legacy_levels) else None,
                "date_debut": None,
                "date_fin": None,
                "annee": _parse_int(legacy_years[index], 1900, 2100) if index < len(legacy_years) else None,
                "description": None,
                "texte_source": clean,
                "confiance": 0.0,
            })

    experiences = []
    for item in _extract_indexed_entries(form, "experiences_professionnelles"):
        poste = _normalize_string(item.get("poste"))
        entreprise = _normalize_string(item.get("entreprise"))
        lieu = _normalize_string(item.get("lieu"))
        date_debut = _normalize_cv_date_value(item.get("date_debut"))
        date_fin = _normalize_cv_date_value(item.get("date_fin"))
        description = _normalize_string(item.get("description"))
        texte_source = _normalize_string(item.get("texte_source"))
        confidence = _parse_float(item.get("confiance")) or 0.0
        raw_associated = _normalize_string(item.get("competences_associees"))
        competences_associees = [cleaned for cleaned in (_normalize_string(part) for part in re.split(r"[,;\n|]", raw_associated) if raw_associated) if cleaned]
        if not any([poste, entreprise, lieu, date_debut, date_fin, description, texte_source]):
            continue
        experiences.append({
            "poste": poste,
            "entreprise": entreprise or None,
            "date_debut": date_debut,
            "date_fin": date_fin,
            "lieu": lieu or None,
            "description": description or None,
            "competences_associees": competences_associees,
            "texte_source": texte_source,
            "confiance": confidence,
        })
    if not experiences:
        legacy_jobs = form.getlist("experience_job")
        legacy_companies = form.getlist("experience_company")
        legacy_cities = form.getlist("experience_city")
        legacy_starts = form.getlist("experience_start")
        legacy_ends = form.getlist("experience_end")
        legacy_descs = form.getlist("experience_desc")
        for index, job_title in enumerate(legacy_jobs):
            clean = _normalize_string(job_title)
            if not clean:
                continue
            experiences.append({
                "poste": clean,
                "entreprise": _normalize_string(legacy_companies[index]) if index < len(legacy_companies) else None,
                "date_debut": _normalize_cv_date_value(legacy_starts[index]) if index < len(legacy_starts) else None,
                "date_fin": _normalize_cv_date_value(legacy_ends[index]) if index < len(legacy_ends) else None,
                "lieu": _normalize_string(legacy_cities[index]) if index < len(legacy_cities) else None,
                "description": _normalize_string(legacy_descs[index]) if index < len(legacy_descs) else None,
                "competences_associees": [],
                "texte_source": clean,
                "confiance": 0.0,
            })

    return {
        "competences": competences,
        "formations": formations,
        "experiences_professionnelles": experiences,
        "sections_detectees": {
            "formations": bool(formations),
            "competences": bool(competences),
            "experiences_professionnelles": bool(experiences),
        },
        "texte_brut": _normalize_string(form.get("texte_brut")),
        "warnings": [],
    }

def _delete_all_user_data(user_id: int) -> None:
    _clear_cv_file(user_id)
    with transaction() as conn:
        conn.execute("DELETE FROM job_matches WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM desired_jobs WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM user_skills WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM diplomas WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM experiences WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM user_profiles WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


def _current_profile_snapshot(user_id: int) -> Dict[str, Any]:
    profile = _assemble_profile(user_id)
    desired_jobs = [
        {
            "job_title": item["job_title"],
            "normalized_job_title": item["normalized_job_title"],
        }
        for item in profile["desired_jobs"]
    ]
    return {
        "first_name": profile.get("first_name") or "",
        "last_name": profile.get("last_name") or "",
        "city": profile.get("city") or "",
        "postal_code": profile.get("postal_code") or "",
        "department": profile.get("department") or "",
        "search_radius_km": profile.get("search_radius_km"),
        "contract_preference": profile.get("contract_preference") or "",
        "remote_preference": profile.get("remote_preference") or "indifferent",
        "minimum_salary": profile.get("minimum_salary"),
        "availability": profile.get("availability") or "",
        "summary": profile.get("summary") or "",
        "desired_jobs": desired_jobs,
        "skills": [_skill_payload_from_row(item) for item in profile["skills"]],
        "diplomas": [
            {
                "title": item["title"],
                "level": item.get("level") or "",
                "institution": item.get("institution") or "",
                "speciality": item.get("speciality") or "",
                "graduation_year": item.get("graduation_year") or "",
                "description": item.get("description") or "",
                "source": item.get("source") or "manual",
            }
            for item in profile["diplomas"]
        ],
        "experiences": [
            {
                "job_title": item["job_title"],
                "company": item.get("company") or "",
                "city": item.get("city") or "",
                "start_date": item.get("start_date") or "",
                "end_date": item.get("end_date") or "",
                "is_current": int(item.get("is_current") or 0),
                "description": item.get("description") or "",
                "source": item.get("source") or "manual",
                "skills_text": ", ".join(item.get("skills", [])),
            }
            for item in profile["experiences"]
        ],
        "cv": profile.get("cv"),
    }


def _export_user_data_payload(user_id: int) -> Dict[str, Any]:
    profile = _assemble_profile(user_id)
    matches = _current_job_matches(user_id)
    return {
        "user": {
            "id": user_id,
            "profile": _current_profile_snapshot(user_id),
        },
        "jobs_wanted": [item["job_title"] for item in profile["desired_jobs"]],
        "skills": [
            {
                "name": row["name"],
                "normalized_name": row["normalized_name"],
                "level": row.get("level") or None,
                "years_experience": row.get("years_experience"),
                "source": row.get("source"),
            }
            for row in profile["skills"]
        ],
        "diplomas": [dict(item) for item in profile["diplomas"]],
        "experiences": [dict(item) for item in profile["experiences"]],
        "cv": dict(profile["cv"]) if profile.get("cv") else None,
        "job_matches": [
            {
                "offer_identifier": match.get("offer_identifier"),
                "global_score": match.get("global_score"),
                "matching_skills": match.get("matching_skills_json") or [],
                "missing_skills": match.get("missing_skills_json") or [],
                "calculated_at": match.get("calculated_at"),
            }
            for match in matches
        ],
    }


def _offer_matches_filters(offer: Dict[str, Any], filters: Dict[str, Any], match: Dict[str, Any]) -> bool:
    if filters.get("min_score") is not None and match["global_score"] < filters["min_score"]:
        return False
    if filters.get("contract") and normalize_text(filters["contract"]) not in normalize_text(offer.get("contrat")):
        return False
    if filters.get("remote") and normalize_text(filters["remote"]) not in normalize_text(offer.get("teletravail")):
        return False
    if filters.get("skill"):
        target = normalize_text(filters["skill"])
        if target not in " ".join(normalize_text(s) for s in offer.get("competences", [])):
            return False
    if filters.get("job"):
        job_blob = " ".join([offer.get("titre") or "", offer.get("description") or ""])
        if normalize_text(filters["job"]) not in normalize_text(job_blob):
            return False
    if filters.get("source") and normalize_text(filters["source"]) not in normalize_text(offer.get("source")):
        return False
    if filters.get("territoire"):
        location_blob = " ".join(offer.get("lieux", []))
        if normalize_text(filters["territoire"]) not in normalize_text(location_blob):
            return False
    return True


def _current_job_matches(user_id: int) -> List[Dict[str, Any]]:
    rows = fetch_all("SELECT * FROM job_matches WHERE user_id = ? ORDER BY global_score DESC, calculated_at DESC", (user_id,))
    matches = []
    for row in rows:
        payload = dict(row)
        try:
            payload["matching_skills_json"] = json.loads(payload["matching_skills_json"] or "[]")
        except json.JSONDecodeError:
            payload["matching_skills_json"] = []
        try:
            payload["missing_skills_json"] = json.loads(payload["missing_skills_json"] or "[]")
        except json.JSONDecodeError:
            payload["missing_skills_json"] = []
        try:
            payload["explanation_json"] = json.loads(payload["explanation_json"] or "{}")
        except json.JSONDecodeError:
            payload["explanation_json"] = {}
        matches.append(payload)
    return matches


def _explanation_with_offer_summary(match: Dict[str, Any]) -> Dict[str, Any]:
    explanation = dict(match.get("explanation") or {})
    offer = match.get("offer") or {}
    resolved_title = resolve_offer_title(offer)
    resolved_location = resolve_offer_location(offer)
    explanation["offer"] = {
        "titre": resolved_title,
        "intitule": resolved_title,
        "contrat": offer.get("contrat"),
        "lieux": offer.get("lieux") or ([resolved_location] if resolved_location != "Lieu non renseigné" else []),
        "territoire": offer.get("territoire"),
        "ville": offer.get("ville"),
        "competences": offer.get("competences") or [],
        "source": offer.get("source"),
        "url_originale": offer.get("url_originale") or offer.get("url"),
        "entreprise": offer.get("entreprise"),
        "teletravail": offer.get("teletravail"),
    }
    explanation["score_global"] = match.get("global_score")
    explanation["sous_scores"] = match.get("criterion_scores") or {}
    explanation["matching_weights"] = match.get("matching_weights") or {}
    explanation["criterion_details"] = match.get("criterion_details") or {}
    return explanation


def _decoded_explanation(value: object) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            payload = json.loads(value or "{}")
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}
    return {}


def _persist_match(user_id: int, match: Dict[str, Any]) -> None:
    now = utcnow_iso()
    offer_identifier = str(match.get("offer_identifier") or "")
    if not offer_identifier:
        return
    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO job_matches(
                user_id, offer_identifier, global_score, skill_score, job_score, experience_score,
                diploma_score, location_score, contract_score, remote_score,
                matching_skills_json, missing_skills_json, explanation_json, calculated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, offer_identifier) DO UPDATE SET
                global_score = excluded.global_score,
                skill_score = excluded.skill_score,
                job_score = excluded.job_score,
                experience_score = excluded.experience_score,
                diploma_score = excluded.diploma_score,
                location_score = excluded.location_score,
                contract_score = excluded.contract_score,
                remote_score = excluded.remote_score,
                matching_skills_json = excluded.matching_skills_json,
                missing_skills_json = excluded.missing_skills_json,
                explanation_json = excluded.explanation_json,
                calculated_at = excluded.calculated_at
            """,
            (
                user_id,
                offer_identifier,
                match.get("global_score", 0.0),
                match.get("skill_score", 0.0),
                match.get("job_score", 0.0),
                match.get("experience_score", 0.0),
                match.get("diploma_score", 0.0),
                match.get("location_score", 0.0),
                match.get("contract_score", 0.0),
                match.get("remote_score", 0.0),
                json.dumps(match.get("matching_skills", []), ensure_ascii=False),
                json.dumps(match.get("missing_skills", []), ensure_ascii=False),
                json.dumps(_explanation_with_offer_summary(match), ensure_ascii=False),
                now,
            ),
        )


def _compute_recommendations(user_id: int) -> List[Dict[str, Any]]:
    """Retourne les recommandations pour un utilisateur.

    Lit les matchings précalculés par src.jobs.refresh_all si disponibles,
    sinon retombe sur le calcul en direct (compatibilité tests).

    Args:
        user_id: Identifiant de l'utilisateur.

    Returns:
        Liste des matchings, triés par score décroissant.
    """
    if has_precomputed_data():
        cached_matches, error = get_precomputed_matches(user_id)
        if not error and cached_matches:
            offers, _ = get_precomputed_offers()
            offers_by_id = {}
            for offer in offers:
                offer_id = str(offer.get("id") or offer.get("id_offre") or "")
                if offer_id:
                    offers_by_id[offer_id] = offer

            matches = []
            for cached in cached_matches:
                offer_id = str(cached.get("offer_id") or cached.get("offer_identifier") or "")
                offer = offers_by_id.get(offer_id, {})
                details = cached.get("details") or {}

                explanation = details.get("explanation") or {}
                if isinstance(explanation, str):
                    try:
                        explanation = json.loads(explanation)
                    except json.JSONDecodeError:
                        explanation = {}

                criterion_details = details.get("criterion_details") or {}
                sous_scores = details.get("sous_scores") or {}
                criterion_scores = details.get("criterion_scores") or {}

                match = {
                    "offer_identifier": offer_id,
                    "global_score": float(cached.get("score") or details.get("global_score") or details.get("score_global") or 0),
                    "skill_score": float(details.get("skill_score") or 0),
                    "job_score": float(details.get("job_score") or 0),
                    "experience_score": float(details.get("experience_score") or 0),
                    "diploma_score": float(details.get("diploma_score") or 0),
                    "location_score": float(details.get("location_score") or 0),
                    "contract_score": float(details.get("contract_score") or 0),
                    "remote_score": float(details.get("remote_score") or 0),
                    "salary_score": float(details.get("salary_score") or 0),
                    "matching_skills": cached.get("matching_skills") or details.get("matching_skills") or details.get("competences_communes") or [],
                    "missing_skills": cached.get("missing_skills") or details.get("missing_skills") or details.get("competences_manquantes") or [],
                    "explanation": explanation,
                    "sous_scores": sous_scores,
                    "criterion_scores": criterion_scores,
                    "criterion_details": criterion_details,
                    "offer": offer,
                }
                matches.append(match)

            matches.sort(key=lambda item: (-float(item.get("global_score") or 0), item.get("offer", {}).get("titre") or ""))
            return matches

    profile = _current_profile_snapshot(user_id)
    weights = _current_matching_weights()
    offers = [_normalize_offer(offer) for offer in _load_local_offers()]
    matches = []
    for raw_offer in offers:
        result = compute_match(profile, raw_offer, weights=weights)
        result["offer"] = {**result["offer"], **raw_offer}
        _persist_match(user_id, result)
        matches.append(result)
    matches.sort(key=lambda item: (-float(item.get("global_score") or 0), item["offer"].get("titre") or ""))
    return matches


def _recommendation_filters_from_request() -> Dict[str, Any]:
    return {
        "territoire": _normalize_string(request.args.get("territoire")),
        "min_score": _parse_int(request.args.get("score_min"), 0, 100),
        "contract": _normalize_string(request.args.get("contrat")),
        "remote": _normalize_string(request.args.get("teletravail")),
        "skill": _normalize_string(request.args.get("competence")),
        "job": _normalize_string(request.args.get("metier")),
        "source": _normalize_string(request.args.get("source")),
        "page": max(_parse_int(request.args.get("page"), 1) or 1, 1),
        "per_page": min(max(_parse_int(request.args.get("per_page"), 1) or DEFAULT_LIMIT, 1), MAX_CARD_COUNT),
    }


def _filter_and_paginate_matches(matches: List[Dict[str, Any]], filters: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], int, int]:
    filtered = []
    for match in matches:
        if _offer_matches_filters(match["offer"], filters, match):
            filtered.append(match)
    filtered.sort(key=lambda item: (-float(item.get("global_score") or 0), item["offer"].get("titre") or ""))
    total = len(filtered)
    per_page = filters["per_page"]
    page = max(filters["page"], 1)
    total_pages = max((total + per_page - 1) // per_page, 1) if total else 0
    page = min(page, total_pages) if total_pages else 1
    start = (page - 1) * per_page
    end = start + per_page
    return filtered[start:end], total, page


def _build_query_string(params: Dict[str, Any]) -> str:
    from urllib.parse import urlencode

    return urlencode({key: value for key, value in params.items() if value not in (None, "")})


def _score_bar_class(score: float) -> str:
    if score >= 70:
        return "high"
    if score >= 40:
        return "mid"
    return "low"


def _score_ring_class(score: float) -> str:
    if score >= 70:
        return "score-ring--high"
    if score >= 40:
        return "score-ring--mid"
    return "score-ring--low"


_CRITERION_LABELS = {
    "competences": "Compétences",
    "metier": "Métier",
    "experience": "Expérience",
    "diplome": "Diplôme",
    "localisation": "Localisation",
    "salaire": "Salaire",
    "contrat": "Contrat",
    "teletravail": "Télétravail",
}


def _render_score_bars(match: Dict[str, Any]) -> str:
    vm = build_match_view_model(match)
    criterion_scores = vm.criterion_scores
    rows = []
    for key in ("skills", "job", "experience", "diploma", "location", "contract", "remote", "salary"):
        info = criterion_scores.get(key) or {}
        label = info.get("label") or key
        score = info.get("score")
        evaluated = info.get("evaluated", False)
        reason = info.get("reason") or ""
        if not evaluated or score is None:
            bar_class = "absent"
            value_display = "Non évalué"
            width = 0
        else:
            score_f = float(score)
            bar_class = _score_bar_class(score_f)
            value_display = f"{score_f:.0f}/100"
            width = max(0, min(100, score_f))
        reason_html = f'<div class="criterion-reason">{escape(reason)}</div>' if reason else ""
        rows.append(
            f'<div class="score-bar-item">'
            f'<div class="score-bar-item__head">'
            f'<span class="score-bar-item__label">{escape(label)}</span>'
            f'<span class="score-bar-item__value">{value_display}</span>'
            f"</div>"
            f'<div class="score-bar-track"><div class="score-bar-fill score-bar-fill--{bar_class}" style="width:{width}%"></div></div>'
            f"{reason_html}"
            f"</div>"
        )
    return '<div style="margin:10px 0 6px"><strong style="font-size:0.9rem;">Sous-scores</strong></div><div class="score-detail-grid">' + "".join(rows) + "</div>"


def _render_skills_tags(matching: List[str], missing: List[str]) -> str:
    parts = []
    if matching:
        parts.append('<div style="margin-bottom:6px"><strong style="font-size:0.85rem;color:var(--success)">Compétences communes</strong></div>')
        parts.append('<div class="chips">')
        for skill in matching:
            parts.append(f'<span class="skill-tag skill-tag--match">{escape(skill)}</span>')
        parts.append("</div>")
    if missing:
        parts.append('<div style="margin:8px 0 6px"><strong style="font-size:0.85rem;color:var(--danger)">Compétences manquantes</strong></div>')
        parts.append('<div class="chips">')
        for skill in missing[:10]:
            parts.append(f'<span class="skill-tag skill-tag--missing">{escape(skill)}</span>')
        parts.append("</div>")
    return "".join(parts)


def _render_offer_card(match: Dict[str, Any], show_detail_link: bool = True) -> str:
    vm = build_match_view_model(match)
    offer = match.get("offer") or {}
    explanation = match.get("explanation") or {}
    global_score = float(vm.global_score or 0)
    score_int = int(round(global_score))
    ring_class = _score_ring_class(global_score)
    url = vm.url
    if not url:
        source = str(vm.source or "").lower().strip()
        if source in {"", "france travail", "france_travail", "francetravail"}:
            url = f"https://candidat.francetravail.fr/offres/recherche/detail/{vm.offer_id}"
    offer_id = vm.offer_id
    detail_url = url_for("user_portal.recommendation_detail", offer_id=offer_id) if offer_id else None
    matching_skills = vm.matched_skills or match.get("matching_skills") or explanation.get("matching_skills") or []
    missing_skills = vm.missing_skills or match.get("missing_skills") or explanation.get("missing_skills") or []
    summary = explanation.get("summary") or ""
    detail_parts = explanation.get("details") or []

    detail_link_html = ""
    if show_detail_link and detail_url:
        detail_link_html = f'<a class="offer-card__detail-link" href="{escape(detail_url)}">Voir le détail du match →</a>'

    url_html = ""
    if url:
        url_html = f'<a class="btn" href="{escape(url)}" target="_blank" rel="noopener noreferrer">Voir l\u2019offre</a>'
    else:
        url_html = '<span class="muted">Lien indisponible</span>'

    company_display = vm.company or "Entreprise non renseignée"
    location_display = vm.location or "Lieu non renseigné"
    contract_display = vm.contract or "Contrat non renseigné"
    remote_display = vm.remote_text or "Télétravail non renseigné"
    source_display = vm.source or "Source non renseignée"

    debug_html = ""
    if is_debug_mode():
        debug_data = debug_offer_payload(
            raw_offer=offer,
            normalized_offer=offer,
            match_result=match,
            view_model=vm,
        )
        debug_html = (
            f'<details style="margin-top:8px;font-size:0.75rem">'
            f'<summary>Debug</summary>'
            f'<pre style="max-height:300px;overflow:auto;background:#f4f4f4;padding:6px">'
            f'{escape(json.dumps(debug_data, indent=2, ensure_ascii=False, default=str))}'
            f"</pre></details>"
        )

    return (
        f'<article class="offer-card">'
        f'<div class="offer-card__header">'
        f'<div class="score-ring {ring_class}">{score_int}</div>'
        f'<div class="offer-card__header-text">'
        f'<h3 class="offer-title">{escape(vm.title)}</h3>'
        f'<div class="meta">'
        f'<span>{escape(company_display)}</span>'
        f'<span>{escape(location_display)}</span>'
        f'<span>{escape(contract_display)}</span>'
        f'<span>{escape(remote_display)}</span>'
        f'<span>{escape(source_display)}</span>'
        f"</div>"
        f"{detail_link_html}"
        f"</div>"
        f"</div>"
        f'{_render_score_bars(match)}'
        f'{_render_skills_tags(matching_skills, missing_skills)}'
        f'<div class="explain" style="margin-top:10px">'
        f'<p>{escape(summary)}</p>'
        f'{"".join(f"<p>{escape(part)}</p>" for part in detail_parts) if detail_parts else ""}'
        f"</div>"
        f'{debug_html}'
        f'<div class="actions" style="margin-top:12px">{url_html}</div>'
        f"</article>"
    )


def _recommendation_page(matches: List[Dict[str, Any]], filters: Dict[str, Any], total: int, page: int) -> str:
    if not matches:
        cards_html = "<div class='muted'>Aucune offre ne correspond à cette recherche.</div>"
    else:
        cards = [_render_offer_card(match) for match in matches]
        cards_html = "".join(cards)
    total_pages = max((total + filters["per_page"] - 1) // filters["per_page"], 1) if total else 0
    prev_url = None
    next_url = None
    base_params = {
        "territoire": filters["territoire"],
        "score_min": filters["min_score"],
        "contrat": filters["contract"],
        "teletravail": filters["remote"],
        "competence": filters["skill"],
        "metier": filters["job"],
        "source": filters["source"],
        "per_page": filters["per_page"],
    }
    if page > 1:
        prev_url = f"{url_for('user_portal.recommendations')}?{_build_query_string({**base_params, 'page': page - 1})}"
    if total_pages and page < total_pages:
        next_url = f"{url_for('user_portal.recommendations')}?{_build_query_string({**base_params, 'page': page + 1})}"
    return render_template_string(
        """
        <section class="panel">
          <div class="actions" style="justify-content: space-between;">
            <h2>Mes offres</h2>
            <div class="muted">{{ total }} offres triées par score</div>
          </div>
          <div class="offer-grid">{{ cards|safe }}</div>
          <div class="actions" style="justify-content: space-between; margin-top: 14px;">
            <div class="muted">Page {{ page }}{% if total_pages %} / {{ total_pages }}{% endif %}</div>
            <div class="actions">
              {% if prev_url %}<a class="btn secondary" href="{{ prev_url }}">Précédent</a>{% endif %}
              {% if next_url %}<a class="btn secondary" href="{{ next_url }}">Suivant</a>{% endif %}
            </div>
          </div>
        </section>
        """,
        cards=cards_html,
        total=total,
        page=page,
        total_pages=total_pages,
        prev_url=prev_url,
        next_url=next_url,
    )


@user_portal_bp.before_app_request
def _load_current_user() -> None:
    if "user_id" in session:
        g.current_user = _get_user(_current_user_id())


@user_portal_bp.context_processor
def _inject_csrf() -> Dict[str, Any]:
    return {"csrf_token": _csrf_token}


@user_portal_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        error = _validate_required_csrf()
        if error:
            return _render_page("Inscription", _auth_block(url_for("user_portal.register"), "Créer un compte", "S'inscrire", error=error), message=error, message_category="error")
        email = _normalize_string(request.form.get("email")).lower()
        password = request.form.get("password") or ""
        if not email or not password:
            error = "Email et mot de passe sont obligatoires."
            return _render_page("Inscription", _auth_block(url_for("user_portal.register"), "Créer un compte", "S'inscrire", error=error), message=error, message_category="error")
        try:
            user_id = _create_or_update_user(email, password)
        except ValueError as exc:
            return _render_page("Inscription", _auth_block(url_for("user_portal.register"), "Créer un compte", "S'inscrire", error=str(exc)), message=str(exc), message_category="error")
        _login_user(user_id)
        flash("Compte créé avec succès.", "success")
        return redirect(url_for("user_portal.profile"))
    return _render_page("Inscription", _auth_block(url_for("user_portal.register"), "Créer un compte", "S'inscrire"))


@user_portal_bp.route("/login", methods=["GET", "POST"])
def login():
    next_url = request.values.get("next") or url_for("user_portal.dashboard")
    if request.method == "POST":
        error = _validate_required_csrf()
        if error:
            return _render_page("Connexion", _auth_block(url_for("user_portal.login"), "Se connecter", "Connexion", next_url=next_url, error=error), message=error, message_category="error")
        email = _normalize_string(request.form.get("email")).lower()
        password = request.form.get("password") or ""
        user_id = _authenticate_user(email, password)
        if not user_id:
            error = "Identifiants invalides."
            return _render_page("Connexion", _auth_block(url_for("user_portal.login"), "Se connecter", "Connexion", next_url=next_url, error=error), message=error, message_category="error")
        _login_user(user_id)
        return redirect(next_url)
    return _render_page("Connexion", _auth_block(url_for("user_portal.login"), "Se connecter", "Connexion", next_url=next_url))


@user_portal_bp.route("/logout")
def logout():
    _logout_user()
    return redirect(url_for("user_portal.login"))


@user_portal_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user_id = _current_user_id()
    assert user_id is not None
    error = None
    if request.method == "POST":
        error = _validate_required_csrf()
        if not error:
            weight_error = _save_matching_weights_from_form(request.form)
            try:
                _save_profile(user_id)
                if weight_error:
                    error = weight_error
                else:
                    flash("Profil enregistré.", "success")
                    return redirect(url_for("user_portal.profile"))
            except ValueError as exc:
                error = str(exc)
    profile_data = _current_profile_snapshot(user_id)
    matching_weights = _current_matching_weights()
    desired_jobs_text = "\n".join(item["job_title"] if isinstance(item, dict) else str(item) for item in profile_data["desired_jobs"])
    content = _profile_form(profile_data, desired_jobs_text, matching_weights, error)
    content += _profile_summary_block(profile_data)
    skill_items = _item_map(
        _profile_skill_items(user_id),
        "user_portal.edit_skill",
        "user_portal.delete_skill",
    )
    diploma_items = _item_map(
        _list_view_items(user_id, "diplomas"),
        "user_portal.edit_diploma",
        "user_portal.delete_diploma",
    )
    content += _list_section("Compétences", skill_items, [("Nom", "name"), ("Niveau", "level"), ("Années", "years_experience"), ("Source", "source")], url_for("user_portal.skills"), "Aucune compétence enregistrée.")
    content += _list_section("Formations", diploma_items, [("Intitulé", "title"), ("Niveau", "level"), ("Établissement", "institution"), ("Année", "graduation_year"), ("Source", "source")], url_for("user_portal.diplomas"), "Aucune formation enregistrée.")
    content += _profile_privacy_block(profile_data)
    return _render_page("Mon profil", content, message=error)

@user_portal_bp.route("/profile/skills", methods=["GET", "POST"])
@login_required
def skills():
    user_id = _current_user_id()
    assert user_id is not None
    error = None
    if request.method == "POST":
        error = _validate_required_csrf()
        if not error:
            try:
                _store_skill(
                    user_id,
                    request.form.get("name") or "",
                    request.form.get("level"),
                    _parse_float(request.form.get("years_experience")),
                    request.form.get("source") or "manual",
                )
                flash("Compétence enregistrée.", "success")
                return redirect(url_for("user_portal.skills"))
            except ValueError as exc:
                error = str(exc)
    items = _item_map(
        _profile_skill_items(user_id),
        "user_portal.edit_skill",
        "user_portal.delete_skill",
    )
    content = _render_skill_form()
    content += _list_section("Compétences", items, [("Nom", "name"), ("Niveau", "level"), ("Années", "years_experience"), ("Source", "source")], url_for("user_portal.skills"), "Aucune compétence enregistrée.")
    return _render_page("Compétences", content, message=error)


@user_portal_bp.route("/profile/skills/<int:item_id>/edit", methods=["GET", "POST"])
@login_required
def edit_skill(item_id: int):
    user_id = _current_user_id()
    assert user_id is not None
    row = fetch_one(
        """
        SELECT us.*, s.name, s.normalized_name
        FROM user_skills us
        JOIN skills s ON s.id = us.skill_id
        WHERE us.id = ? AND us.user_id = ?
        """,
        (item_id, user_id),
    )
    if not row:
        return redirect(url_for("user_portal.skills"))
    if request.method == "POST":
        error = _validate_required_csrf()
        if not error:
            _delete_owned_row("user_skills", item_id, user_id)
            _store_skill(
                user_id,
                request.form.get("name") or "",
                request.form.get("level"),
                _parse_float(request.form.get("years_experience")),
                request.form.get("source") or "manual",
            )
            return redirect(url_for("user_portal.skills"))
    content = _render_skill_form(_skill_payload_from_row(dict(row)))
    return _render_page("Modifier compétence", content)


@user_portal_bp.route("/profile/skills/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_skill(item_id: int):
    user_id = _current_user_id()
    assert user_id is not None
    if not _check_csrf():
        return redirect(url_for("user_portal.skills"))
    _delete_owned_row("user_skills", item_id, user_id)
    return redirect(url_for("user_portal.skills"))


@user_portal_bp.route("/profile/diplomas", methods=["GET", "POST"])
@login_required
def diplomas():
    user_id = _current_user_id()
    assert user_id is not None
    error = None
    if request.method == "POST":
        error = _validate_required_csrf()
        if not error:
            now = utcnow_iso()
            with transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO diplomas(user_id, title, level, institution, speciality, graduation_year, description, source, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        _normalize_string(request.form.get("title")),
                        _normalize_string(request.form.get("level")),
                        _normalize_string(request.form.get("institution")),
                        _normalize_string(request.form.get("speciality")),
                        _parse_int(request.form.get("graduation_year"), 1900, 2100),
                        _normalize_string(request.form.get("description")),
                        request.form.get("source") or "manual",
                        now,
                        now,
                    ),
                )
            return redirect(url_for("user_portal.diplomas"))
    items = _item_map(
        _list_view_items(user_id, "diplomas"),
        "user_portal.edit_diploma",
        "user_portal.delete_diploma",
    )
    content = _render_diploma_form()
    content += _list_section("Diplômes", items, [("Intitulé", "title"), ("Niveau", "level"), ("Établissement", "institution"), ("Année", "graduation_year"), ("Source", "source")], url_for("user_portal.diplomas"), "Aucun diplôme enregistré.")
    return _render_page("Diplômes", content, message=error)


@user_portal_bp.route("/profile/diplomas/<int:item_id>/edit", methods=["GET", "POST"])
@login_required
def edit_diploma(item_id: int):
    user_id = _current_user_id()
    assert user_id is not None
    row = fetch_one("SELECT * FROM diplomas WHERE id = ? AND user_id = ?", (item_id, user_id))
    if not row:
        return redirect(url_for("user_portal.diplomas"))
    if request.method == "POST":
        if _check_csrf():
            now = utcnow_iso()
            with transaction() as conn:
                conn.execute(
                    """
                    UPDATE diplomas
                    SET title = ?, level = ?, institution = ?, speciality = ?, graduation_year = ?, description = ?, source = ?, updated_at = ?
                    WHERE id = ? AND user_id = ?
                    """,
                    (
                        _normalize_string(request.form.get("title")),
                        _normalize_string(request.form.get("level")),
                        _normalize_string(request.form.get("institution")),
                        _normalize_string(request.form.get("speciality")),
                        _parse_int(request.form.get("graduation_year"), 1900, 2100),
                        _normalize_string(request.form.get("description")),
                        request.form.get("source") or "manual",
                        now,
                        item_id,
                        user_id,
                    ),
                )
            return redirect(url_for("user_portal.diplomas"))
    content = _render_diploma_form(dict(row))
    return _render_page("Modifier diplôme", content)


@user_portal_bp.route("/profile/diplomas/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_diploma(item_id: int):
    user_id = _current_user_id()
    assert user_id is not None
    if _check_csrf():
        _delete_owned_row("diplomas", item_id, user_id)
    return redirect(url_for("user_portal.diplomas"))


@user_portal_bp.route("/profile/experiences", methods=["GET", "POST"])
@login_required
def experiences():
    user_id = _current_user_id()
    assert user_id is not None
    error = None
    if request.method == "POST":
        error = _validate_required_csrf()
        if not error:
            try:
                _store_experience(user_id)
                return redirect(url_for("user_portal.experiences"))
            except ValueError as exc:
                error = str(exc)
    items = _list_view_items(user_id, "experiences")
    for item in items:
        item["duration_years"] = _calculate_duration_years(item.get("start_date"), item.get("end_date"), int(item.get("is_current") or 0))
        item["skills_text"] = ", ".join(
            row["name"]
            for row in fetch_all(
                """
                SELECT s.name
                FROM experience_skills es
                JOIN skills s ON s.id = es.skill_id
                WHERE es.experience_id = ?
                """,
                (item["id"],),
            )
        )
    mapped = _item_map(items, "user_portal.edit_experience", "user_portal.delete_experience")
    content = _render_experience_form()
    content += _list_section("Expériences", mapped, [("Poste", "job_title"), ("Entreprise", "company"), ("Ville", "city"), ("Début", "start_date"), ("Fin", "end_date")], url_for("user_portal.experiences"), "Aucune expérience enregistrée.")
    return _render_page("Expériences", content, message=error)


@user_portal_bp.route("/profile/experiences/<int:item_id>/edit", methods=["GET", "POST"])
@login_required
def edit_experience(item_id: int):
    user_id = _current_user_id()
    assert user_id is not None
    row = fetch_one("SELECT * FROM experiences WHERE id = ? AND user_id = ?", (item_id, user_id))
    if not row:
        return redirect(url_for("user_portal.experiences"))
    if request.method == "POST":
        if _check_csrf():
            now = utcnow_iso()
            with transaction() as conn:
                conn.execute(
                    """
                    UPDATE experiences
                    SET job_title = ?, company = ?, city = ?, start_date = ?, end_date = ?, is_current = ?, description = ?, source = ?, updated_at = ?
                    WHERE id = ? AND user_id = ?
                    """,
                    (
                        _normalize_string(request.form.get("job_title")),
                        _normalize_string(request.form.get("company")),
                        _normalize_string(request.form.get("city")),
                        _parse_date(request.form.get("start_date")),
                        _parse_date(request.form.get("end_date")),
                        1 if request.form.get("is_current") else 0,
                        _normalize_string(request.form.get("description")),
                        request.form.get("source") or "manual",
                        now,
                        item_id,
                        user_id,
                    ),
                )
            return redirect(url_for("user_portal.experiences"))
    experience = dict(row)
    experience["skills_text"] = ", ".join(
        row["name"]
        for row in fetch_all(
            """
            SELECT s.name
            FROM experience_skills es
            JOIN skills s ON s.id = es.skill_id
            WHERE es.experience_id = ?
            """,
            (item_id,),
        )
    )
    content = _render_experience_form(experience)
    return _render_page("Modifier expérience", content)


@user_portal_bp.route("/profile/experiences/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_experience(item_id: int):
    user_id = _current_user_id()
    assert user_id is not None
    if _check_csrf():
        _delete_owned_row("experiences", item_id, user_id)
    return redirect(url_for("user_portal.experiences"))


@user_portal_bp.route("/profile/cv", methods=["GET", "POST"])
@login_required
def upload_cv():
    user_id = _current_user_id()
    assert user_id is not None
    message = None
    message_category = None
    if request.method == "POST":
        error = _validate_required_csrf()
        if error:
            message = error
            message_category = "error"
        else:
            uploaded = request.files.get("cv_file")
            try:
                pending = _store_cv(user_id, uploaded)
                flash("CV importé. Vérifie et confirme les informations extraites.", "success")
                return redirect(url_for("user_portal.validate_cv"))
            except Exception as exc:
                message = str(exc)
                message_category = "error"
    cv_row = fetch_one("SELECT * FROM user_cvs WHERE user_id = ?", (user_id,))
    content = render_template_string(
        """
        <section class="panel">
          <h2>Importer mon CV</h2>
          <p class="muted">Formats acceptés: PDF ou DOCX. Le fichier est stocké hors du dossier public.</p>
          <form method="post" enctype="multipart/form-data">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <div class="field">
              <label>Fichier CV</label>
              <input type="file" name="cv_file" accept=".pdf,.docx" required>
            </div>
            <div class="actions">
              <button class="btn" type="submit">Importer</button>
            </div>
          </form>
          {% if cv_row %}
          <hr>
          <p class="muted">CV actuellement enregistré: {{ cv_row['original_filename'] }}</p>
          <div class="actions">
            <a class="btn secondary" href="{{ url_for('user_portal.cv_preview') }}">Voir l'aperçu</a>
            <form method="post" action="{{ url_for('user_portal.delete_cv') }}">
              <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
              <button class="btn danger" type="submit">Supprimer mon CV</button>
            </form>
          </div>
          {% endif %}
        </section>
        """,
        cv_row=dict(cv_row) if cv_row else None,
        csrf_token=_csrf_token,
    )
    return _render_page("Mon CV", content, message=message, message_category=message_category)


@user_portal_bp.route("/profile/cv/preview")
@login_required
def cv_preview():
    user_id = _current_user_id()
    assert user_id is not None
    cv_row = fetch_one("SELECT * FROM user_cvs WHERE user_id = ?", (user_id,))
    cv_data = dict(cv_row) if cv_row else None
    if not cv_data:
        return _render_page("Aperçu CV", "<section class='panel'><h2>Aucun CV enregistré</h2><div class='muted'>Importe d'abord un CV pour le visualiser.</div></section>")
    path = _uploads_root() / CV_FOLDER_NAME / str(user_id) / cv_data["stored_filename"]
    if not path.exists():
        return _render_page("Aperçu CV", "<section class='panel'><h2>CV introuvable</h2><div class='muted'>Le fichier enregistré n'est plus disponible.</div></section>")
    is_pdf = str(cv_data.get("mime_type") or "").startswith("application/pdf") or str(cv_data.get("original_filename") or "").lower().endswith(".pdf")
    content = render_template_string(
        """
        <section class="panel cv-preview-panel">
          <div class="actions" style="justify-content: space-between;">
            <div>
              <h2>Aperçu de mon CV</h2>
              <p class="muted">{{ cv_row['original_filename'] }}</p>
            </div>
            <div class="actions">
              <a class="btn secondary" href="{{ url_for('user_portal.cv_file') }}" target="_blank" rel="noopener noreferrer">Ouvrir le fichier</a>
              <a class="btn secondary" href="{{ url_for('user_portal.upload_cv') }}">Retour</a>
            </div>
          </div>
          {% if is_pdf %}
          <object class="cv-preview-frame" data="{{ url_for('user_portal.cv_file') }}" type="application/pdf">
            <p class="muted">La prévisualisation PDF n'est pas disponible dans ce navigateur. Utilise le bouton d'ouverture.</p>
          </object>
          {% else %}
          <div class="cv-preview-text">
            <h3>Texte extrait</h3>
            <pre>{{ cv_row['extracted_text'] }}</pre>
          </div>
          {% endif %}
        </section>
        """,
        cv_row=cv_data,
        is_pdf=is_pdf,
    )
    return _render_page("Aperçu CV", content)


@user_portal_bp.route("/profile/cv/file")
@login_required
def cv_file():
    user_id = _current_user_id()
    assert user_id is not None
    cv_row = fetch_one("SELECT * FROM user_cvs WHERE user_id = ?", (user_id,))
    cv_data = dict(cv_row) if cv_row else None
    if not cv_data:
        return redirect(url_for("user_portal.upload_cv"))
    path = _uploads_root() / CV_FOLDER_NAME / str(user_id) / cv_data["stored_filename"]
    if not path.exists():
        return redirect(url_for("user_portal.upload_cv"))
    return send_file(
        path,
        as_attachment=False,
        download_name=cv_data["original_filename"],
        mimetype=cv_data.get("mime_type") or None,
        conditional=True,
    )


@user_portal_bp.route("/profile/cv/delete", methods=["POST"])
@login_required
def delete_cv():
    user_id = _current_user_id()
    assert user_id is not None
    if _check_csrf():
        _clear_cv_file(user_id)
    return redirect(url_for("user_portal.upload_cv"))


@user_portal_bp.route("/profile/cv/validate", methods=["GET", "POST"])
@login_required
def validate_cv():
    user_id = _current_user_id()
    assert user_id is not None
    pending = session.get("pending_cv_import")
    if not pending:
        return render_template("cv_validation.html", page_title="Valider CV", active_page="", pending=None, message=None, message_category=None)
    structured = pending.get("structured") or {}
    message = pending.get("message")
    message_category = None
    if request.method == "POST":
        if _check_csrf():
            pending = dict(pending)
            pending["structured"] = _rebuild_cv_payload_from_form(request.form)
            _save_cv_confirmation(user_id, pending)
            flash("CV validé et importé.", "success")
            return redirect(url_for("user_portal.profile"))
        message = "Jeton CSRF invalide ou manquant."
        message_category = "error"
    return render_template(
        "cv_validation.html",
        page_title="Valider CV",
        active_page="",
        pending=pending,
        message=message,
        message_category=message_category,
        formations=structured.get("formations", []),
        competences=structured.get("competences", []),
        experiences_professionnelles=structured.get("experiences_professionnelles", []),
        sections_detectees=structured.get("sections_detectees", {}),
        texte_brut=structured.get("texte_brut") or "",
        warnings=structured.get("warnings", []),
    )


@user_portal_bp.route("/mes-offres")
@login_required
def recommendations():
    user_id = _current_user_id()
    assert user_id is not None
    filters = _recommendation_filters_from_request()
    matches = _compute_recommendations(user_id)
    cache_status = get_cache_status()
    page_matches, total, page = _filter_and_paginate_matches(matches, filters)

    cache_notice = ""
    if not has_precomputed_data():
        cache_notice = (
            '<div class="status error">Aucun précalcul disponible. '
            "Lancez <code>python -m src.jobs.refresh_all</code> pour générer les données.</div>"
        )
    elif not matches:
        last_refresh = get_last_refresh_time()
        if last_refresh:
            cache_notice = (
                f'<div class="status">Dernière actualisation: {last_refresh}. '
                "Aucune offre recommandée pour votre profil.</div>"
            )
        else:
            cache_notice = (
                '<div class="status">Aucun matching précalculé pour votre profil. '
                "Les données seront disponibles après la prochaine actualisation.</div>"
            )

    filter_form = render_template_string(
        """
        {{ cache_notice|safe }}
        <section class="panel">
          <h2>Mes offres</h2>
          <p class="muted">{{ total }} offres triées par score décroissant.</p>
          <form method="get" class="grid">
            <div class="field"><label>Territoire</label><input name="territoire" value="{{ filters.territoire }}"></div>
            <div class="field"><label>Score minimum</label><input name="score_min" type="number" min="0" max="100" value="{{ filters.min_score or '' }}"></div>
            <div class="field"><label>Contrat</label><input name="contrat" value="{{ filters.contract }}"></div>
            <div class="field"><label>Télétravail</label><input name="teletravail" value="{{ filters.remote }}"></div>
            <div class="field"><label>Compétence</label><input name="competence" value="{{ filters.skill }}"></div>
            <div class="field"><label>Métier</label><input name="metier" value="{{ filters.job }}"></div>
            <div class="field"><label>Source</label><input name="source" value="{{ filters.source }}"></div>
            <div class="field"><label>Par page</label><input name="per_page" type="number" min="1" max="50" value="{{ filters.per_page }}"></div>
            <input type="hidden" name="page" value="1">
            <div class="actions"><button class="btn" type="submit">Filtrer</button></div>
          </form>
        </section>
        """,
        filters=filters,
        total=total,
        cache_notice=cache_notice,
    )
    cards_section = _recommendation_page(page_matches, filters, total, page)
    return _render_page("Mes offres", filter_form + cards_section)


@user_portal_bp.route("/recommandation-formation")
@login_required
def training_recommendation():
    territory = _normalize_string(request.args.get("territoire"))
    period_days = _parse_int(request.args.get("periode_jours"), 1, 365) or 30

    if has_precomputed_data():
        offers, error_message = get_precomputed_offers()
        territory_options = get_cached_territory_options()
    else:
        offers, error_message = load_normalized_offers()
        territory_options = get_available_territories(offers)

    context = build_recommendation_context(offers, territoire=territory or None, periode_jours=period_days)
    context["error_message"] = error_message
    context["territoire"] = territory or ""
    context["territory_options"] = territory_options
    context["period_days"] = period_days
    context["page_title"] = "Recommandation de formation"
    context["active_page"] = "training_recommendation"
    if has_precomputed_data():
        context["cache_status"] = get_cache_status()
    return render_template("training_recommendation.html", **context)

@user_portal_bp.route("/mes-offres/<offer_id>")
@login_required
def recommendation_detail(offer_id: str):
    user_id = _current_user_id()
    assert user_id is not None
    match = fetch_one("SELECT * FROM job_matches WHERE user_id = ? AND offer_identifier = ?", (user_id, offer_id))
    if not match:
        return redirect(url_for("user_portal.recommendations"))
    try:
        explanation = json.loads(match["explanation_json"] or "{}")
    except json.JSONDecodeError:
        explanation = {}
    offer = explanation.get("offer") if isinstance(explanation.get("offer"), dict) else {}
    if not offer and isinstance(match.get("offer"), dict):
        offer = match.get("offer")

    match_dict = {
        "offer_identifier": offer_id,
        "offer": offer,
        "global_score": float(explanation.get("global_score") or match.get("global_score") or 0),
        "explanation": explanation,
        "matching_skills": explanation.get("matching_skills") or [],
        "missing_skills": explanation.get("missing_skills") or [],
        "criterion_details": explanation.get("criterion_details") or {},
        "sous_scores": explanation.get("sous_scores") or {},
        "criterion_scores": explanation.get("criterion_scores") or {},
    }
    for key, label in _CRITERION_LABELS.items():
        score_val = (explanation.get("subscores") or {}).get(key)
        if score_val is not None and key not in match_dict["sous_scores"]:
            match_dict["sous_scores"][key] = {"score": float(score_val), "statut": "evalue"}

    vm = build_match_view_model(match_dict, offer, offer_identifier=offer_id)
    offer_url = vm.url or _offer_fallback_url(offer, offer_id)
    global_score = float(vm.global_score or 0)
    summary = explanation.get("summary") or ""

    score_int = int(round(global_score))
    ring_class = _score_ring_class(global_score)
    url_html = ""
    if offer_url:
        url_html = f'            <a class="btn" href="{escape(offer_url)}" target="_blank" rel="noopener noreferrer">Voir l\u2019offre originale</a>'
    else:
        url_html = '<span class="muted">Lien indisponible</span>'

    weight_rows = []
    weights = explanation.get("weights") or explanation.get("matching_weights") or {}
    for key, criterion in vm.criterion_scores.items():
        label = criterion.get("label", key)
        w = weights.get(key)
        if w is not None:
            weight_rows.append(f'<tr><td>{escape(label)}</td><td style="text-align:right;font-variant-numeric:tabular-nums">{float(w):.0f}%</td></tr>')
    weight_table = ""
    if weight_rows:
        weight_table = (
            '<table style="width:100%;border-collapse:collapse;font-size:0.9rem;margin-top:8px">'
            + "".join(weight_rows)
            + "</table>"
        )

    content = render_template_string(
        """
        <section class="panel">
          <div class="offer-card__header">
            <div class="score-ring {{ ring_class }}">{{ score_int }}</div>
            <div class="offer-card__header-text">
              <h2 style="margin:0 0 6px">{{ offer_title }}</h2>
              <div class="meta">
                <span>{{ offer_company }}</span>
                <span>{{ offer_location }}</span>
                <span>{{ offer_contract }}</span>
                <span>{{ offer_source }}</span>
              </div>
              <p class="muted" style="margin:8px 0 0">{{ summary }}</p>
            </div>
          </div>
        </section>

        <section class="panel">
          <h2>Détail du score</h2>
          {{ score_bars|safe }}
        </section>

        <section class="grid">
          <section class="panel">
            <h2>Compétences communes</h2>
            {% if matching_skills %}
            <div class="chips">
              {% for skill in matching_skills %}<span class="skill-tag skill-tag--match">{{ skill }}</span>{% endfor %}
            </div>
            {% else %}
            <div class="muted">Aucune compétence commune détectée.</div>
            {% endif %}
          </section>
          <section class="panel">
            <h2>Compétences manquantes</h2>
            {% if missing_skills %}
            <div class="chips">
              {% for skill in missing_skills %}<span class="skill-tag skill-tag--missing">{{ skill }}</span>{% endfor %}
            </div>
            {% else %}
            <div class="muted">Aucune compétence manquante.</div>
            {% endif %}
          </section>
        </section>

        {% if detail_lines %}
        <section class="panel">
          <h2>Explications</h2>
          <ul>
            {% for line in detail_lines %}<li>{{ line }}</li>{% endfor %}
          </ul>
        </section>
        {% endif %}

        {% if weight_table %}
        <section class="panel">
          <h2>Poids des critères</h2>
          {{ weight_table|safe }}
        </section>
        {% endif %}

        <section class="panel">
          <div class="actions" style="justify-content: space-between;">
            {{ url_html|safe }}
            <a class="btn secondary" href="{{ url_for('user_portal.recommendations') }}">Retour aux offres</a>
          </div>
        </section>
        """,
        ring_class=ring_class,
        score_int=score_int,
        offer_title=vm.title,
        offer_company=vm.company or "Entreprise non renseignée",
        offer_location=vm.location or "Lieu non renseigné",
        offer_contract=vm.contract or "Contrat non renseigné",
        offer_source=vm.source or "Source non renseignée",
        summary=summary,
        score_bars=_render_score_bars(match_dict),
        matching_skills=vm.matched_skills or explanation.get("matching_skills", []),
        missing_skills=vm.missing_skills or explanation.get("missing_skills", []),
        detail_lines=explanation.get("details") or [],
        weight_table=weight_table,
        url_html=url_html,
    )
    return _render_page("Détail offre", content)


@user_portal_bp.route("/dashboard-utilisateur")
@login_required
def dashboard():
    user_id = _current_user_id()
    assert user_id is not None
    matches = _compute_recommendations(user_id)
    compatible = [match for match in matches if float(match.get("global_score") or 0) >= DEFAULT_COMPATIBILITY_THRESHOLD]
    display_matches = compatible[:5] if compatible else matches[:5]
    average = round(sum(float(match.get("global_score") or 0) for match in matches) / len(matches), 2) if matches else 0.0
    best = max(matches, key=lambda item: float(item.get("global_score") or 0), default=None)
    demanded_counter: Counter[str] = Counter()
    missing_counter: Counter[str] = Counter()
    contract_counter: Counter[str] = Counter()
    location_counter: Counter[str] = Counter()

    for match in compatible or matches:
        explanation = _decoded_explanation(match.get("explanation_json"))
        offer = explanation.get("offer") if isinstance(explanation.get("offer"), dict) else {}
        if not offer and isinstance(match.get("offer"), dict):
            offer = match.get("offer")
        vm_dash = build_match_view_model(match, offer)
        for skill in offer.get("competences") or explanation.get("matching_skills", []):
            demanded_counter[str(skill)] += 1
        for skill in explanation.get("missing_skills", []):
            missing_counter[str(skill)] += 1
        contract_counter[str(vm_dash.contract or "Non renseigné")] += 1
        location_label = vm_dash.location or "Non renseigné"
        location_counter[location_label] += 1

    best_explanation = best.get("explanation") if best and isinstance(best.get("explanation"), dict) else _decoded_explanation(best.get("explanation_json")) if best else {}
    if isinstance(best_explanation, dict):
        best_explanation = dict(best_explanation)
        best_explanation["criterion_details"] = best.get("criterion_details") or best_explanation.get("criterion_details") or {}
    best_offer_raw = {}
    if best:
        best_offer_raw = best_explanation.get("offer") if isinstance(best_explanation.get("offer"), dict) else {}
        if not best_offer_raw and isinstance(best.get("offer"), dict):
            best_offer_raw = best.get("offer")
    best_vm = build_match_view_model(best or {}, best_offer_raw) if best else None
    skills_to_develop = missing_counter.most_common(5)
    match_cards = []
    for match in display_matches:
        explanation = _decoded_explanation(match.get("explanation_json"))
        offer = explanation.get("offer") if isinstance(explanation.get("offer"), dict) else {}
        if not offer and isinstance(match.get("offer"), dict):
            offer = match.get("offer")
        vm_card = build_match_view_model(match, offer)
        offer_id = vm_card.offer_id
        detail_url = url_for("user_portal.recommendation_detail", offer_id=offer_id) if offer_id else None
        card_url = vm_card.url
        if not card_url:
            source = str(vm_card.source or "").lower().strip()
            if source in {"", "france travail", "france_travail", "francetravail"}:
                card_url = f"https://candidat.francetravail.fr/offres/recherche/detail/{offer_id}"
            elif detail_url:
                card_url = detail_url

        sub_scores_display = {}
        for key, criterion in vm_card.criterion_scores.items():
            sub_scores_display[key] = {
                "label": criterion.get("label", key),
                "score": criterion.get("score"),
                "evaluated": criterion.get("evaluated", False),
                "reason": criterion.get("reason", ""),
            }

        match_cards.append({
            "title": vm_card.title,
            "company": vm_card.company or "Entreprise non renseignée",
            "location": vm_card.location or "Lieu non renseigné",
            "contract": vm_card.contract or "Contrat non renseigné",
            "source": vm_card.source or "Source non renseignée",
            "score": float(vm_card.global_score or 0),
            "url": card_url,
            "detail_url": detail_url,
            "matching_skills": vm_card.matched_skills or explanation.get("matching_skills", []),
            "missing_skills": vm_card.missing_skills or explanation.get("missing_skills", []),
            "criterion_scores": sub_scores_display,
        })
    content = render_template_string(
        """
        <section class="dash-grid">
          <div class="metric"><div class="label">Offres compat.</div><div class="value">{{ compatible_count }}</div></div>
          <div class="metric"><div class="label">Score moyen</div><div class="value">{{ average }}%</div></div>
          <div class="metric"><div class="label">Meilleure offre</div><div class="value">{{ best_score }}%</div></div>
          <div class="metric"><div class="label">Dernier calcul</div><div class="value">{{ last_calculated or '—' }}</div></div>
        </section>
        <section class="panel">
          <div class="actions" style="justify-content: space-between;">
            <h2>Offres compatibles</h2>
            {% if compatible_count == 0 %}<span class="muted">Aucune offre au-dessus du seuil, affichage des meilleures correspondances.</span>{% endif %}
          </div>
          {% if match_cards %}
          <div class="offer-grid">
            {% for card in match_cards %}
            <article class="offer-card">
              <h3 class="offer-title">{{ card.title }}</h3>
              <div class="meta">
                <span>{{ card.company }}</span>
                <span>{{ card.location }}</span>
                <span>{{ card.contract }}</span>
                <span>{{ card.source }}</span>
                <span>Score {{ '%.0f'|format(card.score) }}/100</span>
              </div>
              {% if card.matching_skills %}
              <div class="chips">
                {% for skill in card.matching_skills[:5] %}<span class="chip">{{ skill }}</span>{% endfor %}
              </div>
              {% endif %}
              <div class="actions">
                {% if card.url %}<a class="btn" href="{{ card.url }}" target="_blank" rel="noopener noreferrer">Voir l’offre</a>{% else %}<span class="muted">Lien indisponible</span>{% endif %}
              </div>
            </article>
            {% endfor %}
          </div>
          {% else %}
          <div class="muted">Aucune offre calculée.</div>
          {% endif %}
        </section>
        <section class="grid">
          <section class="panel">
            <h2>Meilleure offre</h2>
            {% if best_vm %}
            <article class="offer-card offer-card--highlight">
              <h3 class="offer-title">{{ best_vm.title }}</h3>
              <div class="meta">
                <span>{{ best_vm.company or 'Entreprise non renseignée' }}</span>
                <span>{{ best_vm.location or 'Lieu non renseigné' }}</span>
                <span>{{ best_vm.contract or 'Contrat non renseigné' }}</span>
                <span>Score {{ '%.0f'|format(best_vm.global_score or 0) }}/100</span>
              </div>
              <p class="muted">{{ best_explanation.get('summary') }}</p>
              {% if best_vm.criterion_scores %}
              <div class="muted small">
                {% for key, criterion in best_vm.criterion_scores.items() %}
                {% if criterion.evaluated %}
                <div>{{ criterion.label }}: {{ '%.0f'|format(criterion.score) }}/100{% if criterion.reason %} — {{ criterion.reason }}{% endif %}</div>
                {% endif %}
                {% endfor %}
              </div>
              {% endif %}
              {% if best_vm.matched_skills %}
              <div class="chips">
                {% for skill in best_vm.matched_skills[:5] %}<span class="chip">{{ skill }}</span>{% endfor %}
              </div>
              {% endif %}
              <div class="actions">
                {% if best_vm.url %}<a class="btn" href="{{ best_vm.url }}" target="_blank" rel="noopener noreferrer">Voir l'offre</a>{% elif best_vm.offer_id %}<a class="btn" href="{{ url_for('user_portal.recommendation_detail', offer_id=best_vm.offer_id) }}">Voir l'offre</a>{% else %}<span class="muted">Lien indisponible</span>{% endif %}
              </div>
            </article>
            {% else %}
            <div class="muted">Aucune offre calculée.</div>
            {% endif %}
          </section>
          <section class="panel">
            <h2>Compétences à développer</h2>
            {% if skills_to_develop %}
            <ul>
              {% for skill, count in skills_to_develop %}
              <li>{{ skill }} — manquante dans {{ count }} offres compatibles</li>
              {% endfor %}
            </ul>
            {% else %}
            <div class="muted">Aucune compétence manquante prioritaire.</div>
            {% endif %}
          </section>
          <section class="panel">
            <h2>Compétences les plus demandées</h2>
            {% if demanded_skills %}
            <ul>{% for skill, count in demanded_skills %}<li>{{ skill }} — {{ count }} offres compatibles</li>{% endfor %}</ul>
            {% else %}<div class="muted">Aucune compétence demandée disponible.</div>{% endif %}
          </section>
          <section class="panel">
            <h2>Répartition des contrats</h2>
            {% if contract_distribution %}
            <ul>{% for label, count in contract_distribution %}<li>{{ label }} — {{ count }} offres</li>{% endfor %}</ul>
            {% else %}<div class="muted">Aucun contrat disponible.</div>{% endif %}
          </section>
          <section class="panel">
            <h2>Répartition géographique</h2>
            {% if location_distribution %}
            <ul>{% for label, count in location_distribution %}<li>{{ label }} — {{ count }} offres</li>{% endfor %}</ul>
            {% else %}<div class="muted">Aucune localisation disponible.</div>{% endif %}
          </section>
        </section>
        """,
        compatible_count=len(compatible),
        average=average,
        best_score=round(float(best["global_score"]) if best else 0.0, 2),
        best=best,
        best_explanation=best_explanation,
        best_vm=best_vm,
        last_calculated=max((match.get("calculated_at") for match in matches if match.get("calculated_at")), default="—"),
        skills_to_develop=skills_to_develop,
        demanded_skills=demanded_counter.most_common(5),
        contract_distribution=contract_counter.most_common(),
        location_distribution=location_counter.most_common(5),
        match_cards=match_cards,
    )
    return _render_page("Tableau de bord utilisateur", content)


@user_portal_bp.route("/profile/export-data")
@login_required
def export_data():
    user_id = _current_user_id()
    assert user_id is not None
    payload = _export_user_data_payload(user_id)
    response = current_app.response_class(
        json.dumps(payload, ensure_ascii=False, indent=2),
        mimetype="application/json; charset=utf-8",
    )
    response.headers["Content-Disposition"] = f'attachment; filename="trendradar-donnees-{user_id}.json"'
    return response


@user_portal_bp.route("/profile/delete-account", methods=["POST"])
@login_required
def delete_account():
    user_id = _current_user_id()
    assert user_id is not None
    if _check_csrf():
        _delete_all_user_data(user_id)
        _logout_user()
        flash("Votre compte et vos données ont été supprimés.", "success")
        return redirect(url_for("user_portal.register"))
    return redirect(url_for("user_portal.profile"))


@user_portal_bp.route("/profile/delete-all", methods=["POST"])
@login_required
def delete_all_data():
    return delete_account()


def register_user_portal(app) -> None:
    _ensure_app_config(app)
    app.register_blueprint(user_portal_bp)
    init_db(app)
    init_db_teardown(app)

