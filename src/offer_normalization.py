# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Normalize offers from France Travail and Indeed into one common schema."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple


from src.offer_field_extractors import (
    extract_diplomas_from_text,
    extract_salary_from_text,
    extract_teletravail_from_text,
)


COMMON_KEYS = (
    "id_offre",
    "source",
    "date",
    "territoire",
    "metier",
    "niveau",
    "contrat",
    "competences",
    "titre",
    "entreprise",
    "description",
)

INDEED_FIELD_ALIASES = {
    "id_offre": ("id_offre", "id", "jobkey", "jobKey", "key", "job_id", "jobId"),
    "date": ("date", "posted_at", "published_at", "publication_date", "created_at"),
    "territoire": (
        "territoire",
        "location",
        "lieu",
        "place",
        "city",
        "localisation",
        "location_name",
    ),
    "metier": ("metier", "title", "job_title", "jobTitle", "intitule", "role", "occupation"),
    "niveau": ("niveau", "seniority", "experience_level", "experience", "level"),
    "contrat": (
        "contrat",
        "contract",
        "job_type",
        "employment_type",
        "typeContrat",
        "contract_type",
    ),
    "competences": (
        "competences",
        "skills",
        "tags",
        "keywords",
        "requirements",
        "qualifications",
    ),
    "titre": ("titre", "title", "job_title", "jobTitle", "intitule"),
    "entreprise": ("entreprise", "company", "employer", "organization", "organisation"),
    "description": ("description", "summary", "content", "snippet", "job_description"),
}


def normalize_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().lower()


def clean_label(value: object) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    compact = text.replace(" ", "")
    if len(compact) <= 4 and compact.replace("+", "").replace("#", "").replace(".", "").isalpha():
        return compact.upper()
    if any(ch.isupper() for ch in compact[1:]):
        return compact
    return " ".join(part if part.isupper() else part[:1].upper() + part[1:].lower() for part in text.split(" "))


def normalize_competence(value: object) -> str:
    text = normalize_text(value)
    text = text.replace("/", " ")
    text = re.sub(r"[^a-z0-9+#.-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_competence_display(value: object) -> str:
    return clean_label(value)


def split_multi_value(value: object) -> List[object]:
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
            parts = re.split(r"[;,|]", cleaned)
            return [part.strip() for part in parts if part.strip()]
        return [cleaned]
    return [value]


def parse_date(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    text = str(value).strip()
    if not text:
        return ""
    candidates = (text, text.replace("Z", ""), text.replace("/", "-"))
    for candidate in candidates:
        try:
            return datetime.fromisoformat(candidate).date().isoformat()
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return text


def _first_present(raw_offer: Dict[str, Any], aliases: Tuple[str, ...]) -> object:
    for key in aliases:
        if key in raw_offer and raw_offer.get(key) not in (None, ""):
            return raw_offer.get(key)
    return None


def _extract_territory_from_fr(raw_offer: Dict[str, Any]) -> str:
    lieu = raw_offer.get("lieuTravail") or {}
    if isinstance(lieu, dict):
        return (
            lieu.get("libelle")
            or lieu.get("commune")
            or lieu.get("codePostal")
            or raw_offer.get("intitule")
            or ""
        )
    return raw_offer.get("territoire") or raw_offer.get("intitule") or ""


def _extract_metier_from_fr(raw_offer: Dict[str, Any]) -> str:
    return raw_offer.get("romeLibelle") or raw_offer.get("appellationlibelle") or raw_offer.get("intitule") or ""


def _extract_contrat_from_fr(raw_offer: Dict[str, Any]) -> str:
    return raw_offer.get("typeContratLibelle") or raw_offer.get("typeContrat") or ""


def _extract_niveau_from_fr(raw_offer: Dict[str, Any]) -> str:
    experience = normalize_text(raw_offer.get("experienceLibelle") or raw_offer.get("experienceExige"))
    if any(token in experience for token in ("senior", "expert", "lead", "5 ans", "6 ans", "7 ans", "8 ans")):
        return "senior"
    if any(token in experience for token in ("junior", "debutant", "0 an", "1 an", "2 ans", "sans experience")):
        return "junior"
    if experience:
        return "intermediaire"
    return ""


def _extract_competences_from_fr(raw_offer: Dict[str, Any]) -> List[str]:
    competences: List[str] = []
    for key in ("competences", "competences_requises"):
        for item in raw_offer.get(key) or []:
            if isinstance(item, dict):
                label = item.get("libelle") or item.get("code") or item.get("name") or item.get("label")
            else:
                label = item
            if label is None:
                continue
            text = re.sub(r"\s+", " ", str(label)).strip()
            if text:
                competences.append(text)
    return competences


def _extract_experience_from_fr(raw_offer: Dict[str, Any]) -> Optional[str]:
    """Extrait le texte d'expérience depuis les données France Travail."""
    experience = raw_offer.get("experienceLibelle") or raw_offer.get("experienceExige")
    if experience:
        return str(experience).strip()
    return None


def _extract_salary_from_fr(raw_offer: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
    """Extrait le salaire depuis les données structurées France Travail."""
    salaire = raw_offer.get("salaire")
    if isinstance(salaire, dict):
        min_val = salaire.get("libelle") or salaire.get("code")
        if min_val:
            numbers = re.findall(r"\d+", str(min_val))
            if len(numbers) >= 2:
                return int(numbers[0]), int(numbers[1])
            if len(numbers) == 1:
                return int(numbers[0]), int(numbers[0])
    elif isinstance(salaire, str):
        numbers = re.findall(r"\d+", salaire)
        if len(numbers) >= 2:
            return int(numbers[0]), int(numbers[1])
        if len(numbers) == 1:
            return int(numbers[0]), int(numbers[0])
    return None, None


def _extract_teletravail_from_fr(raw_offer: Dict[str, Any]) -> Optional[str]:
    """Extrait le télétravail depuis les données structurées France Travail."""
    teletravail = raw_offer.get("teletravail") or raw_offer.get("distanciel")
    if teletravail:
        if isinstance(teletravail, dict):
            teletravail = teletravail.get("libelle") or teletravail.get("code")
        text = str(teletravail).lower()
        if any(t in text for t in ("oui", "possible", "partiel")):
            return "hybride"
        if any(t in text for t in ("complet", "total", "100%")):
            return "teletravail"
        if any(t in text for t in ("non", "pas de")):
            return "presentiel"
    return None


def _extract_diplomes_from_fr(raw_offer: Dict[str, Any]) -> List[str]:
    """Extrait les diplômes depuis les données structurées France Travail."""
    diplomes: List[str] = []
    for key in ("diplomes", "diplomes_requis", "formation"):
        items = raw_offer.get(key) or []
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    label = item.get("libelle") or item.get("code") or item.get("name")
                else:
                    label = item
                if label:
                    diplomes.append(str(label).strip())
        elif isinstance(items, str) and items.strip():
            diplomes.append(items.strip())
    return diplomes


def _extract_france_travail_location(raw_offer: Dict[str, Any]) -> Dict[str, str]:
    lieu = raw_offer.get("lieuTravail")
    if not isinstance(lieu, dict):
        lieu = {}
    territoire = (
        lieu.get("libelle")
        or raw_offer.get("territoire")
        or raw_offer.get("localisation")
        or raw_offer.get("location")
        or raw_offer.get("city")
        or ""
    )
    ville = (
        lieu.get("commune")
        or lieu.get("libelle")
        or raw_offer.get("ville")
        or raw_offer.get("city")
        or ""
    )
    code_postal = lieu.get("codePostal") or raw_offer.get("codePostal") or ""
    return {
        "territoire": str(territoire or ""),
        "ville": str(ville or ""),
        "code_postal": str(code_postal or ""),
    }


def _extract_france_travail_url(raw_offer: Dict[str, Any]) -> Optional[str]:
    origine = raw_offer.get("origineOffre")
    if isinstance(origine, dict):
        url = origine.get("urlOrigine")
        if url:
            return str(url)
    identifier = raw_offer.get("id") or raw_offer.get("id_offre") or raw_offer.get("idOffre") or raw_offer.get("idOfr")
    if identifier not in (None, ""):
        return f"https://candidat.francetravail.fr/offres/recherche/detail/{identifier}"
    return None


def normalize_france_travail_offer(raw_offer: Dict[str, Any]) -> Dict[str, Any]:
    location = _extract_france_travail_location(raw_offer)
    entreprise = raw_offer.get("entreprise")
    if isinstance(entreprise, dict):
        entreprise_name = entreprise.get("nom") or entreprise.get("name") or ""
    else:
        entreprise_name = entreprise or ""
    date_creation = parse_date(raw_offer.get("dateCreation") or raw_offer.get("dateActualisation") or raw_offer.get("date"))

    description = str(raw_offer.get("description") or "")

    salaire_min, salaire_max = _extract_salary_from_fr(raw_offer)
    if salaire_min is None and description:
        salary_data = extract_salary_from_text(description)
        if salary_data:
            salaire_min = salary_data.get("minimum")
            salaire_max = salary_data.get("maximum")

    teletravail = _extract_teletravail_from_fr(raw_offer)
    if teletravail is None and description:
        teletravail_data = extract_teletravail_from_text(description)
        if teletravail_data:
            teletravail = teletravail_data.get("mode")

    diplomes_requis = _extract_diplomes_from_fr(raw_offer)
    if not diplomes_requis and description:
        diploma_data = extract_diplomas_from_text(description)
        diplomes_requis = [d.get("label", "") for d in diploma_data if d.get("label")]

    experience_requise = _extract_experience_from_fr(raw_offer)

    return {
        "id": str(raw_offer.get("id") or raw_offer.get("id_offre") or raw_offer.get("idOffre") or raw_offer.get("idOfr") or ""),
        "intitule": str(raw_offer.get("intitule") or raw_offer.get("appellationlibelle") or raw_offer.get("romeLibelle") or ""),
        "entreprise": str(entreprise_name or ""),
        "territoire": location["territoire"],
        "ville": location["ville"],
        "code_postal": location["code_postal"],
        "contrat": str(raw_offer.get("typeContratLibelle") or raw_offer.get("typeContrat") or ""),
        "date_creation": date_creation,
        "date": date_creation,
        "url": _extract_france_travail_url(raw_offer),
        "description": description,
        "metier": _extract_metier_from_fr(raw_offer),
        "niveau": _extract_niveau_from_fr(raw_offer),
        "competences": _extract_competences_from_fr(raw_offer),
        "salaire_min": salaire_min,
        "salaire_max": salaire_max,
        "teletravail": teletravail,
        "diplomes_requis": diplomes_requis,
        "experience_requise": experience_requise,
    }


def _normalize_france_travail_common(raw_offer: Dict[str, Any]) -> Dict[str, Any]:
    normalized = normalize_france_travail_offer(raw_offer)
    return {
        "id_offre": normalized["id"],
        "source": "france_travail",
        "date": normalized["date_creation"],
        "territoire": normalized["territoire"] or normalized["ville"],
        "metier": normalized["metier"],
        "niveau": normalized["niveau"],
        "contrat": normalized["contrat"],
        "competences": normalized["competences"],
        "titre": normalized["intitule"],
        "entreprise": normalized["entreprise"],
        "description": normalized["description"],
        "salaire_min": normalized.get("salaire_min"),
        "salaire_max": normalized.get("salaire_max"),
        "teletravail": normalized.get("teletravail"),
        "diplomes_requis": normalized.get("diplomes_requis", []),
        "experience_requise": normalized.get("experience_requise"),
    }


def _normalize_competences_generic(value: object) -> List[str]:
    items: List[str] = []
    for item in split_multi_value(value):
        if isinstance(item, dict):
            label = item.get("libelle") or item.get("name") or item.get("label") or item.get("code")
        else:
            label = item
        if label is None:
            continue
        text = re.sub(r"\s+", " ", str(label)).strip()
        if text:
            items.append(text)
    return items


def _normalize_location_generic(raw_offer: Dict[str, Any]) -> str:
    value = _first_present(raw_offer, INDEED_FIELD_ALIASES["territoire"])
    if isinstance(value, dict):
        return (
            value.get("display_name")
            or value.get("name")
            or value.get("city")
            or value.get("locality")
            or value.get("label")
            or ""
        )
    return str(value or "")


def normalize_indeed_offer(raw_offer: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id_offre": _first_present(raw_offer, INDEED_FIELD_ALIASES["id_offre"]) or "",
        "source": "indeed",
        "date": parse_date(_first_present(raw_offer, INDEED_FIELD_ALIASES["date"])),
        "territoire": _normalize_location_generic(raw_offer),
        "metier": str(_first_present(raw_offer, INDEED_FIELD_ALIASES["metier"]) or ""),
        "niveau": normalize_text(_first_present(raw_offer, INDEED_FIELD_ALIASES["niveau"])),
        "contrat": str(_first_present(raw_offer, INDEED_FIELD_ALIASES["contrat"]) or ""),
        "competences": _normalize_competences_generic(_first_present(raw_offer, INDEED_FIELD_ALIASES["competences"])),
        "titre": str(_first_present(raw_offer, INDEED_FIELD_ALIASES["titre"]) or ""),
        "entreprise": str(_first_present(raw_offer, INDEED_FIELD_ALIASES["entreprise"]) or ""),
        "description": str(_first_present(raw_offer, INDEED_FIELD_ALIASES["description"]) or ""),
    }


def normalize_offer(raw_offer: Dict[str, Any], source: str) -> Dict[str, Any]:
    if source == "france_travail":
        return _normalize_france_travail_common(raw_offer)
    if source == "indeed":
        return normalize_indeed_offer(raw_offer)
    raise ValueError(f"Source non supportee: {source}")


def normalize_offers(raw_offers: List[Dict[str, Any]], source: str) -> List[Dict[str, Any]]:
    return [normalize_offer(offer, source) for offer in raw_offers if isinstance(offer, dict)]
