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

DATE_KEYS = (
    "date",
    "date_offre",
    "date_publication",
    "published_at",
    "created_at",
    "posted_at",
)


def _normalize_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


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
    text = _normalize_text(value)
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
    candidates = (text, text.replace("/", "-"))
    for candidate in candidates:
        try:
            return datetime.fromisoformat(candidate).date()
        except ValueError:
            pass
    try:
        return datetime.strptime(text, "%d/%m/%Y").date()
    except ValueError:
        return None


def _extract_offer_date(offer: dict[str, Any]) -> date | None:
    for key in DATE_KEYS:
        if key in offer:
            parsed = _parse_date(offer.get(key))
            if parsed is not None:
                return parsed
    return None


def _territoire_matches(offer: dict[str, Any], territoire: str) -> bool:
    candidate = _normalize_text(offer.get("territoire"))
    target = _normalize_text(territoire)
    if not candidate or not target:
        return False
    return target == candidate or target in candidate or candidate in target


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


def _normalize_niveau(value: object) -> str:
    text = _normalize_text(value)
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
    if text in {"junior", "intermediaire", "senior"}:
        return text
    return ""


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
        metiers_raw.extend(_split_values(offer.get("metier")))
        niveaux_raw.extend(_split_values(offer.get("niveau")))
        contrats_raw.extend(_split_values(offer.get("contrat")))

    niveau_counts: Counter[str] = Counter()
    for raw in niveaux_raw:
        key = _normalize_niveau(raw)
        if key:
            niveau_counts[key] += 1

    result = {
        "territoire": territoire,
        "periode_jours": periode_jours,
        "nombre_offres": len(filtered),
        "competences": _count_values(
            competences_raw,
            _normalize_competence_key,
            _normalize_competence_display,
        ),
        "metiers": _count_values(metiers_raw, _normalize_text, _normalize_display_name),
        "niveau": {
            key: niveau_counts[key]
            for key in ("junior", "intermediaire", "senior")
            if niveau_counts.get(key)
        },
        "contrats": _count_values(contrats_raw, _normalize_text, _normalize_display_name),
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
