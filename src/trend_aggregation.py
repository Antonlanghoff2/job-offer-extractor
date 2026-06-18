# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Aggregate normalized job-offer exports into market trend summaries."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from src.offer_normalization import normalize_text

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
    text = normalize_text(value)
    text = text.replace("/", " ")
    text = re.sub(r"[^a-z0-9+#.-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_competence_display(value: object) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    compact = text.replace(" ", "")
    if len(compact) <= 4 and compact.replace("+", "").replace("#", "").replace(".", "").isalpha():
        return compact.upper()
    if any(ch.isupper() for ch in compact[1:]):
        return compact
    return " ".join(
        part if part.isupper() else part[:1].upper() + part[1:].lower()
        for part in text.split(" ")
    )


def _split_values(value: object) -> list[object]:
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


def _parse_date(value: object) -> date | None:
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


def _extract_offer_date(offer: dict[str, Any]) -> date | None:
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


def _territoire_matches(offer: dict[str, Any], territoire: str) -> bool:
    candidate = normalize_text(territoire)
    if not candidate:
        return False
    parts: list[str] = []
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


def _count_values(
    values: Iterable[object],
    key_normalizer,
    display_normalizer,
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    display_names: dict[str, str] = {}
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


_def_niveau_map = {
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
    return _def_niveau_map.get(text, "")


def _extract_summary_offer(offer: dict[str, Any]) -> dict[str, Any]:
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


def aggregate_trends(
    offers: list[dict],
    territoire: str | None = None,
    periode_jours: int = 30,
) -> dict:
    """Aggregate extracted offers into market trends for model 2."""
    valid_offers: list[dict[str, Any]] = [offer for offer in offers if isinstance(offer, dict)]

    reference_dates = [d for d in (_extract_offer_date(offer) for offer in valid_offers) if d is not None]
    reference_date = max(reference_dates) if reference_dates else date.today()
    cutoff_date = date.fromordinal(reference_date.toordinal() - max(periode_jours, 0))

    filtered: list[dict[str, Any]] = []
    for offer in valid_offers:
        offer_date = _extract_offer_date(offer)
        if offer_date is not None and offer_date < cutoff_date:
            continue
        if territoire is not None and not _territoire_matches(offer, territoire):
            continue
        filtered.append(offer)

    competences_raw: list[object] = []
    metiers_raw: list[object] = []
    niveaux_raw: list[object] = []
    contrats_raw: list[object] = []

    for offer in filtered:
        competences = []
        for item in _split_values(offer.get("competences")):
            norm = _normalize_competence_key(item)
            if norm and norm not in competences:
                competences.append(item)
        competences_raw.extend(competences)
        metiers_raw.extend(_split_values(offer.get("metier") or offer.get("titre") or offer.get("intitule")))
        niveaux_raw.extend(_split_values(offer.get("niveau")))
        contrats_raw.extend(_split_values(offer.get("contrat") or offer.get("typeContratLibelle") or offer.get("typeContrat")))

    niveau_counts: Counter[str] = Counter()
    for raw in niveaux_raw:
        key = _normalize_niveau(raw)
        if key:
            niveau_counts[key] += 1

    offres = [_extract_summary_offer(offer) for offer in filtered]
    offres.sort(key=lambda item: item.get("date") or "", reverse=True)

    result = {
        "territoire": territoire,
        "periode_jours": periode_jours,
        "nombre_offres": len(filtered),
        "competences": _count_values(
            competences_raw,
            _normalize_competence_key,
            _normalize_competence_display,
        ),
        "metiers": _count_values(metiers_raw, normalize_text, _normalize_display_name),
        "niveau": {
            key: niveau_counts[key]
            for key in ("junior", "intermediaire", "senior")
            if niveau_counts.get(key)
        },
        "contrats": _count_values(contrats_raw, normalize_text, _normalize_display_name),
        "offres": offres,
        "offers": offres,
    }
    return result


def load_offers_json(path: str | Path) -> list[dict]:
    with Path(path).open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, list):
        raise ValueError("Le fichier JSON d'entree doit contenir une liste d'offres.")
    return [offer for offer in payload if isinstance(offer, dict)]


def dump_trends_json(trends: dict, output_path: str | Path) -> None:
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
