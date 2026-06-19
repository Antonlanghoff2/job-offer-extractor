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
from typing import Any, Callable, Iterable

from flask import Blueprint, current_app, g, redirect, render_template_string, request, session, url_for
from markupsafe import escape
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from src.db import execute, fetch_all, fetch_one, init_app as init_db_teardown, init_db, transaction, utcnow_iso
from src.offer_normalization import normalize_text
from src.services.cv_parser import parse_cv_file
from src.services.matching_service import compute_match, normalize_skill_name

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
      --bg: #f4f7fb;
      --surface: #ffffff;
      --surface-alt: #eef4fb;
      --text: #132033;
      --muted: #5a6a7f;
      --line: #d7e0ea;
      --accent: #1866d1;
      --accent-2: #0f8b8d;
      --danger: #bb3e3e;
      --success: #13795b;
      --shadow: 0 12px 28px rgba(19, 32, 51, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: linear-gradient(180deg, #eef4fb 0%, #f7f9fc 100%);
      color: var(--text);
      font-family: Inter, "Segoe UI", system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
    }
    header {
      padding: 20px 24px 16px;
      background: linear-gradient(135deg, #123055, #184f8f 65%, #176a9b);
      color: white;
    }
    header h1 { margin: 0; font-size: 28px; line-height: 1.15; }
    header p { margin: 8px 0 0; color: rgba(255, 255, 255, 0.82); max-width: 940px; }
    .topnav {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 14px;
    }
    .topnav a {
      color: white;
      text-decoration: none;
      border: 1px solid rgba(255,255,255,0.28);
      padding: 8px 12px;
      border-radius: 999px;
      font-weight: 700;
      font-size: 14px;
    }
    .shell { padding: 18px 22px 28px; }
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
  </style>
</head>
<body>
  <header>
    <h1>TrendRadar IA</h1>
    <p>Espace utilisateur privé, recommandations déterministes et import contrôlé du CV.</p>
    <nav class="topnav">
      <a href="{{ url_for('user_portal.profile') }}">Mon profil</a>
      <a href="{{ url_for('user_portal.upload_cv') }}">Mon CV</a>
      <a href="{{ url_for('user_portal.recommendations') }}">Mes offres</a>
      <a href="{{ url_for('user_portal.dashboard') }}">Mon tableau de bord</a>
      <a href="{{ url_for('user_portal.logout') }}">Déconnexion</a>
    </nav>
  </header>
  <main class="shell">
    {% if message %}
    <div class="status {{ message_category or '' }}">{{ message }}</div>
    {% endif %}
    {{ content|safe }}
  </main>
</body>
</html>
"""


def _ensure_app_config(app) -> None:
    app.config.setdefault("MAX_CONTENT_LENGTH", DEFAULT_MAX_UPLOAD_BYTES)
    app.config.setdefault(
        "UPLOAD_FOLDER",
        str(Path(app.instance_path) / UPLOAD_FOLDER_NAME),
    )
    secret_key = app.config.get("SECRET_KEY") or os.getenv("SECRET_KEY", "trendradar-dev-secret")
    app.config["SECRET_KEY"] = secret_key
    app.secret_key = secret_key


def _db_path() -> Path:
    return Path(current_app.config.get("UPLOAD_FOLDER")).parent / "trendradar.sqlite"


def _uploads_root() -> Path:
    root = Path(current_app.config.get("UPLOAD_FOLDER"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _current_user_id() -> int | None:
    user_id = session.get("user_id")
    if isinstance(user_id, int):
        return user_id
    if isinstance(user_id, str) and user_id.isdigit():
        return int(user_id)
    return None


def _get_user(user_id: int | None = None) -> dict[str, Any] | None:
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


def _require_login() -> int | None:
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


def _csrf_error() -> str | None:
    return None if _check_csrf() else "Jeton CSRF invalide ou manquant."


def _normalize_string(value: object) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalize_lookup(value: object) -> str:
    return normalize_text(value)


def _parse_int(value: object, minimum: int | None = None, maximum: int | None = None) -> int | None:
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


def _parse_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def _parse_date(value: object) -> str | None:
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


def _load_local_offers() -> list[dict[str, Any]]:
    from src.web_app import load_raw_offers

    try:
        return load_raw_offers()
    except Exception:
        return []


def _normalize_offer(raw_offer: dict[str, Any]) -> dict[str, Any]:
    from src.services.offer_normalization import normalize_offer_for_matching

    return normalize_offer_for_matching(raw_offer, source=raw_offer.get("source") or "France Travail")


def _assemble_profile(user_id: int) -> dict[str, Any]:
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


def _skill_payload_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": row.get("name") or row.get("skill_name") or "",
        "normalized_name": row.get("normalized_name") or normalize_skill_name(row.get("name") or row.get("skill_name") or ""),
        "level": row.get("level") or "",
        "years_experience": row.get("years_experience"),
        "source": row.get("source") or "manual",
    }


def _store_skill(user_id: int, name: str, level: str | None, years_experience: float | None, source: str) -> None:
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


def _parse_multi_values(raw_value: object) -> list[str]:
    if raw_value in (None, ""):
        return []
    values = []
    for part in re.split(r"[,\n;|]", str(raw_value)):
        text = _normalize_string(part)
        if text:
            values.append(text)
    return values


def _render_page(title: str, content: str, *, message: str | None = None, message_category: str | None = None, **context: Any):
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


def _auth_block(form_action: str, title: str, submit_label: str, next_url: str = "", error: str | None = None) -> str:
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


def _profile_form(profile: dict[str, Any], desired_jobs_text: str) -> str:
    return render_template_string(
        """
        <section class="panel">
          <h2>Mon profil</h2>
          <form method="post">
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
            <div class="actions"><button class="btn" type="submit">Enregistrer</button></div>
          </form>
        </section>
        """,
        profile=profile,
        desired_jobs_text=desired_jobs_text,
        remote_options=REMOTE_OPTIONS,
        contract_options=CONTRACT_OPTIONS,
        csrf_token=_csrf_token,
    )


def _list_section(title: str, items: list[dict[str, Any]], columns: list[tuple[str, str]], add_url: str, empty_label: str) -> str:
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


def _validate_required_csrf() -> str | None:
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


def _authenticate_user(email: str, password: str) -> int | None:
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


def _render_skill_form(skill: dict[str, Any] | None = None) -> str:
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


def _render_diploma_form(diploma: dict[str, Any] | None = None) -> str:
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


def _render_experience_form(experience: dict[str, Any] | None = None) -> str:
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


def _list_view_items(user_id: int, table: str) -> list[dict[str, Any]]:
    rows = fetch_all(f"SELECT * FROM {table} WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    return [dict(row) for row in rows]


def _item_map(items: list[dict[str, Any]], edit_route: str, delete_route: str) -> list[dict[str, Any]]:
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


def _calculate_duration_years(start_date: str | None, end_date: str | None, is_current: int) -> float | None:
    try:
        start = date.fromisoformat(start_date) if start_date else None
        if not start:
            return None
        end = date.today() if is_current else date.fromisoformat(end_date) if end_date else date.today()
        return round(max((end - start).days / 365.25, 0.0), 2)
    except Exception:
        return None


def _profile_dict(user_id: int) -> dict[str, Any]:
    profile = _assemble_profile(user_id)
    profile_row = {k: profile.get(k) for k in ("first_name", "last_name", "city", "postal_code", "department", "search_radius_km", "remote_preference", "minimum_salary", "availability", "summary")}
    profile_row["desired_jobs_text"] = "\n".join(item["job_title"] for item in profile["desired_jobs"])
    return profile_row


def _store_cv(user_id: int, file_storage) -> dict[str, Any]:
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


def _save_cv_confirmation(user_id: int, pending: dict[str, Any]) -> None:
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
    structured = pending.get("structured") or {}
    for skill in structured.get("competences", []):
        _store_skill(user_id, skill.get("nom", ""), skill.get("niveau"), skill.get("annees_experience"), "cv")
    for diploma in structured.get("diplomes", []):
        now = utcnow_iso()
        with transaction() as conn:
            conn.execute(
                """
                INSERT INTO diplomas(user_id, title, level, institution, speciality, graduation_year, description, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    diploma.get("intitule") or "",
                    diploma.get("niveau"),
                    diploma.get("etablissement"),
                    None,
                    diploma.get("annee"),
                    diploma.get("description") or "",
                    "cv",
                    now,
                    now,
                ),
            )
    for experience in structured.get("experiences", []):
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
                    None,
                    _parse_date(experience.get("date_debut")),
                    _parse_date(experience.get("date_fin")),
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


def _rebuild_cv_payload_from_form(form) -> dict[str, Any]:
    skills = []
    skill_names = form.getlist("skill_name")
    skill_levels = form.getlist("skill_level")
    skill_years = form.getlist("skill_years")
    for index, name in enumerate(skill_names):
        name = _normalize_string(name)
        if not name:
            continue
        skills.append({
            "nom": name,
            "niveau": _normalize_string(skill_levels[index]) if index < len(skill_levels) else None,
            "annees_experience": _parse_float(skill_years[index]) if index < len(skill_years) else None,
        })
    diplomas = []
    diploma_titles = form.getlist("diploma_title")
    diploma_levels = form.getlist("diploma_level")
    diploma_schools = form.getlist("diploma_school")
    diploma_years = form.getlist("diploma_year")
    for index, title in enumerate(diploma_titles):
        title = _normalize_string(title)
        if not title:
            continue
        diplomas.append({
            "intitule": title,
            "niveau": _normalize_string(diploma_levels[index]) if index < len(diploma_levels) else None,
            "etablissement": _normalize_string(diploma_schools[index]) if index < len(diploma_schools) else None,
            "annee": _parse_int(diploma_years[index], 1900, 2100) if index < len(diploma_years) else None,
            "description": "",
        })
    experiences = []
    experience_jobs = form.getlist("experience_job")
    experience_companies = form.getlist("experience_company")
    experience_starts = form.getlist("experience_start")
    experience_ends = form.getlist("experience_end")
    experience_descs = form.getlist("experience_desc")
    for index, job_title in enumerate(experience_jobs):
        job_title = _normalize_string(job_title)
        if not job_title:
            continue
        experiences.append({
            "poste": job_title,
            "entreprise": _normalize_string(experience_companies[index]) if index < len(experience_companies) else None,
            "date_debut": _parse_date(experience_starts[index]) if index < len(experience_starts) else None,
            "date_fin": _parse_date(experience_ends[index]) if index < len(experience_ends) else None,
            "description": _normalize_string(experience_descs[index]) if index < len(experience_descs) else "",
        })
    return {
        "competences": skills,
        "diplomes": diplomas,
        "experiences": experiences,
        "metiers_detectes": [],
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


def _current_profile_snapshot(user_id: int) -> dict[str, Any]:
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


def _offer_matches_filters(offer: dict[str, Any], filters: dict[str, Any], match: dict[str, Any]) -> bool:
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


def _current_job_matches(user_id: int) -> list[dict[str, Any]]:
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


def _explanation_with_offer_summary(match: dict[str, Any]) -> dict[str, Any]:
    explanation = dict(match.get("explanation") or {})
    offer = match.get("offer") or {}
    explanation["offer"] = {
        "titre": offer.get("titre"),
        "contrat": offer.get("contrat"),
        "lieux": offer.get("lieux") or [],
        "competences": offer.get("competences") or [],
        "source": offer.get("source"),
        "url_originale": offer.get("url_originale"),
    }
    return explanation


def _decoded_explanation(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            payload = json.loads(value or "{}")
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}
    return {}


def _persist_match(user_id: int, match: dict[str, Any]) -> None:
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


def _compute_recommendations(user_id: int) -> list[dict[str, Any]]:
    profile = _current_profile_snapshot(user_id)
    offers = [_normalize_offer(offer) for offer in _load_local_offers()]
    matches = []
    for raw_offer in offers:
        result = compute_match(profile, raw_offer)
        result["offer"] = {**result["offer"], **raw_offer}
        _persist_match(user_id, result)
        matches.append(result)
    return matches


def _recommendation_filters_from_request() -> dict[str, Any]:
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


def _filter_and_paginate_matches(matches: list[dict[str, Any]], filters: dict[str, Any]) -> tuple[list[dict[str, Any]], int, int]:
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


def _build_query_string(params: dict[str, Any]) -> str:
    from urllib.parse import urlencode

    return urlencode({key: value for key, value in params.items() if value not in (None, "")})


def _recommendation_page(matches: list[dict[str, Any]], filters: dict[str, Any], total: int, page: int) -> str:
    if not matches:
        cards_html = "<div class='muted'>Aucune offre ne correspond à cette recherche.</div>"
    else:
        cards = []
        for match in matches:
            offer = match["offer"]
            explanation = match.get("explanation", {})
            url = offer.get("url_originale")
            cards.append(
                f"""
                <article class="offer-card">
                  <h3 class="offer-title">{escape(offer.get('titre') or 'Offre sans titre')}</h3>
                  <div class="meta">
                    <span>{escape(offer.get('entreprise') or 'Entreprise non renseignée')}</span>
                    <span>{escape(offer.get('lieux') and ', '.join(offer.get('lieux')) or 'Lieu non renseigné')}</span>
                    <span>{escape(offer.get('contrat') or 'Contrat non renseigné')}</span>
                    <span>{escape(offer.get('teletravail') or 'Télétravail non renseigné')}</span>
                    <span>{escape(offer.get('source') or 'Source non renseignée')}</span>
                    <span>Score {float(match.get('global_score') or 0):.0f}/100</span>
                  </div>
                  <div class="small">
                    Sous-scores: compétences {float(match.get('skill_score') or 0):.0f}, métier {float(match.get('job_score') or 0):.0f}, expérience {float(match.get('experience_score') or 0):.0f}, diplôme {float(match.get('diploma_score') or 0):.0f}, localisation {float(match.get('location_score') or 0):.0f}, contrat {float(match.get('contract_score') or 0):.0f}, télétravail {float(match.get('remote_score') or 0):.0f}.
                    <br>
                    Compétences communes: {escape(', '.join(match.get('matching_skills') or []) or 'aucune')}
                    <br>
                    Compétences manquantes: {escape(', '.join(match.get('missing_skills') or []) or 'aucune')}
                  </div>
                  <div class="explain">
                    {escape(explanation.get('summary') or '')}
                    {"<br>" + escape(' '.join(explanation.get('details') or [])) if explanation.get('details') else ''}
                  </div>
                  <div class="actions" style="margin-top: 10px;">
                    {f"<a class='btn' href='{escape(url)}' target='_blank' rel='noopener noreferrer'>Voir l’offre</a>" if url else "<span class='muted'>Lien indisponible</span>"}
                  </div>
                </article>
                """
            )
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
def _inject_csrf() -> dict[str, Any]:
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
            try:
                _save_profile(user_id)
                flash("Profil enregistré.", "success")
                return redirect(url_for("user_portal.profile"))
            except ValueError as exc:
                error = str(exc)
    profile_data = _current_profile_snapshot(user_id)
    content = _profile_form(profile_data, "\n".join(item["job_title"] if isinstance(item, dict) else str(item) for item in profile_data["desired_jobs"]))
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
        _list_view_items(user_id, "user_skills"),
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
          <form method="post" action="{{ url_for('user_portal.delete_cv') }}">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <button class="btn danger" type="submit">Supprimer mon CV</button>
          </form>
          {% endif %}
        </section>
        """,
        cv_row=dict(cv_row) if cv_row else None,
        csrf_token=_csrf_token,
    )
    return _render_page("Mon CV", content, message=message, message_category=message_category)


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
        return _render_page("Valider CV", "<section class='panel'><h2>Validation du CV</h2><div class='muted'>Aucun import en attente.</div></section>")
    structured = pending.get("structured") or {}
    message = pending.get("message")
    if request.method == "POST":
        if _check_csrf():
            pending = dict(pending)
            pending["structured"] = _rebuild_cv_payload_from_form(request.form)
            _save_cv_confirmation(user_id, pending)
            flash("CV validé et importé.", "success")
            return redirect(url_for("user_portal.profile"))
        message = "Jeton CSRF invalide ou manquant."
    skills = structured.get("competences", [])
    diplomas = structured.get("diplomes", [])
    experiences = structured.get("experiences", [])
    content = render_template_string(
        """
        <section class="panel">
          <h2>Valider les informations extraites</h2>
          {% if message %}<div class="status error">{{ message }}</div>{% endif %}
          <form method="post">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <h3>Compétences</h3>
            {% for item in skills %}
            <div class="pairs">
              <div class="field"><label>Nom</label><input name="skill_name" value="{{ item['nom'] }}"></div>
              <div class="field"><label>Niveau</label><input name="skill_level" value="{{ item['niveau'] or '' }}"></div>
              <div class="field"><label>Années</label><input name="skill_years" value="{{ item['annees_experience'] or '' }}"></div>
            </div>
            {% endfor %}
            <h3>Diplômes</h3>
            {% for item in diplomas %}
            <div class="pairs">
              <div class="field"><label>Intitulé</label><input name="diploma_title" value="{{ item['intitule'] }}"></div>
              <div class="field"><label>Niveau</label><input name="diploma_level" value="{{ item['niveau'] or '' }}"></div>
              <div class="field"><label>Établissement</label><input name="diploma_school" value="{{ item['etablissement'] or '' }}"></div>
              <div class="field"><label>Année</label><input name="diploma_year" value="{{ item['annee'] or '' }}"></div>
            </div>
            {% endfor %}
            <h3>Expériences</h3>
            {% for item in experiences %}
            <div class="pairs">
              <div class="field"><label>Poste</label><input name="experience_job" value="{{ item['poste'] }}"></div>
              <div class="field"><label>Entreprise</label><input name="experience_company" value="{{ item['entreprise'] or '' }}"></div>
              <div class="field"><label>Date début</label><input name="experience_start" value="{{ item['date_debut'] or '' }}"></div>
              <div class="field"><label>Date fin</label><input name="experience_end" value="{{ item['date_fin'] or '' }}"></div>
              <div class="field"><label>Description</label><textarea name="experience_desc">{{ item['description'] or '' }}</textarea></div>
            </div>
            {% endfor %}
            <div class="actions">
              <button class="btn" type="submit">Confirmer l'import</button>
              <a class="btn secondary" href="{{ url_for('user_portal.upload_cv') }}">Retour</a>
            </div>
          </form>
        </section>
        """,
        skills=skills,
        diplomas=diplomas,
        experiences=experiences,
        message=message,
        csrf_token=_csrf_token,
    )
    return _render_page("Valider CV", content)


@user_portal_bp.route("/mes-offres")
@login_required
def recommendations():
    user_id = _current_user_id()
    assert user_id is not None
    filters = _recommendation_filters_from_request()
    matches = _compute_recommendations(user_id)
    page_matches, total, page = _filter_and_paginate_matches(matches, filters)
    filter_form = render_template_string(
        """
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
    )
    cards_section = _recommendation_page(page_matches, filters, total, page)
    return _render_page("Mes offres", filter_form + cards_section)


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
    content = render_template_string(
        """
        <section class="panel">
          <h2>Détail de la recommandation</h2>
          <p class="muted">{{ explanation.get('summary') }}</p>
          <pre style="white-space: pre-wrap; background: #f7fbff; border: 1px solid var(--line); padding: 12px; border-radius: 8px;">{{ explanation|tojson(indent=2) }}</pre>
          <div class="actions">
            <a class="btn secondary" href="{{ url_for('user_portal.recommendations') }}">Retour</a>
          </div>
        </section>
        """,
        explanation=explanation,
    )
    return _render_page("Détail offre", content)


@user_portal_bp.route("/dashboard-utilisateur")
@login_required
def dashboard():
    user_id = _current_user_id()
    assert user_id is not None
    matches = _current_job_matches(user_id)
    compatible = [match for match in matches if float(match.get("global_score") or 0) >= DEFAULT_COMPATIBILITY_THRESHOLD]
    average = round(sum(float(match.get("global_score") or 0) for match in matches) / len(matches), 2) if matches else 0.0
    best = max(matches, key=lambda item: float(item.get("global_score") or 0), default=None)
    demanded_counter: Counter[str] = Counter()
    missing_counter: Counter[str] = Counter()
    contract_counter: Counter[str] = Counter()
    location_counter: Counter[str] = Counter()

    for match in compatible:
        explanation = _decoded_explanation(match.get("explanation_json"))
        offer = explanation.get("offer") if isinstance(explanation.get("offer"), dict) else {}
        for skill in offer.get("competences") or explanation.get("matching_skills", []):
            demanded_counter[str(skill)] += 1
        for skill in explanation.get("missing_skills", []):
            missing_counter[str(skill)] += 1
        contract_counter[str(offer.get("contrat") or "Non renseigné")] += 1
        locations = offer.get("lieux") or []
        if isinstance(locations, str):
            location_label = locations
        elif locations:
            location_label = str(locations[0])
        else:
            location_label = "Non renseigné"
        location_counter[location_label] += 1

    best_explanation = _decoded_explanation(best.get("explanation_json")) if best else {}
    skills_to_develop = missing_counter.most_common(5)
    content = render_template_string(
        """
        <section class="dash-grid">
          <div class="metric"><div class="label">Offres compatibles</div><div class="value">{{ compatible_count }}</div></div>
          <div class="metric"><div class="label">Score moyen</div><div class="value">{{ average }}%</div></div>
          <div class="metric"><div class="label">Meilleure offre</div><div class="value">{{ best_score }}%</div></div>
          <div class="metric"><div class="label">Dernier calcul</div><div class="value">{{ last_calculated or '—' }}</div></div>
        </section>
        <section class="grid">
          <section class="panel">
            <h2>Meilleure offre</h2>
            {% if best %}
            <p><strong>{{ best['offer_identifier'] }}</strong></p>
            <p class="muted">{{ best_explanation.get('summary') }}</p>
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
        last_calculated=max((match.get("calculated_at") for match in matches), default="—"),
        skills_to_develop=skills_to_develop,
        demanded_skills=demanded_counter.most_common(5),
        contract_distribution=contract_counter.most_common(),
        location_distribution=location_counter.most_common(5),
    )
    return _render_page("Tableau de bord utilisateur", content)


@user_portal_bp.route("/profile/delete-all", methods=["POST"])
@login_required
def delete_all_data():
    user_id = _current_user_id()
    assert user_id is not None
    if _check_csrf():
        _delete_all_user_data(user_id)
        _logout_user()
        return redirect(url_for("user_portal.register"))
    return redirect(url_for("user_portal.profile"))


def register_user_portal(app) -> None:
    _ensure_app_config(app)
    app.register_blueprint(user_portal_bp)
    init_db(app)
    init_db_teardown(app)

