# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Dictionnaire initial des compétences canoniques et de leurs alias.

Le projet a besoin d'un référentiel simple, lisible et modifiable à la main.
Le dictionnaire ci-dessous sert de base à l'extraction NER, à la
normalisation, au regroupement sémantique et au matching.
"""

from __future__ import annotations

import re
import unicodedata
from collections import OrderedDict
from typing import Dict, Iterable, List, Tuple


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_skill_lookup(value: object) -> str:
    """Normalise une compétence pour la recherche d'alias.

    La normalisation conserve les symboles utiles comme ``+`` ou ``#`` afin
    de distinguer par exemple ``C`` de ``C++``.
    """

    text = "" if value is None else str(value)
    text = _strip_accents(text.lower())
    text = re.sub(r"[’'`´]", " ", text)
    text = re.sub(r"[^a-z0-9+#]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


SKILL_DICTIONARY: "OrderedDict[str, Dict[str, object]]" = OrderedDict(
    [
        (
            "Python",
            {
                "aliases": ["python", "python3", "programmation python", "developpement python", "développement python", "python 3", "python 3.x"],
                "category": "programmation",
            },
        ),
        ("PHP", {"aliases": ["php"], "category": "programmation"}),
        ("Symfony", {"aliases": ["symfony", "symfony 5", "symfony 6"], "category": "backend"}),
        ("Flask", {"aliases": ["flask"], "category": "backend"}),
        ("FastAPI", {"aliases": ["fastapi"], "category": "backend"}),
        ("Django", {"aliases": ["django"], "category": "backend"}),
        ("SQL", {"aliases": ["sql"], "category": "data"}),
        ("PostgreSQL", {"aliases": ["postgresql", "postgres", "postgres sql"], "category": "data"}),
        ("MySQL", {"aliases": ["mysql"], "category": "data"}),
        ("JavaScript", {"aliases": ["javascript", "js", "java script", "ecmascript"], "category": "frontend"}),
        ("TypeScript", {"aliases": ["typescript", "ts"], "category": "frontend"}),
        ("HTML", {"aliases": ["html"], "category": "frontend"}),
        ("CSS", {"aliases": ["css"], "category": "frontend"}),
        ("React", {"aliases": ["react", "reactjs", "react.js"], "category": "frontend"}),
        ("Vue.js", {"aliases": ["vue", "vuejs", "vue js", "vue.js"], "category": "frontend"}),
        ("C", {"aliases": ["language c", "langage c"], "category": "programmation"}),
        ("C++", {"aliases": ["c++", "cpp", "c plus plus"], "category": "programmation"}),
        ("Qt", {"aliases": ["qt"], "category": "desktop"}),
        ("CMake", {"aliases": ["cmake"], "category": "build"}),
        ("Git", {"aliases": ["git"], "category": "outillage"}),
        ("GitHub", {"aliases": ["github"], "category": "outillage"}),
        ("Docker", {"aliases": ["docker"], "category": "devops"}),
        ("Kubernetes", {"aliases": ["kubernetes", "k8s"], "category": "devops"}),
        ("Linux", {"aliases": ["linux"], "category": "systeme"}),
        ("AWS", {"aliases": ["aws", "amazon web services"], "category": "cloud"}),
        ("Azure", {"aliases": ["azure"], "category": "cloud"}),
        ("Terraform", {"aliases": ["terraform"], "category": "devops"}),
        ("Ansible", {"aliases": ["ansible"], "category": "devops"}),
        ("Machine learning", {"aliases": ["machine learning", "machinelearning", "ml"], "category": "ia"}),
        ("Deep learning", {"aliases": ["deep learning", "deeplearning", "dl"], "category": "ia"}),
        ("NLP", {"aliases": ["nlp", "traitement du langage naturel"], "category": "ia"}),
        ("LLM", {"aliases": ["llm", "large language model", "large language models"], "category": "ia"}),
        ("RAG", {"aliases": ["rag"], "category": "ia"}),
        ("LangChain", {"aliases": ["langchain"], "category": "ia"}),
        ("MLOps", {"aliases": ["mlops"], "category": "ia"}),
        ("Intelligence artificielle", {"aliases": ["ia", "ai", "artificial intelligence", "intelligence artificielle"], "category": "ia"}),
        ("Data engineering", {"aliases": ["data engineering", "ingenierie des donnees", "ingénierie des données"], "category": "data"}),
        ("Analyse de données", {"aliases": ["analyse de données", "analyse de donnees", "data analysis", "data analytics"], "category": "data"}),
        ("Gestion de projet", {"aliases": ["gestion de projet", "gestion projets", "project management", "agile", "scrum", "méthode agile", "methodologie agile"], "category": "management"}),
        ("Cahier des charges", {"aliases": ["cahier des charges", "specifications fonctionnelles"], "category": "management"}),
        ("Application web", {"aliases": ["application web", "web application"], "category": "web"}),
        ("Développement web", {"aliases": ["developpement web", "développement web", "web development"], "category": "web"}),
        ("API REST", {"aliases": ["api rest", "rest api", "restful api", "rest"], "category": "backend"}),
        ("NoSQL", {"aliases": ["nosql"], "category": "data"}),
        ("scikit-learn", {"aliases": ["scikit-learn", "scikit learn", "sklearn"], "category": "data_science"}),
        ("Pandas", {"aliases": ["pandas"], "category": "data_science"}),
        ("NumPy", {"aliases": ["numpy"], "category": "data_science"}),
        ("PyTorch", {"aliases": ["pytorch"], "category": "data_science"}),
        ("TensorFlow", {"aliases": ["tensorflow"], "category": "data_science"}),
        ("REST", {"aliases": ["rest"], "category": "backend"}),
        ("Java", {"aliases": ["java"], "category": "programmation"}),
    ]
)


def iter_skill_definitions() -> Iterable[Tuple[str, Dict[str, object]]]:
    """Itère sur les compétences canoniques du référentiel."""

    return SKILL_DICTIONARY.items()


def build_alias_index() -> Dict[str, str]:
    """Construit l'index alias -> compétence canonique."""

    index: Dict[str, str] = {}
    for canonical, spec in SKILL_DICTIONARY.items():
        aliases = list(spec.get("aliases") or [])
        aliases.append(canonical)
        for alias in aliases:
            normalized = normalize_skill_lookup(alias)
            if not normalized:
                continue
            index.setdefault(normalized, canonical)
    return index


SKILL_ALIAS_INDEX = build_alias_index()
ALIAS_LIST = sorted(SKILL_ALIAS_INDEX.keys(), key=len, reverse=True)



def build_alias_pattern(alias: str) -> str:
    """Construit une expression régulière conservatrice pour un alias."""

    normalized = normalize_skill_lookup(alias)
    if not normalized:
        return ""
    if normalized == "c++":
        return r"(?<![a-z0-9+#])c\s*\+\s*\+(?![a-z0-9+#])"
    parts = [re.escape(part) for part in normalized.split() if part]
    if not parts:
        return ""
    body = r"\s+".join(parts)
    return r"(?<![a-z0-9+#])" + body + r"(?![a-z0-9+#])"
