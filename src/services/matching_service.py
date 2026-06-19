# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Deterministic scoring and explanation logic for user-to-offer matching."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from src.offer_normalization import normalize_text
from src.services.offer_normalization import normalize_offer_for_matching

WEIGHTS = {
    "skill_score": 0.50,
    "job_score": 0.15,
    "experience_score": 0.10,
    "diploma_score": 0.05,
    "location_score": 0.10,
    "contract_score": 0.05,
    "remote_score": 0.05,
}

SKILL_SYNONYMS = {
    "javascript": "javascript",
    "java script": "javascript",
    "machine learning": "machinelearning",
    "machinelearning": "machinelearning",
    "python": "python",
    "flask": "flask",
    "sql": "sql",
    "docker": "docker",
    "fastapi": "fastapi",
    "aws": "aws",
}


def _tokenize(value: object) -> set[str]:
    text = normalize_text(value)
    if not text:
        return set()
    tokens = set(re.split(r"[^a-z0-9]+", text))
    tokens.discard("")
    normalized = set()
    for token in tokens:
        normalized.add(SKILL_SYNONYMS.get(token, token))
    return normalized


def normalize_skill_name(name: object) -> str:
    text = normalize_text(name)
    compact = re.sub(r"[^a-z0-9]+", "", text)
    return SKILL_SYNONYMS.get(text, SKILL_SYNONYMS.get(compact, compact or text))


@dataclass
class ScoreComponent:
    score: float
    applicable: bool
    details: dict[str, Any]


def _scale(value: float) -> float:
    return max(0.0, min(100.0, value))


def compute_skill_score(profile_skills: list[dict[str, Any]], offer_skills: list[str]) -> ScoreComponent:
    profile_map = {normalize_skill_name(item.get("normalized_name") or item.get("name") or item.get("nom")): item for item in profile_skills if item}
    offer_map = {normalize_skill_name(skill): skill for skill in offer_skills if normalize_skill_name(skill)}
    if not profile_map or not offer_map:
        return ScoreComponent(100.0, False, {"matching_skills": [], "missing_skills": [], "coverage": None})
    matched = sorted({profile_map[key].get("name") or profile_map[key].get("nom") or key for key in profile_map.keys() & offer_map.keys()})
    missing = sorted({value for key, value in offer_map.items() if key not in profile_map})
    coverage = len(matched) / max(len(offer_map), 1)
    total = _scale((coverage * 85.0))
    return ScoreComponent(total, True, {"matching_skills": matched, "missing_skills": missing, "coverage": round(coverage, 3)})


def compute_job_score(profile_job_titles: list[str], profile_experience_titles: list[str], offer_title: str) -> ScoreComponent:
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


def _years_from_profile(profile_experiences: list[dict[str, Any]]) -> float | None:
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


def compute_experience_score(profile_experiences: list[dict[str, Any]], offer_experience: object) -> ScoreComponent:
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


def compute_diploma_score(profile_diplomas: list[dict[str, Any]], offer_diplomas: list[str]) -> ScoreComponent:
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


def compute_location_score(profile: dict[str, Any], offer: dict[str, Any]) -> ScoreComponent:
    if not any(profile.get(key) for key in ("city", "postal_code", "department", "search_radius_km")):
        return ScoreComponent(100.0, False, {"reason": "profil sans contrainte locale"})
    offer_locations = [normalize_text(value) for value in offer.get("lieux", []) if value]
    if not offer_locations and offer.get("lieuTravail"):
        offer_locations.append(normalize_text(offer["lieuTravail"].get("libelle")))
    offer_locations = [item for item in offer_locations if item]
    if not offer_locations:
        return ScoreComponent(100.0, False, {"reason": "offre sans localisation exploitable"})
    city = normalize_text(profile.get("city"))
    postal = normalize_text(profile.get("postal_code"))
    department = normalize_text(profile.get("department"))
    if any(city and city in loc for loc in offer_locations):
        return ScoreComponent(100.0, True, {"reason": "ville correspondante"})
    if any(postal and postal in loc for loc in offer_locations):
        return ScoreComponent(100.0, True, {"reason": "code postal correspondant"})
    if any(department and department in loc for loc in offer_locations):
        return ScoreComponent(80.0, True, {"reason": "même département"})
    radius = profile.get("search_radius_km")
    if radius:
        return ScoreComponent(60.0, True, {"reason": "proximité déclarée sans géocodage"})
    return ScoreComponent(40.0, True, {"reason": "localisation partielle"})


def compute_contract_score(profile_contract: str | None, offer_contract: str | None) -> ScoreComponent:
    if not profile_contract or not offer_contract:
        return ScoreComponent(100.0, False, {"reason": "absence de préférence ou de contrat"})
    profile_norm = normalize_text(profile_contract)
    offer_norm = normalize_text(offer_contract)
    if profile_norm == offer_norm:
        return ScoreComponent(100.0, True, {"reason": "contrat identique"})
    return ScoreComponent(0.0, True, {"reason": "contrat différent", "profile": profile_contract, "offer": offer_contract})


def compute_remote_score(profile_remote: str | None, offer_remote: str | None) -> ScoreComponent:
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


def _profile_skill_list(profile_skills: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for item in profile_skills:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("nom") or ""
        normalized_name = item.get("normalized_name") or normalize_skill_name(name)
        normalized.append({**item, "name": name, "normalized_name": normalized_name})
    return normalized


def compute_match(profile: dict[str, Any], offer_raw: dict[str, Any]) -> dict[str, Any]:
    offer = normalize_offer_for_matching(offer_raw, source=offer_raw.get("source"))
    profile_skills = _profile_skill_list(profile.get("skills", []))
    profile_jobs = []
    for item in profile.get("desired_jobs", []):
        if isinstance(item, dict):
            title = item.get("job_title") or item.get("title")
        else:
            title = item
        if title:
            profile_jobs.append(title)
    profile_experience_titles = []
    for item in profile.get("experiences", []):
        if isinstance(item, dict):
            title = item.get("job_title") or item.get("poste")
        else:
            title = item
        if title:
            profile_experience_titles.append(title)
    profile_diplomas = profile.get("diplomas", [])
    skill_component = compute_skill_score(profile_skills, offer.get("competences", []))
    job_component = compute_job_score(profile_jobs, profile_experience_titles, offer.get("titre") or "")
    experience_component = compute_experience_score(profile.get("experiences", []), offer.get("experience_requise"))
    diploma_component = compute_diploma_score(profile_diplomas, offer.get("diplomes_requis", []))
    location_component = compute_location_score(profile, offer)
    contract_component = compute_contract_score(profile.get("contract_preference"), offer.get("contrat"))
    remote_component = compute_remote_score(profile.get("remote_preference"), offer.get("teletravail"))

    components = {
        "skill_score": skill_component,
        "job_score": job_component,
        "experience_score": experience_component,
        "diploma_score": diploma_component,
        "location_score": location_component,
        "contract_score": contract_component,
        "remote_score": remote_component,
    }
    numerator = 0.0
    denominator = 0.0
    for key, weight in WEIGHTS.items():
        component = components[key]
        if component.applicable:
            numerator += component.score * weight
            denominator += weight
    global_score = _scale(numerator / denominator if denominator else 0.0)
    matching_skills = skill_component.details.get("matching_skills", [])
    missing_skills = skill_component.details.get("missing_skills", [])
    explanation_parts = []
    if skill_component.applicable:
        explanation_parts.append(f"Vous possédez {len(matching_skills)} compétence(s) commune(s) sur {len(matching_skills) + len(missing_skills)} demandée(s).")
        if missing_skills:
            explanation_parts.append(f"Compétences manquantes: {', '.join(missing_skills[:5])}.")
    if job_component.applicable and job_component.score >= 50:
        explanation_parts.append("Votre expérience et vos métiers recherchés correspondent au poste.")
    if location_component.applicable:
        explanation_parts.append(f"Compatibilité localisation: {location_component.score:.0f}/100.")
    if contract_component.applicable:
        explanation_parts.append(f"Contrat: {contract_component.score:.0f}/100.")
    if remote_component.applicable:
        explanation_parts.append(f"Télétravail: {remote_component.score:.0f}/100.")
    explanation = {
        "summary": f"Cette offre correspond à {global_score:.0f}% à votre profil.",
        "details": explanation_parts,
        "matching_skills": matching_skills,
        "missing_skills": missing_skills,
        "subscores": {key: component.score for key, component in components.items()},
    }
    return {
        "offer_identifier": offer.get("id"),
        "offer": offer,
        "global_score": round(global_score, 2),
        "skill_score": round(skill_component.score, 2),
        "job_score": round(job_component.score, 2),
        "experience_score": round(experience_component.score, 2),
        "diploma_score": round(diploma_component.score, 2),
        "location_score": round(location_component.score, 2),
        "contract_score": round(contract_component.score, 2),
        "remote_score": round(remote_component.score, 2),
        "matching_skills": matching_skills,
        "missing_skills": missing_skills,
        "explanation": explanation,
    }
