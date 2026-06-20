# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Centralized offer loading and territory trend helpers for the Flask app."""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src.offer_normalization import normalize_france_travail_offer, normalize_text
from src.trend_aggregation import aggregate_trends


logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW_OFFERS_PATH = PROJECT_ROOT / "data" / "raw" / "offres_france_travail.json"


def load_normalized_offers(path: Path = DEFAULT_RAW_OFFERS_PATH) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Load and normalize the stored France Travail offers."""

    try:
        if not path.exists():
            message = f"Aucun fichier d'offres n'a été trouvé: {path}"
            logger.error(message)
            return [], message
        with path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        if not isinstance(payload, list):
            message = "Le fichier d'offres doit contenir une liste JSON."
            logger.error(message)
            return [], message
        offers = [normalize_france_travail_offer(offer) for offer in payload if isinstance(offer, dict)]
        return offers, None
    except json.JSONDecodeError:
        message = "Le fichier d'offres est invalide."
        logger.exception("Impossible de décoder le fichier d'offres %s", path)
        return [], message
    except OSError:
        message = "Impossible de lire le fichier d'offres."
        logger.exception("Impossible de lire le fichier d'offres %s", path)
        return [], message
    except Exception:
        message = "Une erreur inattendue est survenue lors du chargement des offres."
        logger.exception("Erreur inattendue lors du chargement de %s", path)
        return [], message


def _parse_offer_date(value: object) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
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


def get_available_territories(offers: Iterable[Dict[str, Any]]) -> List[str]:
    """Return the distinct territory labels found in the available offers."""

    territories = {
        str(offer.get("territoire") or "").strip()
        for offer in offers
        if isinstance(offer, dict) and str(offer.get("territoire") or "").strip()
    }
    return sorted(territories, key=lambda value: normalize_text(value))


def _territory_label(territory: Optional[str]) -> str:
    if not territory:
        return "Tous les territoires"
    return territory


def _period_label(offers: Iterable[Dict[str, Any]]) -> Optional[str]:
    dates = [
        parsed
        for parsed in (_parse_offer_date(offer.get("date")) for offer in offers)
        if parsed is not None
    ]
    if not dates:
        return None
    start = min(dates).isoformat()
    end = max(dates).isoformat()
    return f"{start} au {end}"


def _top_skill_rows(
    offers: List[Dict[str, Any]],
    territory: Optional[str],
    limit: int,
) -> Tuple[List[Dict[str, Any]], int, List[Dict[str, Any]]]:
    selected_territory = None if not territory or territory == "Tous les territoires" else territory
    trends = aggregate_trends(offers, territoire=selected_territory, periode_jours=36500)
    total_offers = int(trends.get("nombre_offres") or 0)
    ranked: List[Dict[str, Any]] = []
    items = list(trends.get("competences", {}).items())[: max(limit, 1)]
    for index, (skill, count) in enumerate(items, start=1):
        if not skill:
            continue
        percentage = round((count / total_offers) * 100.0, 1) if total_offers else 0.0
        ranked.append({"rank": index, "skill": skill, "count": count, "percentage": percentage})
    filtered_offers = list(trends.get("offres") or trends.get("offers") or [])
    return ranked[: max(limit, 1)], total_offers, filtered_offers


def get_top_skills_by_territory(
    offers: List[Dict[str, Any]],
    territory: Optional[str],
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Return the top skills for a territory as rank/count/percentage rows."""

    rows, _, _ = _top_skill_rows(offers, territory, limit)
    return rows


def build_territory_trends_context(
    offers: List[Dict[str, Any]],
    territory: Optional[str],
    limit: int = 10,
) -> Dict[str, Any]:
    """Build the data structure required by the territory trends page."""

    rows, total_offers, filtered_offers = _top_skill_rows(offers, territory, limit)
    period_label = _period_label(filtered_offers)
    selected_territory = None if not territory or territory == "Tous les territoires" else territory
    return {
        "selected_territory": _territory_label(selected_territory),
        "territory_value": selected_territory or "",
        "total_offers": total_offers,
        "period_label": period_label,
        "top_skills": rows,
        "has_data": bool(rows),
    }
