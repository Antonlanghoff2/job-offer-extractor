# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Rapprochement sémantique des candidats avec le référentiel.

Niveau 3 du pipeline hybride. Ce module compare les expressions
candidates extraites avec un référentiel de compétences stocké dans
``data/referentials/skills.json``.

Le rapprochement utilise Sentence Transformers si disponible, sinon
il retombe sur une comparaison textuelle basée sur la similarité
cosinus de tokens. Le modèle est chargé en lazy loading et mis en
cache pour éviter les rechargements.
"""

from __future__ import annotations

import logging
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .models import ExtractedSkill
from .referential_loader import (
    clear_referential_cache,
    load_referential,
    resolve_referential_path,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REFERENTIAL_PATH = resolve_referential_path("skills.json")

SEMANTIC_SKILL_THRESHOLD = float(os.getenv("SEMANTIC_SKILL_THRESHOLD", "0.72"))
IMPLICIT_SKILL_THRESHOLD = float(os.getenv("IMPLICIT_SKILL_THRESHOLD", "0.78"))
MAX_SEMANTIC_MATCHES_PER_CANDIDATE = int(os.getenv("MAX_SEMANTIC_MATCHES_PER_CANDIDATE", "3"))
ENABLE_SEMANTIC_EXTRACTION = os.getenv("ENABLE_SEMANTIC_EXTRACTION", "true").lower() in ("true", "1", "yes")

ENABLE_SENTENCE_TRANSFORMERS = os.getenv("ENABLE_SENTENCE_TRANSFORMERS", "false").lower() in ("true", "1", "yes")
SENTENCE_TRANSFORMER_MODEL = os.getenv("SENTENCE_TRANSFORMER_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

_referential_cache: Optional[List[Dict[str, Any]]] = None
_model_cache: Optional[Any] = None
_embeddings_cache: Optional[Dict[str, List[float]]] = None


def _load_referential_result(path: Optional[Path] = None):
    """Charge le référentiel de compétences avec validation et cache partagé."""

    referential_path = path or DEFAULT_REFERENTIAL_PATH
    return load_referential(
        "skills.json",
        referential_name="skills_referential",
        required_string_fields=("canonical_name", "category", "description"),
        required_list_fields=("aliases",),
        optional_list_fields=("domains",),
        path=referential_path,
    )


def _load_referential(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Charge le référentiel de compétences depuis le fichier JSON."""

    result = _load_referential_result(path)
    if not result.ok:
        logger.warning(result.message)
        return []
    return [dict(entry) for entry in result.entries]


def _tokenize(text: str) -> List[str]:
    """Tokenise un texte en mots normalisés."""

    import re
    import unicodedata
    normalized = unicodedata.normalize("NFKD", text.lower())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"[^a-z0-9+# ]", " ", normalized)
    return [token for token in normalized.split() if token and len(token) > 1]


def _cosine_similarity(vec_a: Dict[str, float], vec_b: Dict[str, float]) -> float:
    """Calcule la similarité cosinus entre deux vecteurs creux."""

    common_keys = set(vec_a.keys()) & set(vec_b.keys())
    if not common_keys:
        return 0.0
    dot_product = sum(vec_a[k] * vec_b[k] for k in common_keys)
    norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
    norm_b = math.sqrt(sum(v * v for v in vec_b.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot_product / (norm_a * norm_b)


def _text_to_vector(text: str) -> Dict[str, float]:
    """Convertit un texte en vecteur creux basé sur les tokens."""

    tokens = _tokenize(text)
    vector: Dict[str, float] = {}
    for token in tokens:
        vector[token] = vector.get(token, 0.0) + 1.0
    return vector


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
        logger.debug("sentence-transformers non installé, fallback sur comparaison textuelle.")
        return None
    except Exception as exc:
        logger.warning("Échec du chargement du modèle Sentence Transformer: %s", exc)
        return None


def _compute_semantic_similarity(candidate: str, referential_entry: Dict[str, Any]) -> float:
    """Calcule la similarité sémantique entre un candidat et une entrée du référentiel."""

    model = _load_sentence_transformer()
    if model is not None:
        return _compute_similarity_with_transformer(model, candidate, referential_entry)
    return _compute_similarity_textual(candidate, referential_entry)


def _compute_similarity_with_transformer(model: Any, candidate: str, entry: Dict[str, Any]) -> float:
    """Calcule la similarité avec Sentence Transformers."""

    global _embeddings_cache
    if _embeddings_cache is None:
        _embeddings_cache = {}

    entry_key = entry.get("canonical_name", "")
    if entry_key not in _embeddings_cache:
        texts_to_embed = [entry.get("canonical_name", "")]
        texts_to_embed.extend(entry.get("aliases", []))
        desc = entry.get("description", "")
        if desc:
            texts_to_embed.append(desc)
        embeddings = model.encode(texts_to_embed, convert_to_numpy=True)
        _embeddings_cache[entry_key] = {
            "canonical": embeddings[0],
            "aliases": embeddings[1:1 + len(entry.get("aliases", []))],
            "description": embeddings[-1] if desc else None,
        }

    candidate_embedding = model.encode([candidate], convert_to_numpy=True)[0]
    cached = _embeddings_cache[entry_key]

    similarities: List[float] = []
    import numpy as np
    similarities.append(float(np.dot(candidate_embedding, cached["canonical"]) / (
        np.linalg.norm(candidate_embedding) * np.linalg.norm(cached["canonical"]) + 1e-9
    )))
    for alias_emb in cached["aliases"]:
        similarities.append(float(np.dot(candidate_embedding, alias_emb) / (
            np.linalg.norm(candidate_embedding) * np.linalg.norm(alias_emb) + 1e-9
        )))
    if cached["description"] is not None:
        similarities.append(float(np.dot(candidate_embedding, cached["description"]) / (
            np.linalg.norm(candidate_embedding) * np.linalg.norm(cached["description"]) + 1e-9
        )))

    return max(similarities) if similarities else 0.0


def _compute_similarity_textual(candidate: str, entry: Dict[str, Any]) -> float:
    """Calcule la similarité textuelle sans modèle de transformer."""

    candidate_vec = _text_to_vector(candidate)
    if not candidate_vec:
        return 0.0

    similarities: List[float] = []

    canonical_vec = _text_to_vector(entry.get("canonical_name", ""))
    if canonical_vec:
        similarities.append(_cosine_similarity(candidate_vec, canonical_vec))

    for alias in entry.get("aliases", []):
        alias_vec = _text_to_vector(alias)
        if alias_vec:
            similarities.append(_cosine_similarity(candidate_vec, alias_vec))

    description = entry.get("description", "")
    if description:
        desc_vec = _text_to_vector(description)
        if desc_vec:
            similarities.append(_cosine_similarity(candidate_vec, desc_vec))

    best = max(similarities) if similarities else 0.0

    candidate_tokens = set(_tokenize(candidate))
    for alias in entry.get("aliases", []):
        alias_tokens = set(_tokenize(alias))
        if not alias_tokens:
            continue
        overlap = candidate_tokens & alias_tokens
        if len(overlap) >= 2:
            recall = len(overlap) / len(alias_tokens)
            if recall >= 0.5:
                best = max(best, 0.72 + 0.2 * recall)

    return best


def match_candidates_to_referential(
    candidates: List[Tuple[str, str]],
    referential_path: Optional[Path] = None,
) -> List[ExtractedSkill]:
    """Rapproche les candidats extraits avec le référentiel de compétences.

    Pour chaque candidat, calcule la similarité sémantique avec chaque
    entrée du référentiel et retient les meilleurs résultats au-dessus
    du seuil configurable.

    Args:
        candidates: Liste de tuples ``(candidat, phrase_source)``.
        referential_path: Chemin optionnel vers le référentiel JSON.

    Returns:
        Liste de compétences détectées par rapprochement sémantique.
    """

    if not candidates or not ENABLE_SEMANTIC_EXTRACTION:
        return []

    referential = _load_referential(referential_path)
    if not referential:
        return []

    results: List[ExtractedSkill] = []
    seen_canonical: set = set()

    for candidate_text, source_sentence in candidates:
        matches: List[Tuple[float, Dict[str, Any]]] = []

        for entry in referential:
            similarity = _compute_semantic_similarity(candidate_text, entry)
            if similarity >= SEMANTIC_SKILL_THRESHOLD:
                matches.append((similarity, entry))

        matches.sort(key=lambda item: item[0], reverse=True)
        matches = matches[:MAX_SEMANTIC_MATCHES_PER_CANDIDATE]

        for score, entry in matches:
            canonical = entry.get("canonical_name", "")
            if canonical.lower() in seen_canonical:
                continue
            seen_canonical.add(canonical.lower())

            extraction_type = "semantic"
            confidence = round(score, 4)
            if score >= IMPLICIT_SKILL_THRESHOLD and _looks_implicit(candidate_text, entry):
                extraction_type = "implicit"
                confidence = round(score * 0.95, 4)

            results.append(ExtractedSkill(
                canonical_name=canonical,
                raw_text=candidate_text,
                source_sentence=source_sentence,
                extraction_type=extraction_type,
                confidence=confidence,
                category=entry.get("category"),
                optional=False,
                negated=False,
            ))

    return results


def _looks_implicit(candidate_text: str, entry: Dict[str, Any]) -> bool:
    """Détermine si un candidat correspond à une compétence implicite.

    Une compétence est considérée implicite si le texte candidat ne
    contient pas directement le nom canonique ni un de ses alias,
    mais décrit une activité ou un contexte lié à la compétence.
    """

    canonical = entry.get("canonical_name", "").lower()
    aliases = [alias.lower() for alias in entry.get("aliases", [])]

    candidate_lower = candidate_text.lower()
    if canonical in candidate_lower:
        return False
    for alias in aliases:
        if alias in candidate_lower and len(alias) >= 3:
            return False

    description = entry.get("description", "").lower()
    if description:
        desc_words = set(description.split())
        candidate_words = set(candidate_lower.split())
        overlap = desc_words & candidate_words
        if len(overlap) >= 2:
            return True

    return False


def reset_caches() -> None:
    """Réinitialise les caches internes. Utile pour les tests."""

    global _referential_cache, _model_cache, _embeddings_cache
    clear_referential_cache()
    _referential_cache = None
    _model_cache = None
    _embeddings_cache = None
