# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Matching helpers for configurable user weights and scoring."""

from .weights import DEFAULT_MATCHING_WEIGHTS, MATCHING_WEIGHT_KEYS, validate_matching_weights
from .scoring import calculate_weighted_score, build_scoring_result

__all__ = [
    "DEFAULT_MATCHING_WEIGHTS",
    "MATCHING_WEIGHT_KEYS",
    "validate_matching_weights",
    "calculate_weighted_score",
    "build_scoring_result",
]
