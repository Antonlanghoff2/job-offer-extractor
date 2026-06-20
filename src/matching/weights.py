# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Default matching weights and validation helpers."""

from __future__ import annotations

from typing import Dict, Iterable, Tuple


MATCHING_WEIGHT_KEYS = (
    "competences",
    "metier",
    "experience",
    "diplome",
    "localisation",
    "contrat",
    "teletravail",
)

DEFAULT_MATCHING_WEIGHTS = {
    "competences": 10.0,
    "metier": 15.0,
    "experience": 10.0,
    "diplome": 15.0,
    "localisation": 40.0,
    "contrat": 5.0,
    "teletravail": 5.0,
}

WEIGHT_SUM_TOLERANCE = 0.01


def _as_float(value: object) -> float:
    if isinstance(value, bool):
        raise ValueError("Les poids booléens sont interdits.")
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError("Chaque poids doit être numérique.")


def validate_matching_weights(weights: object) -> Tuple[Dict[str, float], str]:
    """Validate and normalize matching weights.

    Returns a tuple ``(normalized_weights, error_message)``.
    ``normalized_weights`` is empty when validation fails.
    """

    if not isinstance(weights, dict):
        return {}, "Les pondérations doivent être fournies sous forme de dictionnaire."

    unknown_keys = [key for key in weights.keys() if key not in MATCHING_WEIGHT_KEYS]
    if unknown_keys:
        return {}, "Clés de pondération inconnues: %s." % ", ".join(sorted(str(key) for key in unknown_keys))

    missing_keys = [key for key in MATCHING_WEIGHT_KEYS if key not in weights]
    if missing_keys:
        return {}, "Clés de pondération manquantes: %s." % ", ".join(missing_keys)

    normalized = {}
    total = 0.0
    for key in MATCHING_WEIGHT_KEYS:
        try:
            value = _as_float(weights.get(key))
        except ValueError as exc:
            return {}, str(exc)
        if value < 0.0 or value > 100.0:
            return {}, "Chaque poids doit être compris entre 0 et 100."
        normalized[key] = round(value, 2)
        total += value

    if abs(total - 100.0) > WEIGHT_SUM_TOLERANCE:
        return {}, "Le total des pondérations doit être égal à 100 %."

    return normalized, ""


def ensure_matching_weights(weights: object) -> Dict[str, float]:
    normalized, error = validate_matching_weights(weights)
    if error:
        return dict(DEFAULT_MATCHING_WEIGHTS)
    return normalized
