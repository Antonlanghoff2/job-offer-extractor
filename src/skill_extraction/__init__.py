# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Extraction hybride de compétences pour les offres d'emploi.

Ce package implémente un pipeline d'extraction en plusieurs niveaux :

1. **Extraction lexicale** — détection des compétences explicites.
2. **Extraction de candidats** — extraction d'expressions candidates.
3. **Rapprochement sémantique** — comparaison avec le référentiel.
4. **Extraction implicite** — déduction de compétences depuis les missions.
5. **Normalisation** — fusion des doublons et tri.

Le point d'entrée principal est la fonction
``extract_skills_from_offer`` du module ``skill_pipeline``.

Pour obtenir les compétences séparées par type d'extraction,
utiliser ``extract_skills_categorized``.
"""

from .implicit_extractor import ImplicitExtractionDebug, extract_implicit_skills
from .referential_loader import clear_referential_cache
from .models import ExtractedSkill
from .skill_pipeline import (
    extract_skills_as_dicts,
    extract_skills_categorized,
    extract_skill_names,
    extract_skills_from_offer,
)

__all__ = [
    "ExtractedSkill",
    "ImplicitExtractionDebug",
    "extract_implicit_skills",
    "clear_referential_cache",
    "extract_skills_from_offer",
    "extract_skills_as_dicts",
    "extract_skill_names",
    "extract_skills_categorized",
]
