# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Outils NER pour l'extraction, la normalisation et le regroupement des compétences.

Ce package fournit une implémentation légère, déterministe et extensible.
La première version repose sur un dictionnaire métier, des expressions
régulières et une similarité textuelle simple. Des moteurs plus lourds
(spaCy, CamemBERT, Sentence-BERT) pourront être branchés plus tard sans
changer les appels publics essentiels.
"""

from __future__ import annotations

from .skill_dictionary import SKILL_DICTIONARY
from .skill_entity_extractor import SkillEntity, extract_skill_entities, group_skill_entities
from .skill_normalizer import (
    canonicalize_skill_name,
    group_skill_variants,
    normalize_skill_name,
    normalize_skill_names,
)
from .skill_similarity import skill_similarity_score, should_merge_skills

__all__ = [
    "SKILL_DICTIONARY",
    "SkillEntity",
    "extract_skill_entities",
    "group_skill_entities",
    "canonicalize_skill_name",
    "group_skill_variants",
    "normalize_skill_name",
    "normalize_skill_names",
    "skill_similarity_score",
    "should_merge_skills",
]

