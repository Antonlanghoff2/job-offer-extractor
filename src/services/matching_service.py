# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Deterministic scoring and explanation logic for user-to-offer matching."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.offer_normalization import normalize_text
from src.ner.skill_normalizer import canonicalize_skill_name
from src.services.offer_normalization import normalize_offer_for_matching
from src.matching.scoring import build_scoring_result, calculate_weighted_score
from src.matching.weights import DEFAULT_MATCHING_WEIGHTS, ensure_matching_weights


def _tokenize(value: object) -> set[str]:
    text = normalize_text(value)
    if not text:
        return set()
    tokens = set(re.split(r"[^a-z0-9]+", text))
    tokens.discard("")
    return tokens


def normalize_skill_name(name: object) -> str:
    """Retourne le nom canonique d'une compétence."""

    return canonicalize_skill_name(name)


@dataclass
class ScoreComponent:
    score: float
    applicable: bool
    details: Dict[str, Any]


def _scale(value: float) -> float:
    return max(0.0, min(100.0, value))


def _component_value(component: ScoreComponent) -> Optional[float]:
    if not component.applicable:
        return None
    return round(max(0.0, min(100.0, component.score)) / 100.0, 4)


def compute_skill_score(profile_skills: List[Dict[str, Any]], offer_skills: List[str]) -> ScoreComponent:
    profile_map = {
        normalize_skill_name(item.get("normalized_name") or item.get("name") or item.get("nom")): item
        for item in profile_skills
        if item
    }
    offer_map = {normalize_skill_name(skill): skill for skill in offer_skills if normalize_skill_name(skill)}
    if not profile_map or not offer_map:
        return ScoreComponent(100.0, False, {"matching_skills": [], "missing_skills": [], "coverage": None})
    matched = sorted(
        {profile_map[key].get("normalized_name") or key for key in profile_map.keys() & offer_map.keys()}
    )
    missing = sorted({normalize_skill_name(key) or key for key in offer_map.keys() if key not in profile_map})
    coverage = len(matched) / max(len(offer_map), 1)
    total = _scale(coverage * 85.0)
    return ScoreComponent(total, True, {"matching_skills": matched, "missing_skills": missing, "coverage": round(coverage, 3)})


def compute_job_score(profile_job_titles: List[str], profile_experience_titles: List[str], offer_title: str) -> ScoreComponent:
    profile_titles = [_tokenize(title) for title in profile_job_titles if title]
    profile_titles += [_tokenize(title) for title in profile_experience_titles if title]
    offer_tokens = _tokenize(offer_title)
    if not offer_tokens or not profile_titles:
        return ScoreComponent(100.0, False, {"matched_tokens": [], "coverage": None})
    best = 0.0
    matched_tokens: set[str] = set()
    for candidate in profile_titles:
        overlap = candidate & offer_tokens
        union = candidate | offer_tokens
        if not union:
            continue
        score = len(overlap) / len(union)
        if score > best:
            best = score
            matched_tokens = overlap
    return ScoreComponent(_scale(best * 100.0), True, {"matched_tokens": sorted(matched_tokens), "coverage": round(best, 3)})


def _years_from_profile(profile_experiences: List[Dict[str, Any]]) -> Optional[float]:
    years = 0.0
    found = False
    for experience in profile_experiences:
        if experience.get("duration_years") is not None:
            years += float(experience["duration_years"])
            found = True
        elif experience.get("start_date") and experience.get("end_date"):
            try:
                from datetime import date
                start = date.fromisoformat(str(experience["start_date"]))
                end = date.fromisoformat(str(experience["end_date"]))
                years += max((end - start).days / 365.25, 0.0)
                found = True
            except Exception:
                continue
    return years if found else None


def compute_experience_score(profile_experiences: List[Dict[str, Any]], offer_experience: object) -> ScoreComponent:
    if not offer_experience:
        return ScoreComponent(100.0, False, {"required": None, "profile_years": _years_from_profile(profile_experiences)})
    profile_years = _years_from_profile(profile_experiences)
    if profile_years is None:
        return ScoreComponent(100.0, False, {"required": str(offer_experience), "profile_years": None})
    requirement = normalize_text(offer_experience)
    required_years = None
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:ans|annees|années)", requirement)
    if match:
        required_years = float(match.group(1).replace(",", "."))
    if required_years is None:
        return ScoreComponent(100.0, False, {"required": str(offer_experience), "profile_years": profile_years})
    if profile_years >= required_years:
        score = 100.0
    else:
        score = _scale((profile_years / required_years) * 100.0)
    return ScoreComponent(score, True, {"required_years": required_years, "profile_years": round(profile_years, 2)})


def compute_diploma_score(profile_diplomas: List[Dict[str, Any]], offer_diplomas: List[str]) -> ScoreComponent:
    profile_titles = {normalize_text(item.get("title") or item.get("intitule")) for item in profile_diplomas if item}
    required_titles = {normalize_text(item) for item in offer_diplomas if item}
    profile_titles.discard("")
    required_titles.discard("")
    if not profile_titles or not required_titles:
        return ScoreComponent(100.0, False, {"matching_diplomas": [], "missing_diplomas": [], "coverage": None})
    matched = sorted(profile_titles & required_titles)
    missing = sorted(required_titles - profile_titles)
    coverage = len(matched) / len(required_titles)
    return ScoreComponent(_scale(coverage * 100.0), True, {"matching_diplomas": matched, "missing_diplomas": missing, "coverage": round(coverage, 3)})


def _extract_department_from_text(text: str) -> Optional[str]:
    normalized = normalize_text(text)
    if not normalized:
        return None
    match = re.search(r"\b(\d{2})(?:\d{3})?\b", normalized)
    if match:
        return match.group(1)
    if normalized.startswith("97") and len(normalized) >= 3 and normalized[2].isdigit():
        return normalized[:3]
    return None


def compute_location_score(profile: Dict[str, Any], offer: Dict[str, Any]) -> ScoreComponent:
    if not any(profile.get(key) for key in ("city", "postal_code", "department", "search_radius_km")):
        return ScoreComponent(100.0, False, {"reason": "profil sans contrainte locale"})
    offer_locations = [normalize_text(value) for value in offer.get("lieux", []) if value]
    if not offer_locations and offer.get("lieuTravail"):
        offer_locations.append(normalize_text(offer["lieuTravail"].get("libelle")))
        offer_locations.append(normalize_text(offer["lieuTravail"].get("commune")))
        offer_locations.append(normalize_text(offer["lieuTravail"].get("codePostal")))
    offer_locations = [item for item in offer_locations if item]
    if not offer_locations:
        return ScoreComponent(100.0, False, {"reason": "offre sans localisation exploitable"})
    city = normalize_text(profile.get("city"))
    postal = normalize_text(profile.get("postal_code"))
    department = normalize_text(profile.get("department"))
    offer_departments = []
    for item in offer_locations:
        department_from_text = _extract_department_from_text(item)
        if department_from_text:
            offer_departments.append(department_from_text)
    if any(city and city in loc for loc in offer_locations):
        return ScoreComponent(100.0, True, {"reason": "ville correspondante"})
    if any(postal and postal in loc for loc in offer_locations):
        return ScoreComponent(100.0, True, {"reason": "code postal correspondant"})
    if department and any(department == item or department == item[:2] for item in offer_departments):
        return ScoreComponent(80.0, True, {"reason": "même département"})
    if postal and any(item.startswith(postal[:2]) for item in offer_locations if len(postal) >= 2):
        return ScoreComponent(80.0, True, {"reason": "même département postal"})
    if department and any(department in loc for loc in offer_locations):
        return ScoreComponent(60.0, True, {"reason": "département partiellement correspondant"})
    if profile.get("search_radius_km"):
        return ScoreComponent(0.0, True, {"reason": "localisation éloignée", "offer_locations": offer_locations})
    return ScoreComponent(20.0, True, {"reason": "localisation non correspondante", "offer_locations": offer_locations})


def compute_salary_score(profile_salary: Optional[object], offer: Dict[str, Any]) -> ScoreComponent:
    try:
        requested_salary = float(profile_salary) if profile_salary not in (None, "") else None
    except (TypeError, ValueError):
        requested_salary = None
    if requested_salary is None:
        return ScoreComponent(100.0, False, {"reason": "préférence salariale non renseignée"})

    offer_min = offer.get("salaire_min")
    offer_max = offer.get("salaire_max")
    try:
        offer_min_value = float(offer_min) if offer_min not in (None, "") else None
    except (TypeError, ValueError):
        offer_min_value = None
    try:
        offer_max_value = float(offer_max) if offer_max not in (None, "") else None
    except (TypeError, ValueError):
        offer_max_value = None

    if offer_min_value is None and offer_max_value is None:
        return ScoreComponent(100.0, False, {"reason": "salaire non renseigné sur l'offre", "requested_salary": requested_salary})
    if offer_min_value is None:
        offer_min_value = offer_max_value
    if offer_max_value is None:
        offer_max_value = offer_min_value
    if offer_min_value is None or offer_max_value is None:
        return ScoreComponent(100.0, False, {"reason": "salaire non renseigné sur l'offre", "requested_salary": requested_salary})

    if offer_max_value < requested_salary:
        ratio = offer_max_value / requested_salary if requested_salary else 0.0
        return ScoreComponent(_scale(ratio * 100.0), True, {
            "reason": "salaire inférieur au minimum souhaité",
            "requested_salary": round(requested_salary, 2),
            "offer_salary_min": round(offer_min_value, 2),
            "offer_salary_max": round(offer_max_value, 2),
        })
    if offer_min_value >= requested_salary:
        return ScoreComponent(100.0, True, {
            "reason": "salaire au moins égal au minimum souhaité",
            "requested_salary": round(requested_salary, 2),
            "offer_salary_min": round(offer_min_value, 2),
            "offer_salary_max": round(offer_max_value, 2),
        })
    return ScoreComponent(80.0, True, {
        "reason": "fourchette salariale compatible",
        "requested_salary": round(requested_salary, 2),
        "offer_salary_min": round(offer_min_value, 2),
        "offer_salary_max": round(offer_max_value, 2),
    })


def compute_contract_score(profile_contract: Optional[str], offer_contract: Optional[str]) -> ScoreComponent:
    if not profile_contract or not offer_contract:
        return ScoreComponent(100.0, False, {"reason": "absence de préférence ou de contrat"})
    profile_norm = normalize_text(profile_contract)
    offer_norm = normalize_text(offer_contract)
    if profile_norm == offer_norm:
        return ScoreComponent(100.0, True, {"reason": "contrat identique"})
    return ScoreComponent(0.0, True, {"reason": "contrat différent", "profile": profile_contract, "offer": offer_contract})


def compute_remote_score(profile_remote: Optional[str], offer_remote: Optional[str]) -> ScoreComponent:
    if not profile_remote or normalize_text(profile_remote) in {"indifferent", ""}:
        return ScoreComponent(100.0, False, {"reason": "préférence télétravail neutre"})
    profile_norm = normalize_text(profile_remote)
    offer_norm = normalize_text(offer_remote)
    if not offer_norm:
        return ScoreComponent(100.0, False, {"reason": "télétravail non renseigné sur l'offre"})
    if profile_norm == offer_norm:
        return ScoreComponent(100.0, True, {"reason": "préférence télétravail respectée"})
    if profile_norm == "hybride" and offer_norm in {"hybride", "teletravail", "presentiel"}:
        return ScoreComponent(70.0, True, {"reason": "compatibilité partielle"})
    return ScoreComponent(0.0, True, {"reason": "préférence télétravail non respectée"})


def _profile_skill_list(profile_skills: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized = []
    for item in profile_skills:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("nom") or ""
        normalized_name = normalize_skill_name(item.get("normalized_name") or name)
        normalized.append({**item, "name": name, "normalized_name": normalized_name})
    return normalized


def calculate_matching_score(
    user_profile: Dict[str, Any],
    job_offer: Dict[str, Any],
    weights: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    offer = normalize_offer_for_matching(job_offer, source=job_offer.get("source"))
    profile_skills = _profile_skill_list(user_profile.get("skills", []))
    profile_jobs = []
    for item in user_profile.get("desired_jobs", []):
        if isinstance(item, dict):
            title = item.get("job_title") or item.get("title")
        else:
            title = item
        if title:
            profile_jobs.append(title)
    profile_experience_titles = []
    for item in user_profile.get("experiences", []):
        if isinstance(item, dict):
            title = item.get("job_title") or item.get("poste")
        else:
            title = item
        if title:
            profile_experience_titles.append(title)
    profile_diplomas = user_profile.get("diplomas", [])

    skill_component = compute_skill_score(profile_skills, offer.get("competences", []))
    job_component = compute_job_score(profile_jobs, profile_experience_titles, offer.get("titre") or "")
    experience_component = compute_experience_score(user_profile.get("experiences", []), offer.get("experience_requise"))
    diploma_component = compute_diploma_score(profile_diplomas, offer.get("diplomes_requis", []))
    location_component = compute_location_score(user_profile, offer)
    salary_component = compute_salary_score(user_profile.get("minimum_salary"), offer)
    contract_component = compute_contract_score(user_profile.get("contract_preference"), offer.get("contrat"))
    remote_component = compute_remote_score(user_profile.get("remote_preference"), offer.get("teletravail"))

    criterion_components = {
        "competences": skill_component,
        "metier": job_component,
        "experience": experience_component,
        "diplome": diploma_component,
        "localisation": location_component,
        "contrat": contract_component,
        "teletravail": remote_component,
        "salaire": salary_component,
    }
    criterion_scores = {key: _component_value(component) for key, component in criterion_components.items()}
    normalized_weights = ensure_matching_weights(weights or DEFAULT_MATCHING_WEIGHTS)
    weighted_score = calculate_weighted_score(criterion_scores, normalized_weights)
    criterion_details = {key: component.details for key, component in criterion_components.items()}
    scoring_result = build_scoring_result(
        criterion_scores,
        normalized_weights,
        common_skills=skill_component.details.get("matching_skills", []),
        missing_skills=skill_component.details.get("missing_skills", []),
        criterion_details=criterion_details,
        source=str(offer.get("source") or ""),
        url_originale=str(offer.get("url_originale") or offer.get("url") or ""),
    )

    explanation_parts = []
    matching_skills = skill_component.details.get("matching_skills", [])
    missing_skills = skill_component.details.get("missing_skills", [])
    if skill_component.applicable:
        explanation_parts.append(
            "Vous possédez %s compétence(s) commune(s) sur %s demandée(s)."
            % (len(matching_skills), len(matching_skills) + len(missing_skills))
        )
        if missing_skills:
            explanation_parts.append("Compétences manquantes: %s." % ", ".join(missing_skills[:5]))
    if job_component.applicable and job_component.score >= 50:
        explanation_parts.append("Votre expérience et vos métiers recherchés correspondent au poste.")
    if location_component.applicable:
        location_reason = location_component.details.get("reason")
        explanation_parts.append("Compatibilité localisation: %.0f/100.%s" % (location_component.score, (" " + str(location_reason)) if location_reason else ""))
    if salary_component.applicable:
        salary_reason = salary_component.details.get("reason")
        explanation_parts.append("Compatibilité salariale: %.0f/100.%s" % (salary_component.score, (" " + str(salary_reason)) if salary_reason else ""))
    if contract_component.applicable:
        explanation_parts.append("Contrat: %.0f/100." % contract_component.score)
    if remote_component.applicable:
        explanation_parts.append("Télétravail: %.0f/100." % remote_component.score)

    scoring_result.update(
        {
            "offer_identifier": offer.get("id"),
            "offer": offer,
            "global_score": weighted_score,
            "skill_score": round(skill_component.score, 2),
            "job_score": round(job_component.score, 2),
            "experience_score": round(experience_component.score, 2),
            "diploma_score": round(diploma_component.score, 2),
            "location_score": round(location_component.score, 2),
            "salary_score": round(salary_component.score, 2),
            "contract_score": round(contract_component.score, 2),
            "remote_score": round(remote_component.score, 2),
            "matching_skills": matching_skills,
            "missing_skills": missing_skills,
            "criterion_scores": criterion_scores,
            "criterion_details": criterion_details,
            "matching_weights": normalized_weights,
            "explanation": {
                "summary": "Cette offre correspond à %.0f%% à votre profil." % weighted_score,
                "details": explanation_parts,
                "matching_skills": matching_skills,
                "missing_skills": missing_skills,
                "subscores": {key: component.score for key, component in criterion_components.items()},
            },
        }
    )
    return scoring_result


def compute_match(profile: Dict[str, Any], offer_raw: Dict[str, Any], weights: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    return calculate_matching_score(profile, offer_raw, weights=weights)
