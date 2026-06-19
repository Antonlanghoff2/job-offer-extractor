# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Deterministic formation recommendation helpers for TrendRadar IA.

The service consumes normalized market offers, aggregates market signals and
maps them to pedagogical domains stored in ``config/formation_domains.json``.
The implementation stays fully deterministic and does not depend on any
external model or network call.
"""

from __future__ import annotations

import json
import logging
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.model2_market_context import normalize_market_offer, normalize_text
from src.services.matching_service import normalize_skill_name
from src.trend_aggregation import aggregate_trends


logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DOMAIN_CONFIG_PATH = PROJECT_ROOT / "config" / "formation_domains.json"


def _as_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _split_values(value: object) -> List[object]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return []
        if any(sep in cleaned for sep in (",", ";", "|")):
            return [part.strip() for part in re.split(r"[;,|]", cleaned) if part.strip()]
        return [cleaned]
    return [value]


def _parse_date(value: object) -> Optional[Tuple[int, int, int]]:
    if value is None:
        return None
    text = _as_text(value)
    if not text:
        return None
    text = text.replace("Z", "").replace("/", "-")
    parts = text.split("T", 1)[0]
    if re.fullmatch(r"\d{4}", parts):
        return int(parts), 1, 1
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", parts):
        year, month, day = parts.split("-")
        return int(year), int(month), int(day)
    return None


def _territory_matches(offer: Dict[str, Any], territory: str) -> bool:
    candidate = normalize_text(territory)
    if not candidate:
        return False
    parts: List[str] = []
    for key in ("territoire", "ville", "lieu", "location", "code_postal", "codePostal"):
        value = offer.get(key)
        if isinstance(value, list):
            parts.extend(_as_text(item) for item in value if _as_text(item))
        elif value not in (None, ""):
            parts.append(_as_text(value))
    lieu_travail = offer.get("lieuTravail")
    if isinstance(lieu_travail, dict):
        for key in ("libelle", "commune", "codePostal"):
            value = lieu_travail.get(key)
            if value not in (None, ""):
                parts.append(_as_text(value))
    blob = normalize_text(" ".join(parts))
    return bool(blob) and (candidate in blob or blob in candidate)


def _offer_date(offer: Dict[str, Any]) -> Optional[Tuple[int, int, int]]:
    for key in ("date_publication", "date_publication_offre", "dateCreation", "dateActualisation", "date_creation", "date", "published_at"):
        parsed = _parse_date(offer.get(key))
        if parsed is not None:
            return parsed
    return None


def _filter_offers(offers: Sequence[Dict[str, Any]], territoire: Optional[str], periode_jours: int) -> List[Dict[str, Any]]:
    valid_offers = [offer for offer in offers if isinstance(offer, dict)]
    reference_dates = [date for date in (_offer_date(offer) for offer in valid_offers) if date is not None]
    if reference_dates:
        reference = max(reference_dates)
    else:
        reference = None
    filtered: List[Dict[str, Any]] = []
    for offer in valid_offers:
        if territoire and not _territory_matches(offer, territoire):
            continue
        offer_date = _offer_date(offer)
        if reference is not None and offer_date is not None:
            ref_year, ref_month, ref_day = reference
            ref_days = (ref_year * 372) + (ref_month * 31) + ref_day
            off_days = (offer_date[0] * 372) + (offer_date[1] * 31) + offer_date[2]
            if ref_days - off_days > max(periode_jours, 0):
                continue
        filtered.append(offer)
    return filtered


def _collect_offer_skills(offer: Dict[str, Any]) -> List[str]:
    candidates: List[str] = []
    for key in ("competences", "competences_requises", "skills", "skillset", "mots_cles"):
        for item in _split_values(offer.get(key)):
            if isinstance(item, dict):
                candidate = item.get("libelle") or item.get("label") or item.get("name") or item.get("title") or item.get("code")
            else:
                candidate = item
            text = _as_text(candidate)
            if text:
                candidates.append(text)
    deduped: List[str] = []
    seen = set()
    for item in candidates:
        key = normalize_skill_name(item)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(key)
    return deduped


def _collect_offer_metier(offer: Dict[str, Any]) -> str:
    for key in ("metier", "intitule_poste", "intitule", "titre", "job_title", "title"):
        value = offer.get(key)
        if value not in (None, ""):
            return _as_text(value)
    return ""


def _collect_offer_level(offer: Dict[str, Any]) -> str:
    level = _as_text(offer.get("niveau") or offer.get("experience_level") or offer.get("seniority") or offer.get("experienceLibelle") or offer.get("experience"))
    lowered = normalize_text(level)
    if not lowered:
        return ""
    if any(token in lowered for token in ("senior", "expert", "lead", "senior")):
        return "senior"
    if any(token in lowered for token in ("junior", "debutant", "débutant", "starter")):
        return "junior"
    if any(token in lowered for token in ("intermediaire", "intermediate", "confirm", "avance", "avancé")):
        return "intermediaire"
    return "intermediaire"


def _collect_offer_contract(offer: Dict[str, Any]) -> str:
    for key in ("contrat", "typeContratLibelle", "typeContrat", "contract"):
        value = offer.get(key)
        if value not in (None, ""):
            return _as_text(value)
    return ""


def _normalize_domain_competence(value: object) -> Dict[str, Any]:
    if isinstance(value, dict):
        name = value.get("nom") or value.get("name") or value.get("label") or ""
        aliases = value.get("aliases") or []
    else:
        name = value
        aliases = []
    canonical = normalize_skill_name(name)
    alias_values = {normalize_text(name), normalize_text(canonical)}
    for alias in _split_values(aliases):
        alias_values.add(normalize_text(alias))
    alias_values.discard("")
    return {"nom": canonical or _as_text(name), "aliases": sorted(alias_values)}


def _load_domains(path: Path = DEFAULT_DOMAIN_CONFIG_PATH) -> List[Dict[str, Any]]:
    if not path.exists():
        logger.error("Fichier de configuration des domaines de formation introuvable: %s", path)
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Impossible de lire la configuration des domaines de formation: %s", path)
        return []
    raw_domains = payload.get("domains") if isinstance(payload, dict) else None
    if not isinstance(raw_domains, list):
        logger.error("La configuration des domaines de formation est invalide: %s", path)
        return []
    domains: List[Dict[str, Any]] = []
    for raw_domain in raw_domains:
        if not isinstance(raw_domain, dict):
            continue
        title = _as_text(raw_domain.get("titre") or raw_domain.get("title") or raw_domain.get("nom"))
        if not title:
            continue
        competencies = [_normalize_domain_competence(item) for item in _split_values(raw_domain.get("competences"))]
        metiers = [_as_text(item) for item in _split_values(raw_domain.get("metiers")) if _as_text(item)]
        aliases = {normalize_text(title)}
        for alias in _split_values(raw_domain.get("aliases")):
            alias_text = normalize_text(alias)
            if alias_text:
                aliases.add(alias_text)
        for item in competencies:
            aliases.add(normalize_text(item.get("nom")))
            for alias in item.get("aliases", []):
                aliases.add(normalize_text(alias))
        for metier in metiers:
            aliases.add(normalize_text(metier))
        domains.append(
            {
                "id": _as_text(raw_domain.get("id") or title),
                "titre": title,
                "aliases": sorted(item for item in aliases if item),
                "competences": competencies,
                "metiers": metiers,
                "public_cible": _as_text(raw_domain.get("public_cible") or raw_domain.get("public_cible_titre")),
                "prerequis": [_as_text(item) for item in _split_values(raw_domain.get("prerequis")) if _as_text(item)],
                "objectifs": [_as_text(item) for item in _split_values(raw_domain.get("objectifs")) if _as_text(item)],
                "modules": [
                    {
                        "titre": _as_text(module.get("titre") if isinstance(module, dict) else module),
                        "duree_heures": int(module.get("duree_heures") if isinstance(module, dict) and module.get("duree_heures") is not None else 0),
                    }
                    for module in _split_values(raw_domain.get("modules"))
                    if _as_text(module.get("titre") if isinstance(module, dict) else module)
                ],
            }
        )
    return domains


def _domain_skill_keys(domain: Dict[str, Any]) -> List[str]:
    keys = []
    for item in domain.get("competences", []):
        if isinstance(item, dict):
            key = normalize_skill_name(item.get("nom"))
        else:
            key = normalize_skill_name(item)
        if key and key not in keys:
            keys.append(key)
    if not keys:
        for alias in domain.get("aliases", []):
            canonical = normalize_skill_name(alias)
            if canonical and canonical not in keys:
                keys.append(canonical)
    return keys


def _domain_score(
    domain: Dict[str, Any],
    offers: Sequence[Dict[str, Any]],
    total_offers: int,
) -> Dict[str, Any]:
    domain_aliases = set(domain.get("aliases", []))
    domain_skill_keys = _domain_skill_keys(domain)
    matched_offers: List[Dict[str, Any]] = []
    skill_counter: Counter = Counter()
    metier_counter: Counter = Counter()
    pair_counter: Counter = Counter()
    alias_hits = 0
    for offer in offers:
        skills = _collect_offer_skills(offer)
        metier = _collect_offer_metier(offer)
        blob = normalize_text(" ".join([offer.get("titre", "") if isinstance(offer.get("titre"), str) else _as_text(offer.get("titre")), metier, offer.get("description", "") if isinstance(offer.get("description"), str) else _as_text(offer.get("description"))]))
        offer_alias_hits = sum(1 for alias in domain_aliases if alias and alias in blob)
        matched_skill_set = [skill for skill in skills if skill in domain_skill_keys or normalize_text(skill) in domain_aliases]
        if not matched_skill_set and offer_alias_hits == 0:
            continue
        matched_offers.append(offer)
        alias_hits += offer_alias_hits
        metier_label = _collect_offer_metier(offer)
        if metier_label:
            metier_counter[metier_label] += 1
        for skill in matched_skill_set:
            skill_counter[skill] += 1
        if len(matched_skill_set) >= 2:
            ordered_skills = sorted(set(matched_skill_set))
            for index, skill_a in enumerate(ordered_skills):
                for skill_b in ordered_skills[index + 1:]:
                    pair_counter[(skill_a, skill_b)] += 1

    matched_skill_keys = [skill for skill, _count in skill_counter.most_common()]
    matched_skill_count = len(matched_skill_keys)
    coverage = (matched_skill_count / float(len(domain_skill_keys))) if domain_skill_keys else 0.0
    coverage = max(0.0, min(1.0, coverage))
    freq_values = [count / float(total_offers) for _skill, count in skill_counter.items() if total_offers > 0]
    score_frequence = sum(freq_values) / float(len(freq_values)) if freq_values else 0.0
    score_frequence = max(0.0, min(1.0, score_frequence))
    coverage_offers = len(matched_offers) / float(total_offers) if total_offers else 0.0
    coverage_offers = max(0.0, min(1.0, coverage_offers))
    if pair_counter and matched_offers:
        pair_strengths = [count / float(len(matched_offers)) for count in pair_counter.values()]
        score_coherence = sum(pair_strengths) / float(len(pair_strengths))
    elif matched_skill_count:
        score_coherence = min(1.0, matched_skill_count / 5.0)
    else:
        score_coherence = 0.0
    score_coherence = max(0.0, min(1.0, score_coherence))
    score_diversite = min(1.0, len(metier_counter) / 3.0) if metier_counter else 0.0
    score_fiabilite = min(1.0, total_offers / 40.0) if total_offers else 0.0
    score_alias = min(1.0, alias_hits / 4.0) if alias_hits else 0.0
    score = (
        0.30 * score_frequence
        + 0.20 * coverage_offers
        + 0.15 * score_coherence
        + 0.10 * score_diversite
        + 0.10 * score_fiabilite
        + 0.15 * score_alias
    )
    score = max(0.0, min(1.0, score))
    confidence = _confidence_label(total_offers)
    if total_offers < 15:
        priority = "exploratoire"
    elif score >= 0.75:
        priority = "élevée"
    elif score >= 0.55:
        priority = "moyenne"
    else:
        priority = "faible"
    top_skills = matched_skill_keys[:5]
    top_metiers = [metier for metier, _count in metier_counter.most_common(3)]
    limits: List[str] = []
    if total_offers < 15:
        limits.append("Analyse exploratoire: l’échantillon reste limité.")
    elif total_offers < 40:
        limits.append("Volume intermédiaire: la recommandation doit encore être confirmée.")
    if coverage_offers < 0.5 and total_offers >= 5:
        limits.append("Les compétences retenues couvrent une part limitée des offres analysées.")
    if not top_skills:
        limits.append("Aucune famille de compétences forte n’a été identifiée.")
    return {
        "id": domain.get("id"),
        "titre": domain.get("titre"),
        "priorite": priority,
        "score_pertinence": round(score, 3),
        "niveau_confiance": confidence,
        "nombre_offres_analysees": total_offers,
        "score_frequence": round(score_frequence, 3),
        "score_couverture": round(coverage_offers, 3),
        "score_coherence": round(score_coherence, 3),
        "score_diversite_metiers": round(score_diversite, 3),
        "score_fiabilite": round(score_fiabilite, 3),
        "score_alias": round(score_alias, 3),
        "competences_cibles": top_skills,
        "metiers_cibles": top_metiers,
        "matched_skills": matched_skill_keys,
        "matched_metiers": top_metiers,
        "matched_offer_count": len(matched_offers),
        "coverage_ratio": round(coverage, 3),
        "public_cible": domain.get("public_cible") or "Professionnels techniques",
        "prerequis": domain.get("prerequis") or [],
        "objectifs_pedagogiques": domain.get("objectifs") or [],
        "modules": domain.get("modules") or [],
        "justification": (
            "Cette proposition couvre %s des offres analysées et regroupe des compétences fréquemment demandées ensemble."
            % ("{:.0%}".format(coverage_offers))
        ),
        "limites": limits,
        "_matched_offers": matched_offers,
        "_pair_counter": pair_counter,
    }


def _confidence_label(total_offers: int) -> str:
    if total_offers >= 40:
        return "bon"
    if total_offers >= 15:
        return "moyen"
    if total_offers >= 5:
        return "faible"
    return "insuffisant"


def _fallback_recommendation(offers: Sequence[Dict[str, Any]], territory: Optional[str], period_days: int, trends: Dict[str, Any]) -> Dict[str, Any]:
    total_offers = int(trends.get("nombre_offres") or len(offers))
    top_competences = list(trends.get("competences", {}).items())
    top_metiers = list(trends.get("metiers", {}).items())
    skills = [skill for skill, _count in top_competences[:5]]
    metiers = [metier for metier, _count in top_metiers[:3]]
    score = min(1.0, total_offers / 40.0)
    return {
        "id": "fallback",
        "titre": "Renforcer les compétences numériques prioritaires",
        "territoire": territory or "Tous les territoires",
        "priorite": "exploratoire" if total_offers < 15 else ("moyenne" if total_offers < 40 else "élevée"),
        "score_pertinence": round(score, 3),
        "niveau_confiance": _confidence_label(total_offers),
        "nombre_offres_analysees": total_offers,
        "competences_cibles": skills,
        "metiers_cibles": metiers,
        "public_cible": "Professionnels techniques",
        "prerequis": ["Bases techniques générales"],
        "objectifs_pedagogiques": [
            "Identifier les compétences les plus demandées",
            "Consolider les bases techniques",
            "Structurer une montée en compétences adaptée au marché",
        ],
        "modules": [
            {"titre": "Lecture du marché local", "duree_heures": 7},
            {"titre": "Approfondissement des compétences clés", "duree_heures": 14},
            {"titre": "Projet d’application", "duree_heures": 7},
        ],
        "justification": "La configuration pédagogique n'a pas permis d'identifier une spécialisation claire. La recommandation reste exploratoire.",
        "limites": ["Aucune spécialisation clairement dominante n’a été détectée."],
        "score_frequence": round(score, 3),
        "score_couverture": round(score, 3),
        "score_coherence": round(score, 3),
        "score_diversite_metiers": round(score, 3),
        "score_fiabilite": round(score, 3),
    }


def recommend_training(
    offers: Sequence[Dict[str, Any]],
    territoire: Optional[str] = None,
    periode_jours: int = 30,
    config_path: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """Return the most relevant training recommendation for the market slice.

    The function returns ``None`` when the sample size is too small to avoid a
    misleading recommendation.
    """

    normalized_offers = [normalize_market_offer(offer) for offer in offers if isinstance(offer, dict)]
    if not normalized_offers:
        return None
    normalized_offers = _filter_offers(normalized_offers, territoire, periode_jours)
    trends = aggregate_trends(normalized_offers, territoire=territoire, periode_jours=periode_jours)
    total_offers = int(trends.get("nombre_offres") or 0)
    if total_offers < 5:
        return None

    domains = _load_domains(config_path or DEFAULT_DOMAIN_CONFIG_PATH)
    scored_domains: List[Dict[str, Any]] = []
    for domain in domains:
        scored = _domain_score(domain, normalized_offers, total_offers)
        scored_domains.append(scored)
    scored_domains.sort(key=lambda item: (-float(item.get("score_pertinence") or 0.0), _as_text(item.get("titre")).lower()))
    best = scored_domains[0] if scored_domains else None
    if not best or float(best.get("score_pertinence") or 0.0) < 0.15:
        fallback = _fallback_recommendation(normalized_offers, territoire, periode_jours, trends)
        fallback["territoire"] = territoire or "Tous les territoires"
        return fallback

    recommendation = {key: value for key, value in best.items() if not key.startswith("_")}
    recommendation["territoire"] = territoire or "Tous les territoires"
    recommendation["periode_jours"] = periode_jours
    recommendation["nombre_offres_analysees"] = total_offers
    recommendation["modules"] = recommendation.get("modules") or []
    recommendation["limites"] = recommendation.get("limites") or []
    recommendation["justification"] = (
        "Cette proposition couvre %s des offres analysées et regroupe des compétences fréquemment demandées ensemble."
        % ("{:.0%}".format(float(recommendation.get("score_couverture") or 0.0)))
    )
    return recommendation


def build_recommendation_context(
    offers: Sequence[Dict[str, Any]],
    territoire: Optional[str] = None,
    periode_jours: int = 30,
    config_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Return a UI-friendly context for the formation recommendation page."""

    normalized_offers = [normalize_market_offer(offer) for offer in offers if isinstance(offer, dict)]
    trends = aggregate_trends(normalized_offers, territoire=territoire, periode_jours=periode_jours)
    territories = sorted(
        {str(offer.get("territoire") or "").strip() for offer in normalized_offers if str(offer.get("territoire") or "").strip()},
        key=lambda value: normalize_text(value),
    )
    recommendation = recommend_training(normalized_offers, territoire=territoire, periode_jours=periode_jours, config_path=config_path)
    return {
        "recommendation": recommendation,
        "territoire": territoire or "",
        "territory_options": territories,
        "period_days": periode_jours,
        "has_data": bool(trends.get("nombre_offres")),
        "total_offers": int(trends.get("nombre_offres") or 0),
        "error_message": None,
    }
