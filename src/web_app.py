# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Web dashboard for France Travail offers and market trends."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from flask import Flask, flash, jsonify, render_template, request, session

from src.france_travail_client import iter_search_offres
from src.offer_normalization import normalize_france_travail_offer
from src.matching.weights import DEFAULT_MATCHING_WEIGHTS, MATCHING_WEIGHT_KEYS, validate_matching_weights
from src.services.matching_service import compute_match
from src.services.offer_repository import (
    build_territory_trends_context,
    get_available_territories,
    load_normalized_offers,
)
from src.trend_aggregation import aggregate_trends
from src.user_portal import _current_profile_snapshot, _current_user_id, register_user_portal
from src.skill_extraction import extract_skills_from_offer
from src.cache_reader import (
    get_precomputed_offers,
    get_precomputed_trends,
    get_territory_options as get_cached_territory_options,
    get_last_refresh_time,
    is_refresh_running,
    get_cache_status,
    has_precomputed_data,
)
from src.performance import timed_route, RouteTimer, _PERF_DEBUG


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_OFFERS_PATH = PROJECT_ROOT / "data" / "raw" / "offres_france_travail.json"
PROCESSED_CONTEXT_PATH = PROJECT_ROOT / "data" / "processed" / "metier_context_t3_2025.csv"
DEFAULT_PERIOD = 30
DEFAULT_TOP_N = 10
DEFAULT_PER_PAGE = 20
DEFAULT_PORT = 8000
DEFAULT_HOST = "127.0.0.1"
TERRITOIRE_TYPE_OPTIONS = (
    ("all", "Tous les territoires"),
    ("commune", "Commune"),
    ("departement", "Département"),
    ("region", "Région"),
)


def _normalize_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().lower()


def _parse_date(value: object) -> Optional[date]:
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


def _extract_territory(raw_offer: Dict[str, Any]) -> str:
    lieu = raw_offer.get("lieuTravail")
    if isinstance(lieu, dict):
        territory = lieu.get("libelle") or lieu.get("commune") or lieu.get("codePostal")
        if territory:
            return str(territory)
    for key in ("territoire", "ville", "lieu", "location", "city"):
        value = raw_offer.get(key)
        if value:
            return str(value)
    return str(raw_offer.get("intitule") or "")


def _extract_metier(raw_offer: Dict[str, Any]) -> str:
    return str(
        raw_offer.get("romeLibelle")
        or raw_offer.get("appellationlibelle")
        or raw_offer.get("intitule")
        or ""
    )


def _extract_contrat(raw_offer: Dict[str, Any]) -> str:
    return str(raw_offer.get("typeContratLibelle") or raw_offer.get("typeContrat") or "")


def _extract_niveau(raw_offer: Dict[str, Any]) -> str:
    experience = _normalize_text(raw_offer.get("experienceLibelle") or raw_offer.get("experienceExige"))
    if any(token in experience for token in ("senior", "expert", "lead", "5 ans", "6 ans", "7 ans", "8 ans")):
        return "senior"
    if any(token in experience for token in ("junior", "debutant", "0 an", "1 an", "2 ans", "sans experience")):
        return "junior"
    if experience:
        return "intermediaire"
    return ""


def _extract_competences(raw_offer: Dict[str, Any]) -> List[str]:
    competences: List[str] = []
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


def normalize_offer(raw_offer: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id_offre": str(raw_offer.get("id") or raw_offer.get("id_offre") or ""),
        "date": _format_date(raw_offer.get("dateActualisation") or raw_offer.get("dateCreation") or raw_offer.get("date")),
        "territoire": _extract_territory(raw_offer),
        "metier": _extract_metier(raw_offer),
        "niveau": _extract_niveau(raw_offer),
        "contrat": _extract_contrat(raw_offer),
        "competences": _extract_competences(raw_offer),
        "entreprise": str((raw_offer.get("entreprise") or {}).get("nom") if isinstance(raw_offer.get("entreprise"), dict) else raw_offer.get("entreprise") or ""),
        "description": str(raw_offer.get("description") or ""),
        "intitule": str(raw_offer.get("intitule") or ""),
    }


def load_raw_offers(path: Path = RAW_OFFERS_PATH) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Fichier d'offres introuvable: {path}")
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, list):
        raise ValueError("Le fichier d'offres brut doit contenir une liste JSON.")
    return [offer for offer in payload if isinstance(offer, dict)]


def _offer_matches_territory(offer: Dict[str, Any], territoire: Optional[str]) -> bool:
    if not territoire:
        return True
    target = _normalize_text(territoire)
    if not target:
        return False
    parts: List[str] = []
    for key in ("territoire", "ville", "lieu", "location", "city", "code_postal"):
        value = offer.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value if item not in (None, ""))
        elif value not in (None, ""):
            parts.append(str(value))
    lieu_travail = offer.get("lieuTravail")
    if isinstance(lieu_travail, dict):
        for key in ("libelle", "commune", "codePostal"):
            value = lieu_travail.get(key)
            if value:
                parts.append(str(value))
    offer_territory = _normalize_text(" ".join(parts))
    return bool(offer_territory) and (target in offer_territory or offer_territory in target)


def _offer_in_period(offer: Dict[str, Any], cutoff: date) -> bool:
    parsed = _parse_date(offer.get("date"))
    if parsed is None:
        return True
    return parsed >= cutoff


def filter_offers(offers: List[Dict[str, Any]], territoire: Optional[str], periode_jours: int) -> List[Dict[str, Any]]:
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


def load_market_context_rows(path: Path = PROCESSED_CONTEXT_PATH) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = [row for row in reader if row.get("domaine")]
    return rows[:12]


def _format_percentage(count: int, total: int) -> str:
    if total <= 0:
        return "0,0 %"
    return f"{(count / total) * 100:.1f}".replace('.', ',') + " %"


def build_ranking_entries(data: Optional[Dict[str, Any]], total_offers: int, limit: int) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
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
            "nom": str(label),
            "count": count,
            "pourcentage": _format_percentage(count, total_offers),
        })
    entries.sort(key=lambda item: (-item["count"], _normalize_text(item["nom"])) )
    return entries[:max(limit, 1)]


def _territory_type_label(territoire_type: str) -> str:
    mapping = {key: label for key, label in TERRITOIRE_TYPE_OPTIONS}
    return mapping.get(territoire_type, "Tous les territoires")


def _sanitize_page(value: object, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(parsed, 1)


def _sanitize_per_page(value: object, default: int = DEFAULT_PER_PAGE) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed, 1), 50)


def _sanitize_period(value: object) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_PERIOD
    return max(parsed, 1)


def _sanitize_top_n(value: object) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_TOP_N
    return max(parsed, 1)


def _sanitize_territory_type(value: Optional[str]) -> str:
    candidate = (value or "all").strip().lower()
    if candidate in {item[0] for item in TERRITOIRE_TYPE_OPTIONS}:
        return candidate
    return "all"


def _matching_weight_input_name(key: str) -> str:
    return "matching_weights_%s" % key


def _extract_matching_weights_from_request() -> Tuple[Dict[str, float], Optional[str]]:
    provided = any(_matching_weight_input_name(key) in request.args for key in MATCHING_WEIGHT_KEYS)
    if not provided:
        stored = session.get("matching_weights")
        normalized, error = validate_matching_weights(stored) if isinstance(stored, dict) else (dict(DEFAULT_MATCHING_WEIGHTS), "")
        if error:
            return dict(DEFAULT_MATCHING_WEIGHTS), ""
        return normalized, ""

    candidate = {key: request.args.get(_matching_weight_input_name(key)) for key in MATCHING_WEIGHT_KEYS}
    normalized, error = validate_matching_weights(candidate)
    if error:
        stored = session.get("matching_weights")
        if isinstance(stored, dict):
            fallback, fallback_error = validate_matching_weights(stored)
            if not fallback_error:
                return fallback, error
        return dict(DEFAULT_MATCHING_WEIGHTS), error

    session["matching_weights"] = normalized
    return normalized, ""


def _matching_weight_query_params(weights: Dict[str, float]) -> Dict[str, float]:
    return {_matching_weight_input_name(key): float(weights.get(key, DEFAULT_MATCHING_WEIGHTS[key])) for key in MATCHING_WEIGHT_KEYS}


def _build_search_arguments(territoire_type: str, territoire: str, distance: object) -> Tuple[Dict[str, Any], Optional[str], str]:
    search_kwargs: Dict[str, Any] = {}
    territory_label = None
    territoire = territoire.strip()
    if territoire_type == "commune":
        search_kwargs["commune"] = territoire or None
        if distance not in (None, ""):
            try:
                parsed_distance = int(distance)
                if parsed_distance > 0:
                    search_kwargs["distance"] = parsed_distance
            except (TypeError, ValueError):
                pass
        territory_label = f"la commune {territoire}" if territoire else "la commune sélectionnée"
    elif territoire_type == "departement":
        search_kwargs["departement"] = territoire or None
        territory_label = f"le département {territoire}" if territoire else "le département sélectionné"
    elif territoire_type == "region":
        search_kwargs["region"] = territoire or None
        territory_label = f"la région {territoire}" if territoire else "la région sélectionnée"
    else:
        territory_label = "tous les territoires"
    return search_kwargs, territory_label, territoire




def build_live_state(
    mots_cles: str,
    territoire_type: str,
    territoire: str,
    distance: object,
    page: int,
    per_page: int,
    periode_jours: int,
    top_n: int,
    matching_weights: Dict[str, float],
) -> Dict[str, Any]:
    errors: List[str] = []
    search_filters, territoire_label, normalized_territoire = _build_search_arguments(territoire_type, territoire, distance)
    territory_offers, territory_error = load_normalized_offers()
    territory_options = get_available_territories(territory_offers)
    if territory_error:
        errors.append(territory_error)

    if not mots_cles.strip():
        return {
            "mots_cles": mots_cles,
            "territoire_type": territoire_type,
            "territoire": normalized_territoire,
            "distance": str(distance or ""),
            "page": page,
            "per_page": per_page,
            "periode_jours": periode_jours,
            "top_n": top_n,
            "territoire_label": territoire_label,
            "error_message": " ".join(errors) if errors else "Veuillez saisir des mots-clés pour lancer la recherche.",
            "nombre_offres": 0,
            "offres": [],
            "offers": [],
            "paged_offers": [],
            "total_pages": 0,
            "page": page,
            "page_size": per_page,
            "top_metiers": [],
            "top_competences": [],
            "trends": {"territoire": normalized_territoire or None, "periode_jours": periode_jours, "nombre_offres": 0, "competences": {}, "metiers": {}, "niveau": {}, "contrats": {}, "offres": [], "offers": []},
            "market_context": load_market_context_rows(),
            "market_context_headers": [],
            "territoire_options": territory_options,
            "trend_competence_items": [],
            "trend_contract_items": [],
            "trend_niveau_items": [],
            "matching_weights": dict(matching_weights),
            "default_matching_weights": dict(DEFAULT_MATCHING_WEIGHTS),
            "matching_weights_error": "",
        }

    if territoire_type != "all" and not normalized_territoire:
        errors.append("Le territoire est requis pour ce type de filtre.")

    if territoire_type == "commune" and distance not in (None, ""):
        try:
            parsed_distance = int(distance)
            if parsed_distance <= 0:
                errors.append("La distance doit être un entier positif.")
            else:
                search_filters["distance"] = parsed_distance
        except (TypeError, ValueError):
            errors.append("La distance fournie est invalide.")

    try:
        raw_offers = iter_search_offres(mots_cles, **search_filters)
    except RuntimeError as exc:
        return {
            "mots_cles": mots_cles,
            "territoire_type": territoire_type,
            "territoire": normalized_territoire,
            "distance": str(distance or ""),
            "page": page,
            "per_page": per_page,
            "periode_jours": periode_jours,
            "top_n": top_n,
            "territoire_label": territoire_label,
            "error_message": str(exc),
            "nombre_offres": 0,
            "offres": [],
            "offers": [],
            "paged_offers": [],
            "total_pages": 0,
            "page": page,
            "page_size": per_page,
            "top_metiers": [],
            "top_competences": [],
            "trends": {"territoire": normalized_territoire or None, "periode_jours": periode_jours, "nombre_offres": 0, "competences": {}, "metiers": {}, "niveau": {}, "contrats": {}, "offres": [], "offers": []},
            "market_context": load_market_context_rows(),
            "market_context_headers": [],
            "territoire_options": territory_options,
            "trend_competence_items": [],
            "trend_contract_items": [],
            "trend_niveau_items": [],
            "matching_weights": dict(matching_weights),
            "default_matching_weights": dict(DEFAULT_MATCHING_WEIGHTS),
            "matching_weights_error": "",
        }

    normalized_offers = [normalize_france_travail_offer(offer) for offer in raw_offers]
    trends = aggregate_trends(normalized_offers, territoire=normalized_territoire or None, periode_jours=periode_jours)
    normalized_by_id = {
        offer.get("id"): offer
        for offer in normalized_offers
        if offer.get("id")
    }
    current_profile = None
    try:
        user_id = _current_user_id()
        if user_id:
            current_profile = _current_profile_snapshot(user_id)
    except Exception:
        current_profile = None

    enriched_offers: List[Dict[str, Any]] = []
    for offer in trends.get("offres", []):
        enriched = dict(offer)
        source_offer = normalized_by_id.get(str(offer.get("id") or offer.get("id_offre") or ""))
        if source_offer:
            structured_competences = source_offer.get("competences", [])
            description = source_offer.get("description", "")
            
            extracted_skills = extract_skills_from_offer(
                description,
                structured_competences=structured_competences,
            )
            all_competences = list(dict.fromkeys(skill.canonical_name for skill in extracted_skills))
            
            enriched["competences"] = all_competences
            enriched["competences_explicites"] = [s.canonical_name for s in extracted_skills if s.extraction_type == "explicit"]
            enriched["competences_semantiques"] = [s.canonical_name for s in extracted_skills if s.extraction_type == "semantic"]
            enriched["competences_implicites"] = [s.canonical_name for s in extracted_skills if s.extraction_type == "implicit"]
            enriched["ville"] = source_offer.get("ville", "")
            enriched["code_postal"] = source_offer.get("code_postal", "")
        if current_profile and source_offer:
            try:
                match = compute_match(current_profile, source_offer, weights=matching_weights)
                enriched["match_score"] = round(float(match.get("global_score") or 0.0), 2)
                enriched["matching_skills"] = match.get("matching_skills", [])
                enriched["missing_skills"] = match.get("missing_skills", [])
                enriched["match_details"] = match
                enriched["match_explanation"] = match.get("explanation", {})
            except Exception:
                enriched["match_score"] = None
                enriched["matching_skills"] = []
                enriched["missing_skills"] = []
                enriched["match_explanation"] = {}
        enriched_offers.append(enriched)

    enriched_offers.sort(
        key=lambda item: (
            -float(item.get("match_score") if item.get("match_score") is not None else item.get("global_score") or 0),
            item.get("intitule") or item.get("titre") or "",
        )
    )

    total_offers = len(enriched_offers)
    total_pages = max((total_offers + per_page - 1) // per_page, 1) if total_offers else 0
    current_page = min(page, total_pages) if total_pages else 1
    start_index = (current_page - 1) * per_page
    end_index = start_index + per_page
    paged_offers = enriched_offers[start_index:end_index] if total_offers else []

    ranking_source = trends
    total_for_rankings = total_offers
    top_limit = max(top_n, 1)
    trend_competence_items = list(trends.get("competences", {}).items())[:top_limit]
    trend_contract_items = list(trends.get("contrats", {}).items())[:top_limit]
    trend_niveau_items = list(trends.get("niveau", {}).items())[:top_limit]
    market_context = load_market_context_rows()
    market_context_headers = list(market_context[0].keys())[:4] if market_context else []
    return {
        "mots_cles": mots_cles,
        "territoire_type": territoire_type,
        "territoire": normalized_territoire,
        "distance": str(distance or ""),
        "page": current_page,
        "per_page": per_page,
        "periode_jours": periode_jours,
        "top_n": top_n,
        "territoire_label": territoire_label,
        "error_message": " ".join(errors),
        "nombre_offres": total_offers,
        "offres": trends.get("offres", []),
        "offers": trends.get("offres", []),
        "paged_offers": enriched_offers,
        "total_pages": total_pages,
        "page_size": per_page,
        "top_metiers": build_ranking_entries(ranking_source.get("metiers"), total_for_rankings, top_limit),
        "top_competences": build_ranking_entries(ranking_source.get("competences"), total_for_rankings, top_limit),
        "trends": trends,
        "trend_competence_items": trend_competence_items,
        "trend_contract_items": trend_contract_items,
        "trend_niveau_items": trend_niveau_items,
        "market_context": market_context,
        "market_context_headers": market_context_headers,
        "territoire_options": territory_options,
        "matching_weights": dict(matching_weights),
        "default_matching_weights": dict(DEFAULT_MATCHING_WEIGHTS),
        "matching_weights_error": "",
    }


def build_cached_state(
    mots_cles: str,
    territoire_type: str,
    territoire: str,
    distance: object,
    page: int,
    per_page: int,
    periode_jours: int,
    top_n: int,
    matching_weights: Dict[str, float],
) -> Dict[str, Any]:
    """Construit l'état depuis les caches précalculés.

    Cette fonction lit les données précalculées par src.jobs.refresh_all
    au lieu de recalculer à chaque requête. Elle ne fait que filtrer,
    trier et paginer les résultats.

    Args:
        mots_cles: Mots-clés de recherche.
        territoire_type: Type de territoire (commune, departement, region, all).
        territoire: Valeur du territoire.
        distance: Distance pour la recherche par commune.
        page: Numéro de page.
        per_page: Nombre d'offres par page.
        periode_jours: Période en jours.
        top_n: Nombre de top éléments.
        matching_weights: Pondérations du matching.

    Returns:
        Dictionnaire de contexte pour le rendu.
    """
    errors: List[str] = []
    search_filters, territoire_label, normalized_territoire = _build_search_arguments(territoire_type, territoire, distance)

    offers, offers_error = get_precomputed_offers()
    territory_options = get_cached_territory_options()

    if offers_error:
        errors.append(offers_error)

    cache_status = get_cache_status()

    if not mots_cles.strip():
        return {
            "mots_cles": mots_cles,
            "territoire_type": territoire_type,
            "territoire": normalized_territoire,
            "distance": str(distance or ""),
            "page": page,
            "per_page": per_page,
            "periode_jours": periode_jours,
            "top_n": top_n,
            "territoire_label": territoire_label,
            "error_message": " ".join(errors) if errors else "Veuillez saisir des mots-clés pour lancer la recherche.",
            "nombre_offres": 0,
            "offres": [],
            "offers": [],
            "paged_offers": [],
            "total_pages": 0,
            "page": page,
            "page_size": per_page,
            "top_metiers": [],
            "top_competences": [],
            "trends": {"territoire": normalized_territoire or None, "periode_jours": periode_jours, "nombre_offres": 0, "competences": {}, "metiers": {}, "niveau": {}, "contrats": {}, "offres": [], "offers": []},
            "market_context": load_market_context_rows(),
            "market_context_headers": [],
            "territoire_options": territory_options,
            "trend_competence_items": [],
            "trend_contract_items": [],
            "trend_niveau_items": [],
            "matching_weights": dict(matching_weights),
            "default_matching_weights": dict(DEFAULT_MATCHING_WEIGHTS),
            "matching_weights_error": "",
            "cache_status": cache_status,
        }

    if territoire_type != "all" and not normalized_territoire:
        errors.append("Le territoire est requis pour ce type de filtre.")

    filtered_offers = []
    for offer in offers:
        if not _offer_matches_territory(offer, normalized_territoire if territoire_type != "all" else None):
            continue
        if mots_cles.strip():
            searchable = " ".join([
                str(offer.get("intitule") or offer.get("titre") or ""),
                str(offer.get("description") or ""),
                str(offer.get("metier") or ""),
                " ".join(str(s) for s in (offer.get("competences") or [])),
            ]).lower()
            if mots_cles.lower() not in searchable:
                continue
        filtered_offers.append(offer)

    filtered_offers.sort(key=lambda item: item.get("date") or "", reverse=True)

    trends, _ = get_precomputed_trends(territoire=normalized_territoire or None, periode_jours=periode_jours)
    total_offers = len(filtered_offers)
    total_pages = max((total_offers + per_page - 1) // per_page, 1) if total_offers else 0
    current_page = min(page, total_pages) if total_pages else 1
    start_index = (current_page - 1) * per_page
    end_index = start_index + per_page
    paged_offers = filtered_offers[start_index:end_index] if total_offers else []

    top_limit = max(top_n, 1)
    trend_competence_items = list((trends or {}).get("competences", {}).items())[:top_limit]
    trend_contract_items = list((trends or {}).get("contrats", {}).items())[:top_limit]
    trend_niveau_items = list((trends or {}).get("niveau", {}).items())[:top_limit]
    market_context = load_market_context_rows()
    market_context_headers = list(market_context[0].keys())[:4] if market_context else []

    return {
        "mots_cles": mots_cles,
        "territoire_type": territoire_type,
        "territoire": normalized_territoire,
        "distance": str(distance or ""),
        "page": current_page,
        "per_page": per_page,
        "periode_jours": periode_jours,
        "top_n": top_n,
        "territoire_label": territoire_label,
        "error_message": " ".join(errors),
        "nombre_offres": total_offers,
        "offres": filtered_offers[:50],
        "offers": filtered_offers[:50],
        "paged_offers": paged_offers,
        "total_pages": total_pages,
        "page_size": per_page,
        "top_metiers": build_ranking_entries((trends or {}).get("metiers"), total_offers, top_limit),
        "top_competences": build_ranking_entries((trends or {}).get("competences"), total_offers, top_limit),
        "trends": trends or {},
        "trend_competence_items": trend_competence_items,
        "trend_contract_items": trend_contract_items,
        "trend_niveau_items": trend_niveau_items,
        "market_context": market_context,
        "market_context_headers": market_context_headers,
        "territoire_options": territory_options,
        "matching_weights": dict(matching_weights),
        "default_matching_weights": dict(DEFAULT_MATCHING_WEIGHTS),
        "matching_weights_error": "",
        "cache_status": cache_status,
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
      --danger: #bb3e3e;
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
      grid-template-columns: 1.2fr 0.8fr 0.8fr 0.5fr 0.35fr auto;
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
    .field input, .field select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 11px 12px;
      font: inherit;
      background: white;
      color: var(--text);
    }
    .field small { color: var(--muted); display: block; margin-top: 4px; }
    .field.compact { min-width: 0; }
    button, .button {
      border: 0;
      background: var(--accent);
      color: white;
      border-radius: 8px;
      padding: 11px 16px;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
    }
    button:hover, .button:hover { filter: brightness(1.02); }
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
    .grid { display: grid; grid-template-columns: 1fr 1.15fr; gap: 16px; align-items: start; }
    .panel { padding: 16px; }
    .panel h2 { margin: 0 0 12px; font-size: 18px; }
    .subhead { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 10px; }
    .subhead small { color: var(--muted); }
    .trend-grid { display: grid; grid-template-columns: 1fr; gap: 12px; margin: 12px 0 10px; }
    .detail-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin: 12px 0 10px; }
    .trend-panel {
      background: var(--surface-alt);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
    }
    .trend-panel h3 { margin: 0; font-size: 15px; }
    .trend-list { display: grid; gap: 10px; }
    .trend-row { display: grid; gap: 6px; }
    .trend-head { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 12px; align-items: baseline; }
    .trend-label { font-size: 14px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .trend-stats { color: var(--muted); font-size: 13px; font-variant-numeric: tabular-nums; white-space: nowrap; }
    .trend-track { height: 10px; border-radius: 999px; background: #e8eef5; overflow: hidden; }
    .trend-fill { height: 100%; border-radius: inherit; background: linear-gradient(90deg, var(--accent), var(--accent-2)); }
    .trend-empty, .empty { color: var(--muted); padding: 10px 0; }
    .rankings-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin: 12px 0 10px; }
    .ranking-panel { background: var(--surface-alt); border: 1px solid var(--line); border-radius: 8px; padding: 12px; }
    .ranking-panel h3 { margin: 0; font-size: 15px; }
    .ranking-table { width: 100%; border-collapse: collapse; font-size: 13px; }
    .ranking-table th, .ranking-table td { padding: 8px 0; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
    .ranking-table th { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.02em; }
    .ranking-value { text-align: right; font-variant-numeric: tabular-nums; }
    .offer-grid { display: grid; gap: 12px; }
    .offer-card {
      border: 1px solid var(--line);
      border-radius: 10px;
      background: white;
      padding: 14px;
      box-shadow: 0 8px 22px rgba(19, 32, 51, 0.05);
    }
    .offer-title { margin: 0 0 4px; font-size: 16px; font-weight: 800; }
    .offer-company, .offer-meta, .offer-desc { color: var(--muted); font-size: 13px; }
    .offer-meta { display: flex; flex-wrap: wrap; gap: 10px; margin: 10px 0; }
    .chips { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 10px; }
    .chip { display: inline-flex; align-items: center; border: 1px solid var(--line); border-radius: 999px; padding: 4px 9px; background: #f7faff; color: var(--text); font-size: 12px; font-weight: 600; }
    .pagination { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 14px; flex-wrap: wrap; }
    .pagination .muted { color: var(--muted); }
    .status-message {
      border: 1px solid var(--line);
      border-left: 4px solid var(--accent);
      background: #f7fbff;
      border-radius: 8px;
      padding: 12px 14px;
      margin: 0 0 16px;
    }
    .status-message.error {
      border-left-color: var(--danger);
      background: #fff7f7;
      color: var(--danger);
    }
    .market-context-block { margin-top: 12px; }
    .market-table { width: 100%; border-collapse: collapse; font-size: 14px; }
    .market-table th, .market-table td { padding: 8px 6px; border-bottom: 1px solid var(--line); text-align: left; }
    .market-table th { color: var(--muted); text-transform: uppercase; font-size: 12px; }
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
    }
  </style>
</head>
<body>
  <header>
    <h1>TrendRadar IA</h1>
    <p>Recherche territoriale France Travail avec statistiques, tendances et liste des offres associées.</p>
    <nav class="topnav" style="display:flex;flex-wrap:wrap;gap:10px;margin-top:14px;">
      <a href="/profile" style="color:white;text-decoration:none;border:1px solid rgba(255,255,255,0.28);padding:8px 12px;border-radius:999px;font-weight:700;font-size:14px;">Mon profil</a>
      <a href="/profile/cv" style="color:white;text-decoration:none;border:1px solid rgba(255,255,255,0.28);padding:8px 12px;border-radius:999px;font-weight:700;font-size:14px;">Mon CV</a>
      <a href="/mes-offres" style="color:white;text-decoration:none;border:1px solid rgba(255,255,255,0.28);padding:8px 12px;border-radius:999px;font-weight:700;font-size:14px;">Mes offres</a>
      <a href="/dashboard-utilisateur" style="color:white;text-decoration:none;border:1px solid rgba(255,255,255,0.28);padding:8px 12px;border-radius:999px;font-weight:700;font-size:14px;">Mon tableau de bord</a>
      <a href="/logout" style="color:white;text-decoration:none;border:1px solid rgba(255,255,255,0.28);padding:8px 12px;border-radius:999px;font-weight:700;font-size:14px;">Déconnexion</a>
    </nav>
  </header>
  <main class="shell">
    <form class="filters" method="get" action="{{ url_for('index') }}">
      <div class="field">
        <label for="mots_cles">Mots-clés</label>
        <input id="mots_cles" name="mots_cles" value="{{ mots_cles }}" placeholder="python, data, ia...">
      </div>
      <div class="field compact">
        <label for="territoire_type">Type de territoire</label>
        <select id="territoire_type" name="territoire_type">
          {% for value, label in territoire_type_options %}
          <option value="{{ value }}" {% if value == territoire_type %}selected{% endif %}>{{ label }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="field compact">
        <label for="territoire">Territoire</label>
        <input id="territoire" name="territoire" list="territoire-list" value="{{ territoire }}" placeholder="69, 69123, Auvergne-Rhône-Alpes...">
        <datalist id="territoire-list">
          {% for option in territoire_options %}
          <option value="{{ option }}"></option>
          {% endfor %}
        </datalist>
        <small>Codes INSEE pour commune, département ou région selon le filtre choisi.</small>
      </div>
      <div class="field compact">
        <label for="distance">Distance (km)</label>
        <input id="distance" name="distance" type="number" min="1" step="1" value="{{ distance }}" placeholder="20">
      </div>
      <div class="field compact">
        <label for="per_page">Par page</label>
        <input id="per_page" name="per_page" type="number" min="1" max="50" step="1" value="{{ per_page }}">
      </div>
      <div class="field compact">
        <label>&nbsp;</label>
        <button type="submit">Rechercher</button>
      </div>
      <input type="hidden" name="page" value="1">
      <input type="hidden" name="periode" value="{{ periode_jours }}">
      <input type="hidden" name="top_n" value="{{ top_n }}">
    </form>

    {% if error_message %}
    <div class="status-message error">{{ error_message }}</div>
    {% elif mots_cles and nombre_offres == 0 %}
    <div class="status-message">Aucune offre ne correspond à cette recherche.</div>
    {% elif mots_cles %}
    <div class="status-message">{{ nombre_offres }} offres trouvées pour {{ territoire_label }}.</div>
    {% else %}
    <div class="status-message">Saisissez des mots-clés pour lancer une recherche France Travail.</div>
    {% endif %}

    <section class="summary">
      <div class="metric">
        <div class="label">Offres retenues</div>
        <div class="value">{{ nombre_offres }}</div>
        <div class="caption">sur {{ periode_jours }} jours</div>
      </div>
      <div class="metric">
        <div class="label">Compétences</div>
        <div class="value">{{ trends.competences|length if trends else 0 }}</div>
        <div class="caption">fréquences comptées</div>
      </div>
      <div class="metric">
        <div class="label">Métiers</div>
        <div class="value">{{ trends.metiers|length if trends else 0 }}</div>
        <div class="caption">fréquences comptées</div>
      </div>
      <div class="metric">
        <div class="label">Contrats</div>
        <div class="value">{{ trends.contrats|length if trends else 0 }}</div>
        <div class="caption">fréquences comptées</div>
      </div>
    </section>

    <section class="grid">
      <section class="panel">
        <div class="subhead">
          <h2>Tendances marché</h2>
          <small>{{ territoire_label }}</small>
        </div>
        <section class="trend-grid">
          <section class="trend-panel">
            <div class="subhead"><h3>Compétences</h3><small>Top {{ top_n }}</small></div>
            {% if trends.competences %}
            <div class="trend-list">
              {% for label, count in trend_competence_items %}
              <div class="trend-row">
                <div class="trend-head"><div class="trend-label">{{ label }}</div><div class="trend-stats">{{ count }} offres</div></div>
                <div class="trend-track"><div class="trend-fill" style="width:{{ 100 if loop.first else 70 }}%"></div></div>
              </div>
              {% endfor %}
            </div>
            {% else %}
            <div class="trend-empty">Aucune compétence disponible.</div>
            {% endif %}
          </section>
          <section class="trend-panel">
            <div class="subhead"><h3>Nature des contrats</h3><small>Top {{ top_n }}</small></div>
            {% if trends.contrats %}
            <div class="trend-list">
              {% for label, count in trend_contract_items %}
              <div class="trend-row">
                <div class="trend-head"><div class="trend-label">{{ label }}</div><div class="trend-stats">{{ count }} offres</div></div>
                <div class="trend-track"><div class="trend-fill" style="width:{{ 100 if loop.first else 70 }}%"></div></div>
              </div>
              {% endfor %}
            </div>
            {% else %}
            <div class="trend-empty">Aucun contrat disponible.</div>
            {% endif %}
          </section>
          <section class="trend-panel">
            <div class="subhead"><h3>Ancienneté demandée</h3><small>Top {{ top_n }}</small></div>
            {% if trends.niveau %}
            <div class="trend-list">
              {% for label, count in trend_niveau_items %}
              <div class="trend-row">
                <div class="trend-head"><div class="trend-label">{{ label }}</div><div class="trend-stats">{{ count }} offres</div></div>
                <div class="trend-track"><div class="trend-fill" style="width:{{ 100 if loop.first else 70 }}%"></div></div>
              </div>
              {% endfor %}
            </div>
            {% else %}
            <div class="trend-empty">Aucun niveau disponible.</div>
            {% endif %}
          </section>
        </section>
        <section class="rankings-grid">
          <section class="ranking-panel">
            <div class="subhead"><h3>Top intitulés de poste</h3><small>Top {{ top_n }}</small></div>
            <table class="ranking-table">
              <thead><tr><th>Nom</th><th class="ranking-value">Offres</th><th class="ranking-value">Part</th></tr></thead>
              <tbody>
                {% for item in top_metiers %}
                <tr><td>{{ item.nom }}</td><td class="ranking-value">{{ item.count }}</td><td class="ranking-value">{{ item.pourcentage }}</td></tr>
                {% endfor %}
                {% if not top_metiers %}
                <tr><td colspan="3" class="empty">Aucun intitulé de poste disponible.</td></tr>
                {% endif %}
              </tbody>
            </table>
          </section>
          <section class="ranking-panel">
            <div class="subhead"><h3>Top compétences</h3><small>Top {{ top_n }}</small></div>
            <table class="ranking-table">
              <thead><tr><th>Nom</th><th class="ranking-value">Offres</th><th class="ranking-value">Part</th></tr></thead>
              <tbody>
                {% for item in top_competences %}
                <tr><td>{{ item.nom }}</td><td class="ranking-value">{{ item.count }}</td><td class="ranking-value">{{ item.pourcentage }}</td></tr>
                {% endfor %}
                {% if not top_competences %}
                <tr><td colspan="3" class="empty">Aucune compétence disponible.</td></tr>
                {% endif %}
              </tbody>
            </table>
          </section>
        </section>
        <div class="market-context-block">
          <h2 style="margin-top: 0;">Contexte marché France Travail</h2>
          <table class="market-table">
            {% if market_context %}
            <thead>
              <tr>
                {% for header in market_context_headers %}
                <th>{{ header }}</th>
                {% endfor %}
              </tr>
            </thead>
            <tbody>
              {% for row in market_context %}
              <tr>
                {% for header in market_context_headers %}
                <td>{{ row[header] }}</td>
                {% endfor %}
              </tr>
              {% endfor %}
            </tbody>
            {% else %}
            <tbody><tr><td class="empty">Aucun contexte marché disponible.</td></tr></tbody>
            {% endif %}
          </table>
        </div>
      </section>

      <section class="panel">
        <div class="subhead">
          <h2>Offres associées</h2>
          <small>{{ paged_offers|length }} affichées sur {{ nombre_offres }}</small>
        </div>
        {% if paged_offers %}
        <div class="offer-grid">
          {% for offre in paged_offers %}
          <article class="offer-card">
            <h3 class="offer-title">{{ offre.intitule }}</h3>
            <div class="offer-company">{{ offre.entreprise or 'Entreprise non renseignée' }}</div>
            <div class="offer-meta">
              <span>{{ offre.territoire or offre.ville or 'Territoire non renseigné' }}</span>
              <span>{{ offre.contrat or 'Contrat non renseigné' }}</span>
              <span>{{ offre.date or 'Date non disponible' }}</span>
            </div>
            {% if offre.description %}
            <div class="offer-desc">{{ offre.description }}</div>
            {% endif %}
            <div class="chips">
              {% if offre.url %}
              <a href="{{ offre.url }}" target="_blank" rel="noopener noreferrer" class="button">Voir l'offre</a>
              {% else %}
              <span class="empty">Lien indisponible</span>
              {% endif %}
            </div>
          </article>
          {% endfor %}
        </div>
        <div class="pagination">
          <div class="muted">Page {{ page }} / {{ total_pages if total_pages else 1 }} · {{ per_page }} offres par page</div>
          <div>
            {% if page > 1 %}
            <a class="button" href="{{ prev_url }}">Précédent</a>
            {% endif %}
            {% if next_url %}
            <a class="button" href="{{ next_url }}">Suivant</a>
            {% endif %}
          </div>
        </div>
        {% else %}
        <div class="empty">Aucune offre ne correspond à cette recherche.</div>
        {% endif %}
      </section>
    </section>
  </main>
</body>
</html>
"""


def _build_query_string(params: Dict[str, Any]) -> str:
    from urllib.parse import urlencode

    filtered = {key: value for key, value in params.items() if value not in (None, "")}
    return urlencode(filtered)


def _build_page_url(**params: Any) -> str:
    return f"/?{_build_query_string(params)}"


def _build_render_context_from_request() -> Dict[str, Any]:
    mots_cles = (request.args.get("mots_cles") or "").strip()
    territoire_type = _sanitize_territory_type(request.args.get("territoire_type"))
    territoire = (request.args.get("territoire") or "").strip()
    distance = (request.args.get("distance") or "").strip()
    page = _sanitize_page(request.args.get("page"), 1)
    per_page = _sanitize_per_page(request.args.get("per_page"), DEFAULT_PER_PAGE)
    periode_jours = _sanitize_period(request.args.get("periode"))
    top_n = _sanitize_top_n(request.args.get("top_n"))

    matching_weights, matching_weights_error = _extract_matching_weights_from_request()

    if has_precomputed_data():
        state = build_cached_state(
            mots_cles=mots_cles,
            territoire_type=territoire_type,
            territoire=territoire,
            distance=distance,
            page=page,
            per_page=per_page,
            periode_jours=periode_jours,
            top_n=top_n,
            matching_weights=matching_weights,
        )
    else:
        state = build_live_state(
            mots_cles=mots_cles,
            territoire_type=territoire_type,
            territoire=territoire,
            distance=distance,
            page=page,
            per_page=per_page,
            periode_jours=periode_jours,
            top_n=top_n,
            matching_weights=matching_weights,
        )
    if matching_weights_error:
        existing_error = state.get("error_message") or ""
        state["error_message"] = (existing_error + " " + matching_weights_error).strip()
    state["matching_weights"] = dict(matching_weights)
    state["matching_weights_error"] = matching_weights_error or ""

    prev_url = None
    next_url = None
    if state["total_pages"] and state["page"] > 1:
        prev_url = _build_page_url(
            mots_cles=mots_cles,
            territoire_type=territoire_type,
            territoire=territoire,
            distance=distance,
            page=state["page"] - 1,
            per_page=per_page,
            periode=periode_jours,
            top_n=top_n,
            **_matching_weight_query_params(state["matching_weights"]),
        )
    if state["total_pages"] and state["page"] < state["total_pages"]:
        next_url = _build_page_url(
            mots_cles=mots_cles,
            territoire_type=territoire_type,
            territoire=territoire,
            distance=distance,
            page=state["page"] + 1,
            per_page=per_page,
            periode=periode_jours,
            top_n=top_n,
            **_matching_weight_query_params(state["matching_weights"]),
        )

    state.update(
        {
            "territoire_type_options": TERRITOIRE_TYPE_OPTIONS,
            "prev_url": prev_url,
            "next_url": next_url,
        }
    )
    return state


def _build_territory_trends_context_from_request() -> Dict[str, Any]:
    territory = (request.args.get("territoire") or "").strip()

    if has_precomputed_data():
        offers, error_message = get_precomputed_offers()
        territory_options = get_cached_territory_options()
        trends, trends_error = get_precomputed_trends(territoire=territory or None)
        total_offers = int(trends.get("nombre_offres") or 0) if trends else 0
        top_skills_raw = list((trends or {}).get("competences", {}).items())[:DEFAULT_TOP_N]
        top_skills = []
        for index, (skill, count) in enumerate(top_skills_raw, start=1):
            if not skill:
                continue
            percentage = round((count / total_offers) * 100.0, 1) if total_offers else 0.0
            top_skills.append({"rank": index, "skill": skill, "count": count, "percentage": percentage})
        context = {
            "selected_territory": territory or "Tous les territoires",
            "territory_value": territory or "",
            "total_offers": total_offers,
            "period_label": None,
            "top_skills": top_skills,
            "has_data": bool(top_skills),
            "page_title": "TrendRadar IA - Tendances par territoire",
            "territory_options": territory_options,
            "error_message": error_message or trends_error or "",
            "cache_status": get_cache_status(),
        }
    else:
        offers, error_message = load_normalized_offers()
        context = build_territory_trends_context(offers, territory or None, limit=DEFAULT_TOP_N)
        territory_options = get_available_territories(offers)
        context.update({
            "page_title": "TrendRadar IA - Tendances par territoire",
            "territory_options": territory_options,
            "error_message": error_message or "",
        })
    return context


def build_state(territoire: Optional[str], periode_jours: int, top_n: int = DEFAULT_TOP_N) -> Dict[str, Any]:
    if has_precomputed_data():
        normalized_offers, _error_message = get_precomputed_offers()
        offers = filter_offers(normalized_offers, territoire, periode_jours)
        trends, _ = get_precomputed_trends(territoire=territoire, periode_jours=periode_jours)
        market_context = load_market_context_rows()
        territoire_options = get_cached_territory_options()
        total_offers = int((trends or {}).get("nombre_offres") or len(offers))
        top_limit = max(top_n, 1)
        return {
            "territoire": territoire,
            "periode_jours": periode_jours,
            "top_n": top_limit,
            "nombre_offres_brutes": len(normalized_offers),
            "nombre_offres_filtrees": len(offers),
            "trends": trends or {},
            "ranking_source": trends or {},
            "top_metiers": build_ranking_entries((trends or {}).get("metiers"), total_offers, top_limit),
            "top_competences": build_ranking_entries((trends or {}).get("competences"), total_offers, top_limit),
            "offers": offers[:20],
            "territoire_options": territoire_options,
            "market_context": market_context,
            "cache_status": get_cache_status(),
        }
    else:
        normalized_offers, _error_message = load_normalized_offers()
        offers = filter_offers(normalized_offers, territoire, periode_jours)
        trends = aggregate_trends(offers, territoire=territoire, periode_jours=periode_jours)
        market_context = load_market_context_rows()
        territoire_options = get_available_territories(normalized_offers)
        total_offers = int(trends.get("nombre_offres") or len(offers))
        top_limit = max(top_n, 1)
        return {
            "territoire": territoire,
            "periode_jours": periode_jours,
            "top_n": top_limit,
            "nombre_offres_brutes": len(normalized_offers),
            "nombre_offres_filtrees": len(offers),
            "trends": trends,
            "ranking_source": trends,
            "top_metiers": build_ranking_entries(trends.get("metiers"), total_offers, top_limit),
            "top_competences": build_ranking_entries(trends.get("competences"), total_offers, top_limit),
            "offers": offers[:20],
            "territoire_options": territoire_options,
            "market_context": market_context,
        }


def create_app(config_overrides: Optional[Dict[str, Any]] = None) -> Flask:
    app = Flask(
        __name__,
        template_folder=str(PROJECT_ROOT / "templates"),
        static_folder=str(PROJECT_ROOT / "static"),
    )
    if config_overrides:
        app.config.update(config_overrides)
    app.config["SECRET_KEY"] = app.config.get("SECRET_KEY") or os.getenv("SECRET_KEY", "trendradar-dev-secret")
    app.secret_key = app.config["SECRET_KEY"]
    app.config.setdefault("MAX_CONTENT_LENGTH", 8 * 1024 * 1024)
    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")
    register_user_portal(app)

    @app.get("/")
    def index():
        context = _build_render_context_from_request()
        context["page_title"] = "TrendRadar IA - Recherche d'offres d'emploi"
        context["active_page"] = "search"
        context["body_class"] = "page-search"
        return render_template("search.html", **context)

    @app.get("/tendances")
    def territory_trends():
        context = _build_territory_trends_context_from_request()
        context["active_page"] = "territory_trends"
        context["body_class"] = "page-trends"
        return render_template("territory_trends.html", **context)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/api/state")
    def api_state():
        return jsonify(_build_render_context_from_request())

    @app.get("/api/offers")
    def api_offers():
        return jsonify(_build_render_context_from_request().get("paged_offers", []))

    @app.get("/api/trends")
    def api_trends():
        return jsonify(_build_render_context_from_request().get("trends", {}))

    return app


app = create_app()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="France Travail offers and trends web dashboard.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--debug", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
