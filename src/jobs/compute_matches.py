# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Calcul des matchings utilisateur-offre.

Ce module précalcule les matchings pour tous les profils utilisateurs.
Il lit les profils depuis SQLite, calcule les matchings contre toutes
les offres enrichies, et écrit les résultats dans matches.json et
dans la table job_matches de SQLite.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.jobs.cache import cache_store, compute_hash
from src.jobs.status import task_status
from src.services.matching_service import compute_match
from src.services.offer_normalization import normalize_offer_for_matching

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENRICHED_OFFERS_PATH = PROJECT_ROOT / "data" / "processed" / "offres_enrichies.json"
MATCHES_PATH = PROJECT_ROOT / "data" / "processed" / "matches.json"
DB_PATH = PROJECT_ROOT / "instance" / "trendradar.sqlite"
MATCHES_CACHE_VERSION = "2.0"


def _utcnow_iso() -> str:
    """Retourne l'heure UTC courante au format ISO."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _open_db() -> sqlite3.Connection:
    """Ouvre une connexion SQLite directe.

    Returns:
        Connexion SQLite avec row_factory activé.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _get_user_ids(conn: sqlite3.Connection) -> List[int]:
    """Retourne la liste des identifiants utilisateurs.

    Args:
        conn: Connexion SQLite.

    Returns:
        Liste des user_id.
    """
    rows = conn.execute("SELECT id FROM users ORDER BY id").fetchall()
    return [row["id"] for row in rows]


def _assemble_profile_from_db(conn: sqlite3.Connection, user_id: int) -> Dict[str, Any]:
    """Assemble le profil complet d'un utilisateur depuis SQLite.

    Args:
        conn: Connexion SQLite.
        user_id: Identifiant utilisateur.

    Returns:
        Profil utilisateur complet.
    """
    profile_row = conn.execute(
        "SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)
    ).fetchone()

    desired_jobs = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM desired_jobs WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    ]

    skills = [
        dict(row)
        for row in conn.execute(
            """
            SELECT us.*, s.name, s.normalized_name
            FROM user_skills us
            JOIN skills s ON s.id = us.skill_id
            WHERE us.user_id = ?
            ORDER BY s.normalized_name ASC
            """,
            (user_id,),
        ).fetchall()
    ]

    diplomas = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM diplomas WHERE user_id = ? ORDER BY graduation_year DESC, created_at DESC",
            (user_id,),
        ).fetchall()
    ]

    experiences = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM experiences WHERE user_id = ? ORDER BY start_date DESC, created_at DESC",
            (user_id,),
        ).fetchall()
    ]

    experience_skills: Dict[int, List[str]] = defaultdict(list)
    for row in conn.execute(
        """
        SELECT es.experience_id, s.name
        FROM experience_skills es
        JOIN skills s ON s.id = es.skill_id
        JOIN experiences e ON e.id = es.experience_id
        WHERE e.user_id = ?
        """,
        (user_id,),
    ).fetchall():
        experience_skills[int(row["experience_id"])].append(row["name"])

    cv_row = conn.execute(
        "SELECT * FROM user_cvs WHERE user_id = ?", (user_id,)
    ).fetchone()

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


def _profile_snapshot(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Transforme un profil assemblé en snapshot pour le matching.

    Args:
        profile: Profil assemblé depuis la base.

    Returns:
        Snapshot de profil pour le matching.
    """
    desired_jobs = [
        {
            "job_title": item.get("job_title") or "",
            "normalized_job_title": item.get("normalized_job_title") or "",
        }
        for item in profile.get("desired_jobs", [])
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
        "skills": [
            {
                "name": item.get("name") or "",
                "normalized_name": item.get("normalized_name") or "",
                "level": item.get("level") or "",
                "years_experience": item.get("years_experience"),
                "source": item.get("source") or "manual",
            }
            for item in profile.get("skills", [])
        ],
        "diplomas": [
            {
                "title": item.get("title") or "",
                "level": item.get("level") or "",
                "institution": item.get("institution") or "",
                "speciality": item.get("speciality") or "",
                "graduation_year": item.get("graduation_year") or "",
                "description": item.get("description") or "",
                "source": item.get("source") or "manual",
            }
            for item in profile.get("diplomas", [])
        ],
        "experiences": [
            {
                "job_title": item.get("job_title") or "",
                "company": item.get("company") or "",
                "city": item.get("city") or "",
                "start_date": item.get("start_date") or "",
                "end_date": item.get("end_date") or "",
                "is_current": int(item.get("is_current") or 0),
                "description": item.get("description") or "",
                "source": item.get("source") or "manual",
                "skills_text": ", ".join(item.get("skills", [])),
            }
            for item in profile.get("experiences", [])
        ],
        "cv": profile.get("cv"),
    }


def _persist_match_to_db(conn: sqlite3.Connection, user_id: int, match: Dict[str, Any]) -> None:
    """Persiste un matching dans la table job_matches.

    Args:
        conn: Connexion SQLite.
        user_id: Identifiant utilisateur.
        match: Résultat de matching.
    """
    now = _utcnow_iso()
    offer_identifier = str(match.get("offer_identifier") or "")
    if not offer_identifier:
        return
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
            json.dumps(match.get("explanation", {}), ensure_ascii=False),
            now,
        ),
    )


def compute_all_matches() -> Dict[str, Any]:
    """Calcule les matchings pour tous les utilisateurs.

    Lit les profils depuis SQLite, calcule les matchings contre les offres
    enrichies, et écrit les résultats dans matches.json et job_matches.

    Returns:
        Statistiques du calcul.
    """
    stats = {
        "total_users": 0,
        "users_processed": 0,
        "users_from_cache": 0,
        "matches_computed": 0,
        "errors": 0,
    }

    if not ENRICHED_OFFERS_PATH.exists():
        logger.warning("Fichier introuvable: %s", ENRICHED_OFFERS_PATH)
        return stats

    try:
        with ENRICHED_OFFERS_PATH.open("r", encoding="utf-8") as f:
            raw_offers = json.load(f)

        offers_hash = compute_hash(raw_offers)
        normalized_offers = [
            normalize_offer_for_matching(
                offer, source=offer.get("source") or "France Travail"
            )
            for offer in raw_offers
            if isinstance(offer, dict)
        ]

        conn = _open_db()
        try:
            user_ids = _get_user_ids(conn)
            stats["total_users"] = len(user_ids)

            all_matches: Dict[str, List[Dict[str, Any]]] = {}

            for user_id in user_ids:
                try:
                    raw_profile = _assemble_profile_from_db(conn, user_id)
                    profile = _profile_snapshot(raw_profile)
                    profile_hash = compute_hash(profile)

                    cache_key = f"matches:v{MATCHES_CACHE_VERSION}:user:{user_id}"
                    cached = cache_store.get(cache_key)
                    combined_hash = compute_hash(
                        {"offers": offers_hash, "profile": profile_hash, "version": MATCHES_CACHE_VERSION}
                    )

                    if (
                        cached
                        and cached.get("input_hash") == combined_hash
                    ):
                        cached_matches = cached.get("value") or []
                        all_matches[str(user_id)] = cached_matches
                        stats["users_processed"] += 1
                        stats["users_from_cache"] += 1
                        stats["matches_computed"] += len(cached_matches)
                        continue

                    user_matches = []
                    for offer in normalized_offers:
                        try:
                            result = compute_match(profile, offer)
                            offer_id = str(
                                offer.get("id")
                                or offer.get("id_offre")
                                or offer.get("offer_identifier")
                                or ""
                            )
                            result["offer_identifier"] = offer_id
                            user_matches.append(
                                {
                                    "offer_id": offer_id,
                                    "score": result.get("global_score", 0),
                                    "matching_skills": result.get(
                                        "matching_skills", []
                                    ),
                                    "missing_skills": result.get(
                                        "missing_skills", []
                                    ),
                                    "details": result,
                                }
                            )
                            _persist_match_to_db(conn, user_id, result)
                            stats["matches_computed"] += 1
                        except Exception as e:
                            offer_id = offer.get("id") or "?"
                            logger.error(
                                "Erreur matching offre %s pour user %s: %s",
                                offer_id,
                                user_id,
                                e,
                            )
                            task_status.add_error(
                                "compute_matches",
                                str(offer_id),
                                "matching",
                                str(e),
                            )
                            stats["errors"] += 1

                    conn.commit()

                    user_matches.sort(
                        key=lambda x: x["score"], reverse=True
                    )
                    all_matches[str(user_id)] = user_matches
                    stats["users_processed"] += 1

                    cache_store.set(
                        cache_key,
                        user_matches,
                        input_hash=combined_hash,
                        source_version=MATCHES_CACHE_VERSION,
                    )

                except Exception as e:
                    logger.error(
                        "Erreur calcul matchings user %s: %s", user_id, e
                    )
                    task_status.add_error(
                        "compute_matches", str(user_id), "matching", str(e)
                    )
                    stats["errors"] += 1

            MATCHES_PATH.parent.mkdir(parents=True, exist_ok=True)
            with MATCHES_PATH.open("w", encoding="utf-8") as f:
                json.dump(all_matches, f, ensure_ascii=False, indent=2)

            logger.info(
                "Matchings calculés: %s utilisateurs (%s depuis cache), %s matchings",
                stats["users_processed"],
                stats["users_from_cache"],
                stats["matches_computed"],
            )

        finally:
            conn.close()

    except Exception as e:
        logger.error("Erreur calcul matchings: %s", e)
        stats["errors"] += 1
        raise

    return stats
