# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Extraction des compétences explicites, contextuelles et déduites.

Le module reste volontairement léger : il s'appuie sur le dictionnaire NER
centralisé du projet, puis produit des structures compatibles avec le parseur
CV existant.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from src.ner.skill_dictionary import SKILL_DICTIONARY
from src.ner.skill_entity_extractor import extract_skill_entities
from src.ner.skill_normalizer import canonicalize_skill_name

from .confidence import skill_confidence
from .normalizer import collapse_spaces, normalize_text


@dataclass
class SkillMatch:
    nom: str
    categorie: Optional[str]
    source: str
    texte_source: str
    confiance: float
    formation_source: Optional[str] = None

    def as_dict(self) -> Dict[str, object]:
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


SKILL_CATALOG: Dict[str, Dict[str, object]] = {
    canonical: {
        "aliases": set(spec.get("aliases") or []) | {canonical},
        "category": spec.get("category"),
    }
    for canonical, spec in SKILL_DICTIONARY.items()
}

EXP_SPLIT_RE = re.compile(r"[,;/•|]")


def _looks_like_skill_entry(line: str) -> bool:
    cleaned = collapse_spaces(line)
    if not cleaned:
        return False
    normalized = normalize_text(cleaned)
    if re.search(r"(?:19|20)\d{2}", normalized):
        return False
    if re.search(r"(?:diplome|diplôme|formation|etudes|études|experience|expérience|profil|contact|coordonnees|coordonnées|loisirs|interets|intérêts|universite|université|ecole|école|institut|lycee|lycée|openclassrooms|telecom|télécom|ina|cnam)", normalized):
        return False
    return bool(re.search(r"[,;/•|]", cleaned) or extract_skill_entities(cleaned))


def normalize_skill_name(name: object) -> str:
    """Retourne le nom canonique d'une compétence."""

    return canonicalize_skill_name(name)


def _skill_category(name: str) -> Optional[str]:
    spec = SKILL_CATALOG.get(name)
    if not spec:
        return None
    category = spec.get("category")
    return str(category) if category else None


def _tokenize_explicit_line(line: str) -> List[str]:
    parts = [collapse_spaces(part) for part in EXP_SPLIT_RE.split(line)]
    values = [part.strip(" -–—") for part in parts if part and part.strip(" -–—")]
    return values or [line]


def _merge_unique(matches: Iterable[SkillMatch]) -> List[SkillMatch]:
    ranking = {"explicite": 3, "experience_professionnelle": 2, "deduite_de_formation": 1}
    ordered: OrderedDict[str, SkillMatch] = OrderedDict()
    for item in matches:
        key = normalize_text(item.nom)
        existing = ordered.get(key)
        if existing is None:
            ordered[key] = item
            continue
        if ranking.get(item.source, 0) > ranking.get(existing.source, 0) or item.confiance > existing.confiance:
            ordered[key] = item
    return list(ordered.values())


def extract_explicit_skills(lines: Iterable[str]) -> List[SkillMatch]:
    matches: List[SkillMatch] = []
    for line in lines:
        if not _looks_like_skill_entry(line):
            continue
        entities = extract_skill_entities(line, source="explicite")
        if entities:
            for entity in entities:
                matches.append(
                    SkillMatch(
                        nom=entity.canonical_name,
                        categorie=entity.category,
                        source="explicite",
                        texte_source=collapse_spaces(line),
                        confiance=skill_confidence("explicite", explicit=True),
                    )
                )
            continue
        for part in _tokenize_explicit_line(line):
            name = normalize_skill_name(part)
            if not name or normalize_text(name) not in {normalize_text(skill) for skill in SKILL_CATALOG}:
                continue
            matches.append(
                SkillMatch(
                    nom=name,
                    categorie=_skill_category(name),
                    source="explicite",
                    texte_source=collapse_spaces(line),
                    confiance=skill_confidence("explicite", explicit=True),
                )
            )
    return _merge_unique(matches)


def extract_skills_from_text(text: str, *, source: str, formation_source: Optional[str] = None) -> List[SkillMatch]:
    matches: List[SkillMatch] = []
    for entity in extract_skill_entities(text, source=source):
        matches.append(
            SkillMatch(
                nom=entity.canonical_name,
                categorie=entity.category,
                source=source,
                texte_source=collapse_spaces(text),
                confiance=skill_confidence(source),
                formation_source=formation_source,
            )
        )
    return _merge_unique(matches)


def merge_skill_matches(*groups: Iterable[SkillMatch]) -> List[SkillMatch]:
    all_matches: List[SkillMatch] = []
    for group in groups:
        all_matches.extend(group)
    return _merge_unique(all_matches)
