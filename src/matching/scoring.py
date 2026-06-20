# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Weighted matching score helpers."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .weights import DEFAULT_MATCHING_WEIGHTS, MATCHING_WEIGHT_KEYS, ensure_matching_weights


def _bounded_score(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return max(0.0, min(1.0, float(value)))


def calculate_weighted_score(criterion_scores: Dict[str, Optional[float]], weights: Dict[str, float]) -> float:
    """Return a weighted score between 0 and 100.

    ``None`` means the criterion is absent and must be excluded from the
    denominator. ``0.0`` means the criterion exists but is incompatible.
    """

    active_weight_total = 0.0
    weighted_score = 0.0
    for key in MATCHING_WEIGHT_KEYS:
        score = criterion_scores.get(key)
        if score is None:
            continue
        weight = float(weights.get(key, 0.0))
        active_weight_total += weight
        weighted_score += max(0.0, min(1.0, float(score))) * weight
    if active_weight_total <= 0.0:
        return 0.0
    return round((weighted_score / active_weight_total) * 100.0, 2)


def _classify_status(score: Optional[float]) -> str:
    return "champ_absent" if score is None else "evalue"


def build_scoring_result(
    criterion_scores: Dict[str, Optional[float]],
    weights: Optional[Dict[str, float]] = None,
    common_skills: Optional[List[str]] = None,
    missing_skills: Optional[List[str]] = None,
    source: str = "",
    url_originale: str = "",
) -> Dict[str, Any]:
    normalized_weights = ensure_matching_weights(weights or DEFAULT_MATCHING_WEIGHTS)
    score_global = calculate_weighted_score(criterion_scores, normalized_weights)
    active_weight_total = sum(
        normalized_weights[key]
        for key in MATCHING_WEIGHT_KEYS
        if criterion_scores.get(key) is not None
    )
    sous_scores: Dict[str, Dict[str, Any]] = {}
    for key in MATCHING_WEIGHT_KEYS:
        score = criterion_scores.get(key)
        initial = float(normalized_weights.get(key, 0.0))
        effective = 0.0 if score is None or active_weight_total <= 0.0 else round(initial / active_weight_total * 100.0, 2)
        sous_scores[key] = {
            "score": None if score is None else round(max(0.0, min(1.0, float(score))) * 100.0, 2),
            "poids_initial": initial,
            "poids_effectif": effective,
            "statut": _classify_status(score),
        }
    return {
        "score_global": score_global,
        "sous_scores": sous_scores,
        "competences_communes": list(common_skills or []),
        "competences_manquantes": list(missing_skills or []),
        "source": source,
        "url_originale": url_originale,
    }
