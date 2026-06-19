# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Dataclasses for parsed CV output."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Formation:
    intitule: str
    etablissement: str | None = None
    niveau: str | None = None
    date_debut: str | None = None
    date_fin: str | None = None
    annee: int | None = None
    description: str | None = None
    texte_source: str = ""
    confiance: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "intitule": self.intitule,
            "etablissement": self.etablissement,
            "niveau": self.niveau,
            "date_debut": self.date_debut,
            "date_fin": self.date_fin,
            "annee": self.annee,
            "description": self.description,
            "texte_source": self.texte_source,
            "confiance": self.confiance,
        }


@dataclass
class Competence:
    nom: str
    categorie: str | None = None
    source: str = "explicite"
    texte_source: str = ""
    confiance: float = 0.0
    formation_source: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "nom": self.nom,
            "categorie": self.categorie,
            "source": self.source,
            "texte_source": self.texte_source,
            "confiance": self.confiance,
        }
        if self.formation_source:
            payload["formation_source"] = self.formation_source
        return payload


@dataclass
class ParsedCV:
    text: str
    structured: dict[str, Any]
    message: str | None = None
