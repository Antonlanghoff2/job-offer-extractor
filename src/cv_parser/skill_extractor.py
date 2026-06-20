# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Skill extraction for explicit, experiential and educational contexts."""

from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

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
    "Python": {"aliases": {"python"}, "category": "langage"},
    "PyTorch": {"aliases": {"pytorch"}, "category": "framework_ml"},
    "TensorFlow": {"aliases": {"tensorflow"}, "category": "framework_ml"},
    "scikit-learn": {"aliases": {"scikit learn", "sklearn", "scikit-learn"}, "category": "library_ml"},
    "Pandas": {"aliases": {"pandas"}, "category": "data"},
    "NumPy": {"aliases": {"numpy"}, "category": "data"},
    "SQL": {"aliases": {"sql"}, "category": "data"},
    "PostgreSQL": {"aliases": {"postgresql", "postgres"}, "category": "database"},
    "FastAPI": {"aliases": {"fastapi"}, "category": "backend"},
    "Flask": {"aliases": {"flask"}, "category": "backend"},
    "Django": {"aliases": {"django"}, "category": "backend"},
    "PHP": {"aliases": {"php"}, "category": "langage"},
    "Symfony": {"aliases": {"symfony"}, "category": "framework"},
    "Doctrine": {"aliases": {"doctrine"}, "category": "framework"},
    "JavaScript": {"aliases": {"javascript", "js", "ecmascript"}, "category": "frontend"},
    "TypeScript": {"aliases": {"typescript", "ts"}, "category": "frontend"},
    "React": {"aliases": {"react", "reactjs"}, "category": "frontend"},
    "Vue.js": {"aliases": {"vue js", "vue.js", "vuejs", "vue"}, "category": "frontend"},
    "C++": {"aliases": {"c++", "cpp", "c plus plus"}, "category": "langage"},
    "Qt": {"aliases": {"qt"}, "category": "framework"},
    "CMake": {"aliases": {"cmake"}, "category": "build"},
    "Git": {"aliases": {"git"}, "category": "versioning"},
    "GitHub": {"aliases": {"github"}, "category": "versioning"},
    "Docker": {"aliases": {"docker"}, "category": "devops"},
    "Kubernetes": {"aliases": {"kubernetes", "k8s"}, "category": "devops"},
    "Linux": {"aliases": {"linux"}, "category": "system"},
    "AWS": {"aliases": {"aws", "amazon web services"}, "category": "cloud"},
    "Azure": {"aliases": {"azure"}, "category": "cloud"},
    "Terraform": {"aliases": {"terraform"}, "category": "devops"},
    "Ansible": {"aliases": {"ansible"}, "category": "devops"},
    "Machine Learning": {"aliases": {"machine learning", "ml"}, "category": "ia"},
    "Deep Learning": {"aliases": {"deep learning", "dl"}, "category": "ia"},
    "NLP": {"aliases": {"nlp", "traitement du langage naturel"}, "category": "ia"},
    "RAG": {"aliases": {"rag"}, "category": "ia"},
    "LLM": {"aliases": {"llm", "large language model", "large language models"}, "category": "ia"},
    "MLOps": {"aliases": {"mlops"}, "category": "ia"},
    "REST API": {"aliases": {"rest api", "api rest", "rest"}, "category": "backend"},
    "OSC": {"aliases": {"osc"}, "category": "multimedia"},
    "MIDI": {"aliases": {"midi"}, "category": "multimedia"},
    "DMX": {"aliases": {"dmx"}, "category": "multimedia"},
    "ArtNet": {"aliases": {"artnet"}, "category": "multimedia"},
    "FFmpeg": {"aliases": {"ffmpeg"}, "category": "multimedia"},
    "OpenGL": {"aliases": {"opengl"}, "category": "multimedia"},
    "Réseaux": {"aliases": {"reseaux", "réseaux", "networking"}, "category": "network"},
    "Électronique": {"aliases": {"electronique", "électronique"}, "category": "hardware"},
    "Sonorisation": {"aliases": {"sonorisation"}, "category": "multimedia"},
    "Éclairage scénique": {"aliases": {"eclairage scenique", "éclairage scénique"}, "category": "multimedia"},
    "Vidéo": {"aliases": {"video", "vidéo"}, "category": "multimedia"},
    "Gestion de projet": {"aliases": {"gestion de projet", "gestion projets", "project management", "méthode agile", "methodologie agile", "agile"}, "category": "management"},
    "Audio numérique": {"aliases": {"audio numerique", "audio numérique"}, "category": "multimedia"},
    "Régie son": {"aliases": {"regie son", "régie son"}, "category": "multimedia"},
    "Régie lumière": {"aliases": {"regie lumiere", "régie lumière", "régie lumiere"}, "category": "multimedia"},
    "Régie vidéo": {"aliases": {"regie video", "régie vidéo"}, "category": "multimedia"},
    "Gestion de projet numérique": {"aliases": {"gestion de projet numerique", "gestion de projet numérique"}, "category": "management"},
    "Conception de projet numérique": {"aliases": {"conception de projet numérique", "conception de projet numerique"}, "category": "management"},
}

ALIAS_TO_CANONICAL: Dict[str, str] = {}
for canonical, spec in SKILL_CATALOG.items():
    for alias in spec["aliases"]:  # type: ignore[index]
        ALIAS_TO_CANONICAL[normalize_text(alias)] = canonical

ALIAS_REGEX = sorted(ALIAS_TO_CANONICAL.keys(), key=len, reverse=True)
EXP_SPLIT_RE = re.compile(r"[,;/•|]")


def _looks_like_skill_entry(line: str) -> bool:
    cleaned = collapse_spaces(line)
    if not cleaned:
        return False
    normalized = normalize_text(cleaned)
    if re.search(r"\b(?:19|20)\d{2}\b", normalized):
        return False
    if re.search(r"\b(?:diplome|diplôme|formation|etudes|études|experience|expérience|profil|contact|coordonnees|coordonnées|loisirs|interets|intérêts|universite|université|ecole|école|institut|lycee|lycée|openclassrooms|telecom|télécom|ina|cnam)\b", normalized):
        return False
    if re.search(r"[,;/•|]", cleaned):
        return True
    return normalized in ALIAS_TO_CANONICAL


def normalize_skill_name(name: object) -> str:
    text = collapse_spaces("" if name is None else str(name))
    if not text:
        return ""
    canonical = ALIAS_TO_CANONICAL.get(normalize_text(text))
    if canonical:
        return canonical
    normalized = normalize_text(text)
    version_match = re.fullmatch(r"(.+?)\s+\d+(?:\.\d+)*", normalized)
    if version_match:
        base = collapse_spaces(version_match.group(1))
        base_canonical = ALIAS_TO_CANONICAL.get(normalize_text(base))
        if base_canonical:
            return base_canonical
    special = {
        "gestion projet": "Gestion de projet",
        "gestion des projets": "Gestion de projet",
        "js": "JavaScript",
        "postgres": "PostgreSQL",
        "sklearn": "scikit-learn",
        "scikit learn": "scikit-learn",
        "vue": "Vue.js",
        "vuejs": "Vue.js",
        "cpp": "C++",
        "c plus plus": "C++",
        "ml": "Machine Learning",
        "dl": "Deep Learning",
        "api rest": "REST API",
        "rest api": "REST API",
        "eclairage scenique": "Éclairage scénique",
        "regie son": "Régie son",
        "regie lumiere": "Régie lumière",
        "regie video": "Régie vidéo",
        "audio numerique": "Audio numérique",
    }
    if normalized in special:
        return special[normalized]
    return text


def _skill_category(name: str) -> Optional[str]:
    return str(SKILL_CATALOG.get(name, {}).get("category")) if name in SKILL_CATALOG else None


def _tokenize_explicit_line(line: str) -> List[str]:
    parts = [collapse_spaces(part) for part in EXP_SPLIT_RE.split(line)]
    values = [part.strip(" -–—") for part in parts if part and part.strip(" -–—")]
    return values or [line]


def _find_alias_matches(text: str) -> List[Tuple[str, str]]:
    normalized = normalize_text(text)
    matches: List[Tuple[str, str]] = []
    for alias in ALIAS_REGEX:
        canonical = ALIAS_TO_CANONICAL[alias]
        if alias in {"c++", "c plus plus"}:
            pattern = r"c\s*\+\s*\+|c plus plus"
        elif alias == "js":
            pattern = r"\bjs\b"
        elif alias == "ts":
            pattern = r"\bts\b"
        elif alias in {"ml", "dl"}:
            pattern = rf"\b{alias}\b"
        elif alias == "rest":
            pattern = r"\brest\b"
        else:
            pattern = r"\b" + re.escape(alias) + r"\b"
        if re.search(pattern, normalized):
            matches.append((canonical, alias))
    return matches


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
        for part in _tokenize_explicit_line(line):
            name = normalize_skill_name(part)
            if not name:
                continue
            if normalize_text(name) not in ALIAS_TO_CANONICAL:
                continue
            matches.append(SkillMatch(nom=name, categorie=_skill_category(name), source="explicite", texte_source=collapse_spaces(line), confiance=skill_confidence("explicite", explicit=True)))
    return _merge_unique(matches)


def extract_skills_from_text(text: str, *, source: str, formation_source: Optional[str] = None) -> List[SkillMatch]:
    matches: List[SkillMatch] = []
    seen: set = set()
    for canonical, _alias in _find_alias_matches(text):
        key = normalize_text(canonical)
        if key in seen:
            continue
        seen.add(key)
        matches.append(SkillMatch(nom=canonical, categorie=_skill_category(canonical), source=source, texte_source=collapse_spaces(text), confiance=skill_confidence(source), formation_source=formation_source))
    return matches


def merge_skill_matches(*groups: Iterable[SkillMatch]) -> List[SkillMatch]:
    all_matches: List[SkillMatch] = []
    for group in groups:
        all_matches.extend(group)
    return _merge_unique(all_matches)
