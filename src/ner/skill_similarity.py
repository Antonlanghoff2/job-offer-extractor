# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Fonctions simples de similarité entre compétences.

L'objectif est de fournir une base déterministe, sans dépendance lourde.
La similarité est volontairement conservatrice pour éviter les fusions
incorrectes comme ``Java`` avec ``JavaScript`` ou ``SQL`` avec ``NoSQL``.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Iterable, Set

from .skill_dictionary import normalize_skill_lookup


def _tokenize(value: object) -> Set[str]:
    text = normalize_skill_lookup(value)
    if not text:
        return set()
    return {token for token in re.split(r"\s+", text) if token}


def _is_forbidden_pair(left: str, right: str) -> bool:
    pair = {left, right}
    if pair == {"sql", "nosql"}:
        return True
    if pair == {"c", "c++"}:
        return True
    if pair == {"java", "javascript"}:
        return True
    return False


def skill_similarity_score(left: object, right: object) -> float:
    """Calcule une similarité textuelle entre deux compétences.

    Le score reste entre 0 et 1. La fonction ne fusionne pas les éléments
    manifestement différents : elle préfère laisser des compétences séparées
    plutôt que d'inventer une correspondance.
    """

    left_norm = normalize_skill_lookup(left)
    right_norm = normalize_skill_lookup(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0
    if _is_forbidden_pair(left_norm, right_norm):
        return 0.0
    if left_norm.startswith("no") and left_norm[2:] == right_norm:
        return 0.0
    if right_norm.startswith("no") and right_norm[2:] == left_norm:
        return 0.0

    left_tokens = _tokenize(left_norm)
    right_tokens = _tokenize(right_norm)
    if not left_tokens or not right_tokens:
        return SequenceMatcher(a=left_norm, b=right_norm).ratio()

    intersection = left_tokens & right_tokens
    union = left_tokens | right_tokens
    token_score = len(intersection) / float(len(union))
    sequence_score = SequenceMatcher(a=left_norm, b=right_norm).ratio()
    if intersection and min(len(token) for token in intersection) <= 2:
        token_score *= 0.8
    score = max(token_score, sequence_score)
    return round(score, 4)


def should_merge_skills(left: object, right: object, threshold: float = 0.82) -> bool:
    """Indique si deux compétences peuvent être fusionnées."""

    return skill_similarity_score(left, right) >= threshold

