# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Aggregate normalized job-offer exports into market trend summaries."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.offer_normalization import normalize_text
from src.services.matching_service import normalize_skill_name

DATE_KEYS = (
    "date",
    "date_offre",
    "date_creation",
    "date_publication",
    "published_at",
    "created_at",
    "posted_at",
    "dateActualisation",
    "dateCreation",
)


def _normalize_display_name(value: object) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    if any(ch.isupper() for ch in text[1:]):
        return text
    if len(text) <= 4 and text.replace("+", "").replace("#", "").replace(".", "").isalpha():
        return text.upper()
    return " ".join(
        part if part.isupper() else part[:1].upper() + part[1:].lower()
        for part in text.split(" ")
    )


def _normalize_competence_key(value: object) -> str:
    canonical = normalize_skill_name(value)
    return normalize_text(canonical)


def _normalize_competence_display(value: object) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    compact = text.replace(" ", "")
    if compact.isupper():
        return compact
    if len(compact) <= 4 and compact.lower() in {"sql", "php", "aws", "api", "git", "html", "css", "json", "xml", "llm", "rag", "nlp", "etl", "ci", "cd"}:
        return compact.upper()
    return " ".join(
        part if part.isupper() else part[:1].upper() + part[1:].lower()
        for part in text.split(" ")
    )


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
        if any(sep in cleaned for sep in [",", ";", "|"]):
            parts = re.split(r"[;,|]", cleaned)
            return [part.strip() for part in parts if part.strip()]
        return [cleaned]
    return [value]


def _parse_date(value: object) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if not text:
        return None
    candidates = (text, text.replace("/", "-"), text.replace("Z", ""))
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


def _extract_offer_date(offer: Dict[str, Any]) -> Optional[date]:
    for key in DATE_KEYS:
        if key in offer:
            parsed = _parse_date(offer.get(key))
            if parsed is not None:
                return parsed
    return None


def _iter_text_values(value: object) -> Iterable[str]:
    if value is None:
        return
    if isinstance(value, dict):
        for key in ("libelle", "ville", "commune", "codePostal", "territoire", "location", "label", "name", "display_name"):
            if key in value:
                yield from _iter_text_values(value.get(key))
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _iter_text_values(item)
        return
    text = str(value).strip()
    if text:
        yield text


def _territoire_matches(offer: Dict[str, Any], territoire: str) -> bool:
    candidate = normalize_text(territoire)
    if not candidate:
        return False
    parts: List[str] = []
    for key in ("territoire", "ville", "lieu", "lieux_embauche", "code_postal", "codePostal"):
        parts.extend(_iter_text_values(offer.get(key)))
    lieu_travail = offer.get("lieuTravail")
    if isinstance(lieu_travail, dict):
        parts.extend(_iter_text_values(lieu_travail.get("libelle")))
        parts.extend(_iter_text_values(lieu_travail.get("commune")))
        parts.extend(_iter_text_values(lieu_travail.get("codePostal")))
    location_blob = normalize_text(" ".join(parts))
    if not location_blob:
        return False
    return candidate in location_blob or location_blob in candidate


def filter_offers_for_trends(
    offers: Sequence[Dict[str, Any]],
    territoire: Optional[str] = None,
    periode_jours: int = 30,
) -> List[Dict[str, Any]]:
    """Return offers restricted to the given territory and rolling window."""

    valid_offers = [offer for offer in offers if isinstance(offer, dict)]
    reference_dates = [d for d in (_extract_offer_date(offer) for offer in valid_offers) if d is not None]
    reference_date = max(reference_dates) if reference_dates else date.today()
    cutoff_date = reference_date - timedelta(days=max(periode_jours, 0))
    filtered: List[Dict[str, Any]] = []
    for offer in valid_offers:
        offer_date = _extract_offer_date(offer)
        if offer_date is not None and offer_date < cutoff_date:
            continue
        if territoire is not None and not _territoire_matches(offer, territoire):
            continue
        filtered.append(offer)
    return filtered


def _count_values(
    values: Iterable[object],
    key_normalizer,
    display_normalizer,
) -> Dict[str, int]:
    counts: Counter = Counter()
    display_names: Dict[str, str] = {}
    for raw in values:
        key = key_normalizer(raw)
        if not key:
            continue
        counts[key] += 1
        display_names.setdefault(key, display_normalizer(raw) or key)
    ordered = sorted(
        counts.items(),
        key=lambda item: (-item[1], display_names.get(item[0], item[0]).lower()),
    )
    return {display_names.get(key, key): count for key, count in ordered}


_NIVEAU_MAP = {
    "junior": "junior",
    "intermediaire": "intermediaire",
    "intermediate": "intermediaire",
    "senior": "senior",
}


def _normalize_niveau(value: object) -> str:
    text = normalize_text(value)
    text = text.replace("niveau ", "")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", "", text)
    if not text:
        return ""
    if text.startswith("inter"):
        return "intermediaire"
    if text.startswith("jun"):
        return "junior"
    if text.startswith("sen"):
        return "senior"
    return _NIVEAU_MAP.get(text, "")


def _extract_summary_offer(offer: Dict[str, Any]) -> Dict[str, Any]:
    id_value = (
        offer.get("id")
        or offer.get("id_offre")
        or offer.get("idOffre")
        or offer.get("idOfr")
        or ""
    )
    intitule = offer.get("intitule") or offer.get("titre") or offer.get("metier") or ""
    entreprise = offer.get("entreprise") or ""
    if isinstance(entreprise, dict):
        entreprise = entreprise.get("nom") or entreprise.get("name") or ""
    territoire = offer.get("territoire") or offer.get("ville") or offer.get("lieu") or ""
    if isinstance(territoire, dict):
        territoire = territoire.get("libelle") or territoire.get("display_name") or territoire.get("name") or ""
    date_value = offer.get("date") or offer.get("date_creation") or offer.get("dateCreation") or offer.get("dateActualisation") or ""
    if isinstance(date_value, (date, datetime)):
        date_value = date_value.date().isoformat() if isinstance(date_value, datetime) else date_value.isoformat()
    url = offer.get("url")
    if not url:
        origine = offer.get("origineOffre")
        if isinstance(origine, dict):
            url = origine.get("urlOrigine") or origine.get("url")
    if not url and id_value not in (None, ""):
        url = f"https://candidat.francetravail.fr/offres/recherche/detail/{id_value}"
    return {
        "id": str(id_value or ""),
        "intitule": str(intitule or ""),
        "entreprise": str(entreprise or ""),
        "territoire": str(territoire or ""),
        "contrat": str(offer.get("contrat") or offer.get("typeContratLibelle") or offer.get("typeContrat") or ""),
        "date": _parse_date(date_value).isoformat() if _parse_date(date_value) else str(date_value or ""),
        "url": str(url) if url else None,
    }


def _offer_competences(offer: Dict[str, Any]) -> List[str]:
    competences: List[str] = []
    for key in ("competences", "competences_requises", "skills", "skillset", "mots_cles"):
        for item in _split_values(offer.get(key)):
            if isinstance(item, dict):
                label = item.get("libelle") or item.get("code") or item.get("name") or item.get("label") or item.get("title")
            else:
                label = item
            text = re.sub(r"\s+", " ", str(label)).strip() if label is not None else ""
            if text:
                competences.append(text)
    normalized: List[str] = []
    seen = set()
    for item in competences:
        key = _normalize_competence_key(item)
        if not key or key in seen:
            continue
        seen.add(key)
        normalized.append(_normalize_competence_display(item) or key)
    return normalized


def _offer_metier(offer: Dict[str, Any]) -> List[str]:
    return [str(value) for value in _split_values(offer.get("metier") or offer.get("titre") or offer.get("intitule")) if str(value).strip()]


def _offer_niveaux(offer: Dict[str, Any]) -> List[str]:
    return [str(value) for value in _split_values(offer.get("niveau")) if str(value).strip()]


def _offer_contrats(offer: Dict[str, Any]) -> List[str]:
    return [str(value) for value in _split_values(offer.get("contrat") or offer.get("typeContratLibelle") or offer.get("typeContrat")) if str(value).strip()]


def aggregate_trends(
    offers: List[Dict[str, Any]],
    territoire: Optional[str] = None,
    periode_jours: int = 30,
) -> Dict[str, Any]:
    """Aggregate extracted offers into market trends for model 2."""

    valid_offers = [offer for offer in offers if isinstance(offer, dict)]
    filtered = filter_offers_for_trends(valid_offers, territoire=territoire, periode_jours=periode_jours)

    competences_raw: List[object] = []
    metiers_raw: List[object] = []
    niveaux_raw: List[object] = []
    contrats_raw: List[object] = []
    skill_sets: List[List[str]] = []
    skill_counter: Counter = Counter()
    skill_display_names: Dict[str, str] = {}
    cooccurrences: Counter = Counter()

    for offer in filtered:
        skills = []
        for skill in _offer_competences(offer):
            key = _normalize_competence_key(skill)
            if not key or key in skills:
                continue
            skills.append(key)
            skill_counter[key] += 1
            skill_display_names.setdefault(key, _normalize_competence_display(skill) or key)
        if skills:
            skill_sets.append(skills)
        competences_raw.extend(skill_display_names.get(key, key) for key in skills)
        metiers_raw.extend(_offer_metier(offer))
        niveaux_raw.extend(_offer_niveaux(offer))
        contrats_raw.extend(_offer_contrats(offer))
        if len(skills) >= 2:
            ordered = sorted(set(skills))
            for index, skill_a in enumerate(ordered):
                for skill_b in ordered[index + 1:]:
                    cooccurrences[(skill_a, skill_b)] += 1

    niveau_counts: Counter = Counter()
    for raw in niveaux_raw:
        key = _normalize_niveau(raw)
        if key:
            niveau_counts[key] += 1

    offers_summary = [_extract_summary_offer(offer) for offer in filtered]
    offers_summary.sort(key=lambda item: item.get("date") or "", reverse=True)

    competence_items = []
    for key, count in sorted(skill_counter.items(), key=lambda item: (-item[1], skill_display_names.get(item[0], item[0]).lower())):
        percentage = round((count / len(filtered)) * 100.0, 1) if filtered else 0.0
        competence_items.append({
            "nom": skill_display_names.get(key, key),
            "count": count,
            "percentage": percentage,
        })

    cooccurrence_items = []
    for (skill_a, skill_b), count in sorted(cooccurrences.items(), key=lambda item: (-item[1], skill_display_names.get(item[0][0], item[0][0]).lower(), skill_display_names.get(item[0][1], item[0][1]).lower())):
        cooccurrence_items.append({
            "competence_a": skill_display_names.get(skill_a, skill_a),
            "competence_b": skill_display_names.get(skill_b, skill_b),
            "count": count,
            "percentage": round((count / len(filtered)) * 100.0, 1) if filtered else 0.0,
        })

    result = {
        "territoire": territoire,
        "periode_jours": periode_jours,
        "nombre_offres": len(filtered),
        "competences": _count_values(competences_raw, _normalize_competence_key, _normalize_competence_display),
        "competences_details": competence_items,
        "metiers": _count_values(metiers_raw, normalize_text, _normalize_display_name),
        "niveau": {
            key: niveau_counts[key]
            for key in ("junior", "intermediaire", "senior")
            if niveau_counts.get(key)
        },
        "contrats": _count_values(contrats_raw, normalize_text, _normalize_display_name),
        "cooccurrences": cooccurrence_items,
        "fiabilite": round(min(1.0, len(filtered) / 40.0) if filtered else 0.0, 3),
        "skill_sets": skill_sets,
        "offres": offers_summary,
        "offers": offers_summary,
    }
    return result


def load_offers_json(path: Union[str, Path]) -> List[Dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, list):
        raise ValueError("Le fichier JSON d'entree doit contenir une liste d'offres.")
    return [offer for offer in payload if isinstance(offer, dict)]


def dump_trends_json(trends: Dict[str, Any], output_path: Union[str, Path]) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(trends, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Aggregate extracted job offers into market trends.")
    parser.add_argument("--input", required=True, help="Path to a JSON file containing extracted offers.")
    parser.add_argument("--territoire", default=None, help="Optional territory filter.")
    parser.add_argument("--periode", type=int, default=30, help="Rolling window in days.")
    parser.add_argument("--output", required=True, help="Output JSON path.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    offers = load_offers_json(args.input)
    trends = aggregate_trends(offers, territoire=args.territoire, periode_jours=args.periode)
    dump_trends_json(trends, args.output)

    territoire_label = args.territoire or "(tous territoires)"
    print(f"Offres chargees: {len(offers)}")
    print(f"Offres retenues: {trends['nombre_offres']}")
    print(f"Territoire: {territoire_label}")
    print(f"Periode: {trends['periode_jours']} jours")
    top_competences = list(trends["competences"].items())[:5]
    top_metiers = list(trends["metiers"].items())[:5]
    if top_competences:
        print("Top competences: " + ", ".join(f"{name} ({count})" for name, count in top_competences))
    if top_metiers:
        print("Top metiers: " + ", ".join(f"{name} ({count})" for name, count in top_metiers))


if __name__ == "__main__":
    main()
