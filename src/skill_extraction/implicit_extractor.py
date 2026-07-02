# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Extraction de compétences implicites depuis les descriptions de missions.

Niveau 4 du pipeline hybride. Ce module déduit des compétences à partir
d'actions et de responsabilités décrites dans le texte, sans que celles-ci
ne soient explicitement mentionnées.

Le module utilise :
- Un référentiel d'indicateurs pour le matching déterministe
- Sentence Transformers pour le matching sémantique (optionnel)
- Une détection de négations pour éviter les faux positifs
- Une détection de phrases de missions pour cibler l'analyse

Exemples :
- « Vous déploierez les modèles en production » → MLOps
- « Vous concevrez des flux d'alimentation des données » → Data Engineering
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .models import ExtractedSkill
from .referential_loader import (
    clear_referential_cache,
    load_referential,
    resolve_referential_path,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_IMPLICIT_REFERENTIAL_PATH = resolve_referential_path("implicit_skills.json")

IMPLICIT_SKILL_THRESHOLD = float(os.getenv("IMPLICIT_SKILL_THRESHOLD", "0.78"))
MAX_IMPLICIT_SKILLS_PER_SENTENCE = int(os.getenv("MAX_IMPLICIT_SKILLS_PER_SENTENCE", "3"))
ENABLE_IMPLICIT_SKILLS = os.getenv("ENABLE_IMPLICIT_SKILLS", "true").lower() in ("true", "1", "yes")
ENABLE_SENTENCE_TRANSFORMERS = os.getenv("ENABLE_SENTENCE_TRANSFORMERS", "false").lower() in ("true", "1", "yes")
SENTENCE_TRANSFORMER_MODEL = os.getenv("SENTENCE_TRANSFORMER_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
DEBUG_IMPLICIT_EXTRACTION = os.getenv("DEBUG_IMPLICIT_EXTRACTION", "false").lower() in ("true", "1", "yes")

_NEGATION_PATTERNS = (
    r"aucune\s+(?:connaissance|expérience|utilisation)\s+de",
    r"pas\s+de\s+(?:connaissance|expérience|utilisation)\s+(?:en|de)",
    r"n['’](?:utilisez|utiliserez|aurez|auriez|devez|deviendrez)\s+pas",
    r"sans\s+(?:recours\s+à|utilisation\s+de|connaissance\s+de)",
    r"non\s+(?:requis|requise|nécessaire)",
    r"inutile\s+de",
    r"pas\s+nécessaire\s+de",
    r"ne\s+sera\s+(?:pas|point)\s+(?:utilisé|demandé|requis)",
)

_MISSION_MARKERS = (
    r"vous\s+(?:serez\s+)?charg[ée]s?\s+de",
    r"vous\s+(?:serez\s+)?amen[ée]s?\s+[àa]",
    r"vous\s+d[ée]velopp\w*",
    r"vous\s+d[ée]ploi\w*",
    r"vous\s+concev\w*",
    r"vous\s+g[ée]r\w*",
    r"vous\s+analys\w*",
    r"vous\s+mettrez\s+en\s+place",
    r"vous\s+assur\w*",
    r"vous\s+pilot\w*",
    r"vous\s+supervis\w*",
    r"vous\s+coordonn\w*",
    r"vous\s+sécuris\w*",
    r"vous\s+surveill\w*",
    r"vos\s+missions?\s+comprennent",
    r"vos\s+responsabilit[ée]s",
    r"missions?\s*:",
    r"activit[ée]s?\s*:",
    r"responsabilit[ée]s?\s*:",
)

_GENERIC_PHRASES = (
    r"travailler\s+en\s+[ée]quipe",
    r"bonne\s+communication",
    r"esprit\s+d'[ée]quipe",
    r"dynamique\s+et\s+motivat[ée]",
    r"capacit[ée]\s+[àa]\s+travailler",
    r"sens\s+du\s+service",
    r"autonomie",
    r"rigueur",
    r"proactivit[ée]",
)

_action_verbs = (
    "développer", "concevoir", "implémenter", "déployer", "maintenir",
    "administrer", "analyser", "optimiser", "automatiser", "orchestrer",
    "construire", "mettre en place", "piloter", "superviser", "gérer",
    "assurer", "garantir", "sécuriser", "surveiller", "monitorer",
)

_referential_cache: Optional[List[Dict[str, Any]]] = None
_model_cache: Optional[Any] = None
_embeddings_cache: Optional[Dict[str, Any]] = None


@dataclass
class ImplicitExtractionDebug:
    """Informations de debug pour l'extraction implicite."""

    sentence: str
    is_mission: bool
    is_negated: bool
    is_generic: bool
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    accepted: List[Dict[str, Any]] = field(default_factory=list)
    rejected: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "evaluated"
    canonical_name: Optional[str] = None
    matched_text: Optional[str] = None
    reason: Optional[str] = None
    path: Optional[str] = None


def _format_debug_path(path: Path) -> str:
    """Formate un chemin pour les informations de debug publiques."""

    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _load_implicit_referential_result(path: Optional[Path] = None):
    """Charge le référentiel implicite avec validation et cache partagé."""

    referential_path = path or DEFAULT_IMPLICIT_REFERENTIAL_PATH
    return load_referential(
        "implicit_skills.json",
        referential_name="implicit_referential",
        required_string_fields=("canonical_name", "category", "description"),
        required_list_fields=("indicators",),
        path=referential_path,
    )


def _load_implicit_referential(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Charge le référentiel de compétences implicites."""

    result = _load_implicit_referential_result(path)
    if not result.ok:
        logger.warning(result.message)
        return []
    return [dict(entry) for entry in result.entries]


def _normalize_text(text: str) -> str:
    """Normalise un texte pour la comparaison."""

    normalized = unicodedata.normalize("NFKD", text.lower())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"[^a-z0-9+# ]", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _is_negated(sentence: str) -> bool:
    """Vérifie si la phrase contient un marqueur de négation."""

    sentence_lower = sentence.lower()
    for pattern in _NEGATION_PATTERNS:
        if re.search(pattern, sentence_lower):
            return True
    return False


def _is_mission_sentence(sentence: str) -> bool:
    """Vérifie si la phrase décrit une mission ou une responsabilité."""

    sentence_lower = sentence.lower()
    for pattern in _MISSION_MARKERS:
        if re.search(pattern, sentence_lower):
            return True
    for verb in _action_verbs:
        if re.search(rf"\b{verb}[a-zéèêe]*\b", sentence_lower):
            return True
    return False


def _is_generic_phrase(sentence: str) -> bool:
    """Vérifie si la phrase est trop générique pour produire des compétences."""

    sentence_lower = sentence.lower()
    for pattern in _GENERIC_PHRASES:
        if re.search(pattern, sentence_lower):
            return True
    return False


def _extract_sentences(text: str) -> List[str]:
    """Segmente un texte en phrases."""

    sentences: List[str] = []
    parts = re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Œ])|(?<=\n)\s*", text)
    for part in parts:
        cleaned = part.strip()
        if cleaned and len(cleaned) >= 15:
            sentences.append(cleaned)
    return sentences


def _match_by_indicators(sentence: str, referential: List[Dict[str, Any]]) -> List[Tuple[float, Dict[str, Any], str]]:
    """Matche une phrase avec les indicateurs du référentiel."""

    sentence_normalized = _normalize_text(sentence)
    matches: List[Tuple[float, Dict[str, Any], str]] = []

    for entry in referential:
        indicators = entry.get("indicators", [])
        best_indicator = ""
        best_score = 0.0

        for indicator in indicators:
            indicator_normalized = _normalize_text(indicator)
            if not indicator_normalized:
                continue

            score = 0.0
            if indicator_normalized in sentence_normalized:
                score = 0.95
            else:
                indicator_words = set(indicator_normalized.split())
                sentence_words = set(sentence_normalized.split())
                if indicator_words:
                    overlap = indicator_words & sentence_words
                    if len(overlap) >= 2:
                        recall = len(overlap) / len(indicator_words)
                        precision = len(overlap) / len(sentence_words) if sentence_words else 0
                        score = 0.7 + 0.25 * (recall + precision) / 2

            if score > best_score:
                best_score = score
                best_indicator = indicator

        if best_score >= IMPLICIT_SKILL_THRESHOLD and best_indicator:
            matches.append((best_score, entry, best_indicator))

    matches.sort(key=lambda x: x[0], reverse=True)
    return matches[:MAX_IMPLICIT_SKILLS_PER_SENTENCE]


def _load_sentence_transformer() -> Optional[Any]:
    """Charge le modèle Sentence Transformer en lazy loading."""

    global _model_cache
    if _model_cache is not None:
        return _model_cache

    if not ENABLE_SENTENCE_TRANSFORMERS:
        return None

    try:
        from sentence_transformers import SentenceTransformer
        _model_cache = SentenceTransformer(SENTENCE_TRANSFORMER_MODEL)
        logger.info("Modèle Sentence Transformer chargé: %s", SENTENCE_TRANSFORMER_MODEL)
        return _model_cache
    except ImportError:
        logger.debug("sentence-transformers non installé, fallback sur indicateurs.")
        return None
    except Exception as exc:
        logger.warning("Échec du chargement du modèle Sentence Transformer: %s", exc)
        return None


def _compute_semantic_similarity(sentence: str, entry: Dict[str, Any]) -> Tuple[float, str]:
    """Calcule la similarité sémantique avec Sentence Transformers."""

    global _embeddings_cache
    if _embeddings_cache is None:
        _embeddings_cache = {}

    model = _load_sentence_transformer()
    if model is None:
        return 0.0, ""

    entry_key = entry.get("canonical_name", "")
    if entry_key not in _embeddings_cache:
        texts = [entry.get("description", "")]
        texts.extend(entry.get("indicators", []))
        embeddings = model.encode(texts, convert_to_numpy=True)
        _embeddings_cache[entry_key] = {
            "description": embeddings[0],
            "indicators": embeddings[1:],
        }

    sentence_embedding = model.encode([sentence], convert_to_numpy=True)[0]
    cached = _embeddings_cache[entry_key]

    import numpy as np

    def cosine_sim(a, b):
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))

    best_score = 0.0
    best_indicator = ""

    desc_sim = cosine_sim(sentence_embedding, cached["description"])
    if desc_sim > best_score:
        best_score = desc_sim
        best_indicator = entry.get("description", "")

    for i, indicator_emb in enumerate(cached["indicators"]):
        ind_sim = cosine_sim(sentence_embedding, indicator_emb)
        if ind_sim > best_score:
            best_score = ind_sim
            indicators = entry.get("indicators", [])
            best_indicator = indicators[i] if i < len(indicators) else ""

    return best_score, best_indicator


def _match_by_semantic(sentence: str, referential: List[Dict[str, Any]]) -> List[Tuple[float, Dict[str, Any], str]]:
    """Matche une phrase avec le référentiel par similarité sémantique."""

    matches: List[Tuple[float, Dict[str, Any], str]] = []

    for entry in referential:
        score, indicator = _compute_semantic_similarity(sentence, entry)
        if score >= IMPLICIT_SKILL_THRESHOLD:
            matches.append((score, entry, indicator))

    matches.sort(key=lambda x: x[0], reverse=True)
    return matches[:MAX_IMPLICIT_SKILLS_PER_SENTENCE]


def extract_implicit_skills(
    text: str,
    *,
    explicit_skills: Optional[Set[str]] = None,
    debug: bool = False,
) -> Tuple[List[ExtractedSkill], List[ImplicitExtractionDebug]]:
    """Extrait les compétences implicites depuis un texte.

    Parcourt les phrases du texte, identifie celles décrivant des missions
    ou responsabilités, et tente d'en déduire des compétences implicites
    via les indicateurs du référentiel ou Sentence Transformers.

    Args:
        text: Texte brut de l'offre d'emploi.
        explicit_skills: Ensemble des compétences déjà extraites explicitement.
        debug: Si True, retourne les informations de debug.

    Returns:
        Tuple de (compétences implicites, informations de debug).
    """

    if not text or not ENABLE_IMPLICIT_SKILLS:
        return [], []

    referential_result = _load_implicit_referential_result()
    if not referential_result.ok:
        debug_infos: List[ImplicitExtractionDebug] = []
        if debug or DEBUG_IMPLICIT_EXTRACTION:
            debug_infos.append(
                ImplicitExtractionDebug(
                    sentence="",
                    is_mission=False,
                    is_negated=False,
                    is_generic=False,
                    status="configuration_error",
                    reason=referential_result.reason or "implicit_referential_error",
                    path=_format_debug_path(referential_result.path),
                    rejected=[{
                        "status": "configuration_error",
                        "reason": referential_result.reason or "implicit_referential_error",
                        "path": _format_debug_path(referential_result.path),
                    }],
                )
            )
        return [], debug_infos

    referential = [dict(entry) for entry in referential_result.entries]

    explicit_skills = explicit_skills or set()
    explicit_lower = {s.lower() for s in explicit_skills}

    sentences = _extract_sentences(text)
    results: List[ExtractedSkill] = []
    debug_infos: List[ImplicitExtractionDebug] = []
    seen_canonical: Set[str] = set()

    for sentence in sentences:
        is_negated = _is_negated(sentence)
        is_mission = _is_mission_sentence(sentence)
        is_generic = _is_generic_phrase(sentence)

        debug_info = ImplicitExtractionDebug(
            sentence=sentence,
            is_mission=is_mission,
            is_negated=is_negated,
            is_generic=is_generic,
        )

        if is_negated:
            if debug or DEBUG_IMPLICIT_EXTRACTION:
                debug_info.rejected.append({
                    "status": "rejected",
                    "reason": "negation",
                    "matched_text": sentence,
                })
                debug_infos.append(debug_info)
            continue

        if not is_mission:
            if debug or DEBUG_IMPLICIT_EXTRACTION:
                debug_info.rejected.append({
                    "status": "rejected",
                    "reason": "not_mission",
                    "matched_text": sentence,
                })
                debug_infos.append(debug_info)
            continue

        if is_generic:
            if debug or DEBUG_IMPLICIT_EXTRACTION:
                debug_info.rejected.append({
                    "status": "rejected",
                    "reason": "generic_phrase",
                    "matched_text": sentence,
                })
                debug_infos.append(debug_info)
            continue

        if ENABLE_SENTENCE_TRANSFORMERS:
            matches = _match_by_semantic(sentence, referential)
        else:
            matches = _match_by_indicators(sentence, referential)

        for score, entry, indicator in matches:
            canonical = entry.get("canonical_name", "")
            if not canonical:
                continue

            if canonical.lower() in explicit_lower:
                if debug or DEBUG_IMPLICIT_EXTRACTION:
                    debug_info.rejected.append({
                        "status": "rejected",
                        "reason": "already_explicit",
                        "canonical_name": canonical,
                        "matched_text": sentence,
                        "score": score,
                    })
                continue

            if canonical.lower() in seen_canonical:
                continue

            seen_canonical.add(canonical.lower())

            reason = f"Indicateur détecté: '{indicator}' (score={score:.2f})"

            skill = ExtractedSkill(
                canonical_name=canonical,
                raw_text=sentence,
                source_sentence=sentence,
                extraction_type="implicit",
                confidence=round(score, 4),
                category=entry.get("category"),
                optional=False,
                negated=False,
                reason=reason,
            )
            results.append(skill)

            if debug or DEBUG_IMPLICIT_EXTRACTION:
                debug_info.accepted.append({
                    "status": "accepted",
                    "canonical_name": canonical,
                    "matched_text": indicator or sentence,
                    "reason": reason,
                    "score": score,
                })
                debug_info.candidates.append({
                    "status": "candidate",
                    "canonical_name": canonical,
                    "matched_text": indicator or sentence,
                    "score": score,
                })

        if debug or DEBUG_IMPLICIT_EXTRACTION:
            debug_infos.append(debug_info)

    if debug or DEBUG_IMPLICIT_EXTRACTION:
        logger.info("Extraction implicite: %d compétences depuis %d phrases", len(results), len(sentences))
        for info in debug_infos:
            if info.accepted:
                logger.info("  Phrase: %s", info.sentence[:80])
                for acc in info.accepted:
                    logger.info("    + %s (score=%.2f, indicateur=%s)", acc["canonical_name"], acc["score"], acc["matched_text"])

    return results, debug_infos


def reset_caches() -> None:
    """Réinitialise les caches internes. Utile pour les tests."""

    global _referential_cache, _model_cache, _embeddings_cache
    clear_referential_cache()
    _referential_cache = None
    _model_cache = None
    _embeddings_cache = None
