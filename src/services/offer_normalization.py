# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Common offer normalization for matching and recommendation workflows."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from src.offer_normalization import normalize_text


def _as_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _first_value(raw_offer: Dict[str, Any], keys: Tuple[str, ...]) -> object:
    for key in keys:
        value = raw_offer.get(key)
        if value not in (None, ""):
            return value
    return None


def _collect_list_values(value: object) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    elif isinstance(value, tuple):
        items = list(value)
    else:
        items = [value]
    out: List[str] = []
    for item in items:
        if isinstance(item, dict):
            candidate = item.get("libelle") or item.get("label") or item.get("name") or item.get("title") or item.get("ville") or item.get("commune") or item.get("display_name")
        else:
            candidate = item
        text = _as_text(candidate)
        if text:
            out.append(text)
    return out


def _normalize_teletravail(value: object) -> Optional[str]:
    text = normalize_text(value)
    if not text:
        return None
    if any(token in text for token in ("teletravail complet", "full remote", "100% remote", "remote only")):
        return "teletravail"
    if any(token in text for token in ("hybride", "partial remote", "remote partiel")):
        return "hybride"
    if any(token in text for token in ("presentiel", "onsite", "sur site")):
        return "presentiel"
    return None


def _extract_salary(raw_offer: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
    values = []
    for key in ("salaire", "salary", "salaires", "salaire_min", "salaire_max"):
        value = raw_offer.get(key)
        if value not in (None, ""):
            values.append(str(value))
    blob = " ".join(values)
    numbers = [int(part.replace(" ", "")) for part in re.findall(r"\d[\d\s]{1,8}", blob) if part]
    if len(numbers) >= 2:
        return min(numbers), max(numbers)
    if len(numbers) == 1:
        return numbers[0], numbers[0]
    return None, None


def normalize_offer_for_matching(raw_offer: Dict[str, Any], *, source: Optional[str] = None) -> Dict[str, Any]:
    if not isinstance(raw_offer, dict):
        raise TypeError("raw_offer must be a dictionary")

    offer_id = _first_value(raw_offer, ("id", "id_offre", "idOffre", "idOfr", "numero_offre", "offer_id"))
    title = _first_value(raw_offer, ("titre", "intitule", "intitule_poste", "job_title", "title", "metier"))
    company = _first_value(raw_offer, ("entreprise", "company", "employer"))
    if isinstance(company, dict):
        company = company.get("nom") or company.get("name") or ""
    description = _first_value(raw_offer, ("description", "summary", "content", "snippet")) or ""
    competences = _collect_list_values(_first_value(raw_offer, ("competences", "competences_requises", "skills", "skillset", "mots_cles")))
    lieux = []
    lieux.extend(_collect_list_values(_first_value(raw_offer, ("lieux", "lieux_embauche", "locations"))))
    lieu_travail = raw_offer.get("lieuTravail")
    if isinstance(lieu_travail, dict):
        for key in ("libelle", "commune", "codePostal", "region", "departement"):
            if lieu_travail.get(key):
                lieux.append(str(lieu_travail.get(key)))
    if raw_offer.get("territoire"):
        lieux.append(str(raw_offer.get("territoire")))
    if raw_offer.get("ville"):
        lieux.append(str(raw_offer.get("ville")))
    if raw_offer.get("code_postal"):
        lieux.append(str(raw_offer.get("code_postal")))
    if raw_offer.get("location"):
        lieux.append(str(raw_offer.get("location")))
    source_name = source or raw_offer.get("source") or "France Travail"
    url_originale = _first_value(raw_offer, ("url_originale", "urlOrigine", "origin_url", "url"))
    if isinstance(url_originale, dict):
        url_originale = url_originale.get("urlOrigine") or url_originale.get("url")
    contract = _first_value(raw_offer, ("contrat", "typeContratLibelle", "typeContrat", "contract"))
    teletravail = _normalize_teletravail(_first_value(raw_offer, ("teletravail", "distanciel", "remote", "work_mode")))
    if teletravail is None and raw_offer.get("distanciel"):
        teletravail = _normalize_teletravail(raw_offer.get("distanciel"))
    salary_min, salary_max = _extract_salary(raw_offer)
    experience_requise = _first_value(raw_offer, ("experience_requise", "experienceLibelle", "experience", "seniority"))
    diplomes = _collect_list_values(_first_value(raw_offer, ("diplomes_requis", "diplomes", "degrees")))
    deduped_diplomes = [item for item in dict.fromkeys(_as_text(item) for item in diplomes if _as_text(item))]
    return {
        "id": _as_text(offer_id),
        "titre": _as_text(title),
        "entreprise": _as_text(company),
        "description": _as_text(description),
        "competences": [item for item in dict.fromkeys(_as_text(item) for item in competences if _as_text(item))],
        "lieux": [item for item in dict.fromkeys(_as_text(item) for item in lieux if _as_text(item))],
        "contrat": _as_text(contract) or None,
        "teletravail": teletravail,
        "salaire_min": salary_min,
        "salaire_max": salary_max,
        "experience_requise": _as_text(experience_requise) or None,
        "diplomes_requis": deduped_diplomes,
        "url_originale": _as_text(url_originale) or None,
        "source": _as_text(source_name) or "France Travail",
        "source_identifier": _as_text(offer_id),
    }
