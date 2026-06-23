# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Extraction de candidats de compétences depuis le texte brut.

Niveau 2 du pipeline hybride. Ce module segmente le texte en phrases
et extrait des expressions candidates susceptibles de représenter des
compétences : groupes nominaux techniques, actions techniques décrites
dans les missions, formulations liées au profil recherché.

L'extraction repose sur des règles linguistiques simples et des motifs
autour de verbes techniques. Elle ne nécessite pas de dépendance NLP
lourde comme spaCy.
"""

from __future__ import annotations

import logging
import os
import re
from typing import List, Tuple

logger = logging.getLogger(__name__)

ENABLE_CANDIDATE_EXTRACTION = os.getenv("ENABLE_CANDIDATE_EXTRACTION", "true").lower() in ("true", "1", "yes")

_ACTION_VERBS = (
    "maîtriser", "maitriser", "connaître", "connaitre", "développer",
    "concevoir", "déployer", "administrer", "analyser", "piloter",
    "maintenir", "automatiser", "superviser", "utiliser", "programmer",
    "coder", "implémenter", "mettre en place", "gérer", "realiser",
    "réaliser", "assurer", "participer", "contribuer", "diriger",
    "encadrer", "former", "conseiller", "accompagner",
)

_ACTION_VERB_ROOTS = (
    "maîtris", "maitris", "connaiss", "connais", "développ",
    "concev", "déploy", "administr", "analys", "pilot",
    "maintien", "mainten", "automatis", "supervis", "utilis", "programm",
    "cod", "implément", "mettr", "mett", "gèr", "ger", "réalis", "realis",
    "assur", "particip", "contribu", "dirig",
    "encadr", "form", "conseill", "accompagn",
    "surveill",
)

_ACTION_VERB_PATTERN = re.compile(
    r"(?:vous\s+(?:serez\s+)?charg[ée]\s+de|vous\s+|missions?\s*:?\s*|profil\s*:?\s*|compétences?\s*:?\s*|maîtrise\s+de|connaissance\s+de|experience\s+en|expérience\s+en)?\s*"
    r"\b((?:" + "|".join(re.escape(v) for v in _ACTION_VERBS + _ACTION_VERB_ROOTS) + r")[a-zéèêe]*)\b\s+(.{5,120}?)(?:\.|,|;|\n|$)",
    re.IGNORECASE,
)

_NOUN_GROUP_PATTERN = re.compile(
    r"(?:développement|conception|gestion|administration|mise en place|automatisation|"
    r"analyse|pilotage|supervision|maintenance|implémentation|intégration|configuration|"
    r"déploiement|utilisation|programmation|maîtrise|maîtrise de|connaissance de|"
    r"expérience en|expertise en|formation en)\s+de\s+(.{3,80}?)(?:\.|,|;|\n|$)",
    re.IGNORECASE,
)

_COMPETENCE_COLON_PATTERN = re.compile(
    r"compétences?\s*:?\s*(.{5,300}?)(?:\n\n|\n(?=[A-Z])|$)",
    re.IGNORECASE,
)

_PROFIL_PATTERN = re.compile(
    r"(?:profil\s+(?:recherch[ée]|souhait[ée])|vous\s+(?:avez|poss[ée]dez)|maîtrisez)\s*:?\s*(.{5,200}?)(?:\n\n|\n(?=[A-Z])|$)",
    re.IGNORECASE,
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-Œ])|(?<=\n)\s*")

_STOP_WORDS = frozenset({
    "le", "la", "les", "un", "une", "des", "de", "du", "au", "aux",
    "et", "ou", "mais", "donc", "or", "ni", "car", "que", "qui",
    "dans", "sur", "sous", "avec", "sans", "pour", "par", "entre",
    "ce", "cette", "ces", "mon", "ton", "son", "notre", "votre", "leur",
    "nos", "vos", "leurs", "mes", "tes", "ses",
})

_MIN_CANDIDATE_LENGTH = 3
_MAX_CANDIDATE_LENGTH = 80


def _clean_candidate(text: str) -> str:
    """Nettoie un candidat de compétence extrait."""

    cleaned = re.sub(r"\s+", " ", text).strip()
    cleaned = cleaned.rstrip(".,;:")
    cleaned = cleaned.strip()
    if len(cleaned) < _MIN_CANDIDATE_LENGTH or len(cleaned) > _MAX_CANDIDATE_LENGTH:
        return ""
    words = cleaned.split()
    if len(words) <= 1:
        return ""
    non_stop = [w for w in words if w.lower() not in _STOP_WORDS]
    if not non_stop:
        return ""
    return cleaned


def _extract_sentences(text: str) -> List[str]:
    """Segmente un texte en phrases."""

    sentences: List[str] = []
    for raw in _SENTENCE_SPLIT.split(text):
        cleaned = raw.strip()
        if cleaned and len(cleaned) >= 10:
            sentences.append(cleaned)
    return sentences


def extract_candidates(text: str) -> List[Tuple[str, str]]:
    """Extrait des expressions candidates de compétences depuis un texte.

    Parcourt le texte à la recherche de formulations techniques :
    actions décrites avec des verbes techniques, groupes nominaux
    commençant par un nom d'action, listes de compétences après
    un marqueur explicite.

    Args:
        text: Texte brut de l'offre d'emploi.

    Returns:
        Liste de tuples ``(candidat, phrase_source)``.
    """

    if not text or not ENABLE_CANDIDATE_EXTRACTION:
        return []

    candidates: List[Tuple[str, str]] = []
    seen: set = set()

    sentences = _extract_sentences(text)

    for sentence in sentences:
        for match in _ACTION_VERB_PATTERN.finditer(sentence):
            candidate_text = match.group(2) if match.lastindex and match.lastindex >= 2 else match.group(0)
            cleaned = _clean_candidate(candidate_text)
            if cleaned and cleaned.lower() not in seen:
                seen.add(cleaned.lower())
                candidates.append((cleaned, sentence))

        for match in _NOUN_GROUP_PATTERN.finditer(sentence):
            candidate_text = match.group(1) if match.lastindex else match.group(0)
            cleaned = _clean_candidate(candidate_text)
            if cleaned and cleaned.lower() not in seen:
                seen.add(cleaned.lower())
                candidates.append((cleaned, sentence))

    for match in _COMPETENCE_COLON_PATTERN.finditer(text):
        block = match.group(1)
        for part in re.split(r"[,;•·]", block):
            cleaned = _clean_candidate(part)
            if cleaned and cleaned.lower() not in seen:
                sentence = _find_containing_sentence(text, match.start())
                seen.add(cleaned.lower())
                candidates.append((cleaned, sentence))

    for match in _PROFIL_PATTERN.finditer(text):
        block = match.group(1)
        for part in re.split(r"[,;•·]", block):
            cleaned = _clean_candidate(part)
            if cleaned and cleaned.lower() not in seen:
                sentence = _find_containing_sentence(text, match.start())
                seen.add(cleaned.lower())
                candidates.append((cleaned, sentence))

    return candidates


def _find_containing_sentence(text: str, position: int) -> str:
    """Retourne la phrase contenant la position donnée."""

    start = max(text.rfind("\n", 0, position), text.rfind(".", 0, position))
    start = start + 1 if start >= 0 else 0
    end = text.find("\n", position)
    end_dot = text.find(".", position)
    if end == -1:
        end = len(text)
    if end_dot != -1 and end_dot < end:
        end = end_dot + 1
    return text[start:end].strip()
