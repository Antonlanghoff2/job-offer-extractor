# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""SQLite persistence helpers for TrendRadar IA user features."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from flask import current_app, g

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "instance" / "trendradar.sqlite"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def get_database_path(app=None) -> Path:
    if app is None:
        app = current_app._get_current_object()
    configured = app.config.get("DATABASE_PATH")
    if configured:
        return Path(configured)
    uri = app.config.get("DATABASE_URI") or app.config.get("SQLITE_DATABASE_URI")
    if uri and str(uri).startswith("sqlite:///"):
        return Path(str(uri)[len("sqlite:///"):])
    return DEFAULT_DB_PATH


def get_connection() -> sqlite3.Connection:
    conn = g.get("db_conn")
    if conn is None:
        db_path = get_database_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db_conn = conn
    return conn


def close_connection(exc: Optional[Exception] = None) -> None:
    conn = g.pop("db_conn", None)
    if conn is not None:
        conn.close()


def init_app(app) -> None:
    app.teardown_appcontext(close_connection)


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    first_name TEXT,
    last_name TEXT,
    city TEXT,
    postal_code TEXT,
    department TEXT,
    search_radius_km INTEGER,
    contract_preference TEXT,
    remote_preference TEXT,
    minimum_salary INTEGER,
    availability TEXT,
    summary TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS desired_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_title TEXT NOT NULL,
    normalized_job_title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS skills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_skills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    skill_id INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    level TEXT,
    years_experience REAL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(user_id, skill_id, source)
);

CREATE TABLE IF NOT EXISTS diplomas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    level TEXT,
    institution TEXT,
    speciality TEXT,
    graduation_year INTEGER,
    description TEXT,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS experiences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_title TEXT NOT NULL,
    company TEXT,
    city TEXT,
    start_date TEXT,
    end_date TEXT,
    is_current INTEGER NOT NULL DEFAULT 0,
    description TEXT,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS experience_skills (
    experience_id INTEGER NOT NULL REFERENCES experiences(id) ON DELETE CASCADE,
    skill_id INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    PRIMARY KEY (experience_id, skill_id)
);

CREATE TABLE IF NOT EXISTS user_cvs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    original_filename TEXT NOT NULL,
    stored_filename TEXT NOT NULL,
    mime_type TEXT,
    uploaded_at TEXT NOT NULL,
    extracted_text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    offer_identifier TEXT NOT NULL,
    global_score REAL NOT NULL,
    skill_score REAL,
    job_score REAL,
    experience_score REAL,
    diploma_score REAL,
    location_score REAL,
    contract_score REAL,
    remote_score REAL,
    matching_skills_json TEXT,
    missing_skills_json TEXT,
    explanation_json TEXT,
    calculated_at TEXT NOT NULL,
    UNIQUE(user_id, offer_identifier)
);

CREATE INDEX IF NOT EXISTS idx_job_matches_user_score ON job_matches(user_id, global_score DESC);
CREATE INDEX IF NOT EXISTS idx_desired_jobs_user ON desired_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_user_skills_user ON user_skills(user_id);
CREATE INDEX IF NOT EXISTS idx_diplomas_user ON diplomas(user_id);
CREATE INDEX IF NOT EXISTS idx_experiences_user ON experiences(user_id);
"""


def init_db(app=None) -> None:
    if app is None:
        app = current_app._get_current_object()
    db_path = get_database_path(app)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(SCHEMA_SQL)
        _ensure_user_profile_columns(conn)
        conn.commit()
    finally:
        conn.close()


def _ensure_user_profile_columns(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(user_profiles)").fetchall()}
    if "contract_preference" not in existing:
        conn.execute("ALTER TABLE user_profiles ADD COLUMN contract_preference TEXT")


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def fetch_one(query: str, params: tuple = ()):
    return get_connection().execute(query, params).fetchone()


def fetch_all(query: str, params: tuple = ()):
    return get_connection().execute(query, params).fetchall()


def execute(query: str, params: tuple = ()) -> int:
    cursor = get_connection().execute(query, params)
    get_connection().commit()
    return int(cursor.lastrowid)
