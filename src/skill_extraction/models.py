# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Modèles de données pour l'extraction hybride de compétences.

Ce module définit la structure typée ``ExtractedSkill`` utilisée par
l'ensemble du pipeline d'extraction. Chaque compétence extraite conserve
sa source, son type d'extraction et son score de confiance pour garantir
l'explicabilité du résultat.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


EXTRACTION_TYPES = ("explicit", "semantic", "implicit")


@dataclass
class ExtractedSkill:
    """Représente une compétence extraite d'une offre d'emploi.

    Attributs
    ---------
    canonical_name : str
        Nom canonique de la compétence dans le référentiel.
    raw_text : str
        Texte brut tel qu'il apparaît dans l'offre.
    source_sentence : str
        Phrase complète d'où la compétence a été extraite.
    extraction_type : str
        Type d'extraction : ``explicit``, ``semantic`` ou ``implicit``.
    confidence : float
        Score de confiance entre 0.0 et 1.0.
    category : str or None
        Catégorie métier de la compétence.
    optional : bool
        Indique si la compétence est souhaitée mais non requise.
    negated : bool
        Indique si la compétence apparaît dans un contexte de négation.
    reason : str or None
        Justification de l'extraction (principalement pour les compétences implicites).
    """

    canonical_name: str
    raw_text: str
    source_sentence: str
    extraction_type: str = "explicit"
    confidence: float = 1.0
    category: Optional[str] = None
    optional: bool = False
    negated: bool = False
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Sérialise la compétence en dictionnaire JSON-compatible."""

        return {
            "canonical_name": self.canonical_name,
            "raw_text": self.raw_text,
            "source_sentence": self.source_sentence,
            "extraction_type": self.extraction_type,
            "confidence": self.confidence,
            "category": self.category,
            "optional": self.optional,
            "negated": self.negated,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExtractedSkill":
        """Construit une instance à partir d'un dictionnaire."""

        return cls(
            canonical_name=data.get("canonical_name", ""),
            raw_text=data.get("raw_text", ""),
            source_sentence=data.get("source_sentence", ""),
            extraction_type=data.get("extraction_type", "explicit"),
            confidence=float(data.get("confidence", 1.0)),
            category=data.get("category"),
            optional=bool(data.get("optional", False)),
            negated=bool(data.get("negated", False)),
            reason=data.get("reason"),
        )
