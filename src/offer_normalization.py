# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Normalize offers from France Travail and Indeed into one common schema."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple


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
        "description": str(raw_offer.get("description") or ""),
        "metier": _extract_metier_from_fr(raw_offer),
        "niveau": _extract_niveau_from_fr(raw_offer),
        "competences": _extract_competences_from_fr(raw_offer),
    }


def _normalize_france_travail_common(raw_offer: Dict[str, Any]) -> Dict[str, Any]:
    normalized = normalize_france_travail_offer(raw_offer)
    return {
        "id_offre": normalized["id"],
        "source": "france_travail",
        "date": normalized["date_creation"],
        "territoire": normalized["territoire"] or normalized["ville"],
        "metier": _extract_metier_from_fr(raw_offer),
        "niveau": _extract_niveau_from_fr(raw_offer),
        "contrat": normalized["contrat"] or _extract_contrat_from_fr(raw_offer),
        "competences": _extract_competences_from_fr(raw_offer),
        "titre": normalized["intitule"],
        "entreprise": normalized["entreprise"],
        "description": normalized["description"],
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
