# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Compare normalized France Travail and Indeed offer datasets."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import json

from src.offer_normalization import normalize_offers, normalize_text
from src.trend_aggregation import aggregate_trends


def _load_json_list(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, list):
        raise ValueError(f"Le fichier {path} doit contenir une liste JSON.")
    return [item for item in payload if isinstance(item, dict)]


def _top_overlap(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
    overlap: dict[str, int] = {}
    left_keys = {normalize_text(key): key for key in left}
    right_keys = {normalize_text(key): key for key in right}
    common = sorted(set(left_keys) & set(right_keys))
    for norm_key in common:
        key = left_keys[norm_key]
        overlap[key] = min(left[key], right[right_keys[norm_key]])
    return dict(sorted(overlap.items(), key=lambda item: (-item[1], item[0].lower())))


def _exclusive_counts(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
    right_norm = {normalize_text(key) for key in right}
    return dict(
        sorted(
            ((key, value) for key, value in left.items() if normalize_text(key) not in right_norm),
            key=lambda item: (-item[1], item[0].lower()),
        )
    )


def compare_sources(
    france_travail_offers: list[dict[str, Any]],
    indeed_offers: list[dict[str, Any]],
    territoire: str | None = None,
    periode_jours: int = 30,
) -> dict[str, Any]:
    """Compare France Travail and Indeed after normalizing both sources."""
    ft_normalized = normalize_offers(france_travail_offers, "france_travail")
    indeed_normalized = normalize_offers(indeed_offers, "indeed")

    ft_trends = aggregate_trends(ft_normalized, territoire=territoire, periode_jours=periode_jours)
    indeed_trends = aggregate_trends(indeed_normalized, territoire=territoire, periode_jours=periode_jours)

    return {
        "territoire": territoire,
        "periode_jours": periode_jours,
        "france_travail": ft_trends,
        "indeed": indeed_trends,
        "comparaison": {
            "ecart_nombre_offres": ft_trends["nombre_offres"] - indeed_trends["nombre_offres"],
            "competences_communes": _top_overlap(ft_trends.get("competences", {}), indeed_trends.get("competences", {})),
            "competences_fr_exclusives": _exclusive_counts(ft_trends.get("competences", {}), indeed_trends.get("competences", {})),
            "competences_indeed_exclusives": _exclusive_counts(indeed_trends.get("competences", {}), ft_trends.get("competences", {})),
            "metiers_communs": _top_overlap(ft_trends.get("metiers", {}), indeed_trends.get("metiers", {})),
            "contrats_communs": _top_overlap(ft_trends.get("contrats", {}), indeed_trends.get("contrats", {})),
            "niveau_fr": ft_trends.get("niveau", {}),
            "niveau_indeed": indeed_trends.get("niveau", {}),
        },
    }


def compare_from_files(
    france_travail_path: str | Path,
    indeed_path: str | Path,
    territoire: str | None = None,
    periode_jours: int = 30,
) -> dict[str, Any]:
    ft_raw = _load_json_list(france_travail_path)
    indeed_raw = _load_json_list(indeed_path)
    return compare_sources(ft_raw, indeed_raw, territoire=territoire, periode_jours=periode_jours)
