# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Prepare model 1 outputs with market context for a future model 2.

This module also exposes a conservative market-offer normalizer used by the
formation recommendation layer. The historical pandas merge helpers remain
available for the existing data-preparation workflow.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTEXT_PATH = PROJECT_ROOT / "data" / "processed" / "metier_context_t3_2025.csv"


def normalize_text(value: object) -> str:
    """Normalize text for conservative matching."""
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _as_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _first_value(raw_offer: Dict[str, Any], keys: tuple) -> object:
    for key in keys:
        value = raw_offer.get(key)
        if value not in (None, ""):
            return value
    return None


def _split_values(value: object) -> List[object]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return []
        if any(sep in cleaned for sep in (",", ";", "|")):
            return [part.strip() for part in re.split(r"[;,|]", cleaned) if part.strip()]
        return [cleaned]
    return [value]


def _collect_text_values(value: object) -> List[str]:
    values: List[str] = []
    for item in _split_values(value):
        if isinstance(item, dict):
            candidate = (
                item.get("libelle")
                or item.get("label")
                or item.get("name")
                or item.get("title")
                or item.get("display_name")
                or item.get("ville")
                or item.get("commune")
            )
        else:
            candidate = item
        text = _as_text(candidate)
        if text:
            values.append(text)
    return values


def normalize_market_offer(raw_offer: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a market offer into a stable internal structure.

    The helper accepts both legacy ``competences`` and newer
    ``competences_requises`` payloads, deduplicates skills conservatively and
    keeps the fields required by the aggregation and recommendation layers.
    """

    if not isinstance(raw_offer, dict):
        raise TypeError("raw_offer must be a dictionary")

    title = _first_value(raw_offer, ("intitule_poste", "intitule", "titre", "job_title", "title", "metier"))
    metier = _first_value(raw_offer, ("metier", "romeLibelle", "appellationlibelle", "job_title", "title", "intitule"))
    competences: List[str] = []
    for key in ("competences", "competences_requises", "skills", "skillset", "mots_cles"):
        competences.extend(_collect_text_values(raw_offer.get(key)))
    deduped_competences: List[str] = []
    seen = set()
    for item in competences:
        normalized = normalize_text(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped_competences.append(_as_text(item))

    date_publication = _first_value(
        raw_offer,
        ("date_publication", "date_publication_offre", "dateCreation", "dateActualisation", "date_creation", "date", "published_at"),
    )

    territoire = _first_value(raw_offer, ("territoire", "ville", "location", "lieu", "code_postal", "codePostal"))
    if not territoire:
        lieu_travail = raw_offer.get("lieuTravail")
        if isinstance(lieu_travail, dict):
            territoire = (
                lieu_travail.get("libelle")
                or lieu_travail.get("commune")
                or lieu_travail.get("codePostal")
                or ""
            )

    return {
        "intitule_poste": _as_text(title) or None,
        "intitule": _as_text(title) or None,
        "metier": _as_text(metier) or None,
        "competences": deduped_competences,
        "niveau": _as_text(_first_value(raw_offer, ("niveau", "experience_level", "seniority", "experienceLibelle", "experience"))) or None,
        "contrat": _as_text(_first_value(raw_offer, ("contrat", "typeContratLibelle", "typeContrat", "contract"))) or None,
        "territoire": _as_text(territoire) or None,
        "date_publication": _as_text(date_publication) or None,
    }


def load_market_context(path: Union[str, Path] = DEFAULT_CONTEXT_PATH) -> pd.DataFrame:
    """Load the processed France Travail market context."""
    context_path = Path(path)
    if not context_path.exists():
        raise FileNotFoundError(
            f"Contexte marche introuvable: {context_path}. "
            "Lancez d'abord: python src/integrate_series_offres.py"
        )
    return pd.read_csv(context_path)


def load_model1_json(path: Union[str, Path]) -> pd.DataFrame:
    """Load JSON outputs produced by model 1 extraction."""
    with Path(path).open("r", encoding="utf-8") as fh:
        payload: Any = json.load(fh)
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise ValueError("Le JSON du modele 1 doit contenir un objet ou une liste d'objets.")
    return pd.json_normalize(payload)


def merge_model1_with_market_context(
    model1_outputs: pd.DataFrame,
    market_context: pd.DataFrame,
) -> pd.DataFrame:
    """Attach market context to model 1 outputs without inventing labels.

    The merge is intentionally conservative: it uses a normalized
    ``metier_context_key`` if present in model 1 outputs. Otherwise, it keeps
    the offer rows and leaves market columns empty. The future target column
    ``score_formation`` is created only as an empty placeholder.
    """
    offers = model1_outputs.copy()
    context = market_context.copy()

    if "domaine" not in context.columns:
        raise ValueError("Le contexte marche doit contenir une colonne 'domaine'.")

    context["metier_context_key"] = context["domaine"].map(normalize_text)

    if "metier_context_key" not in offers.columns:
        offers["metier_context_key"] = pd.NA
    else:
        offers["metier_context_key"] = offers["metier_context_key"].map(normalize_text)

    merged = offers.merge(
        context,
        on="metier_context_key",
        how="left",
        suffixes=("", "_marche"),
    )

    if "score_formation" not in merged.columns:
        merged["score_formation"] = pd.NA

    return merged


def prepare_model2_frame(
    model1_json_path: Union[str, Path],
    market_context_path: Union[str, Path] = DEFAULT_CONTEXT_PATH,
) -> pd.DataFrame:
    """Load model 1 JSON and market context, then return a model 2 frame."""
    model1_outputs = load_model1_json(model1_json_path)
    market_context = load_market_context(market_context_path)
    return merge_model1_with_market_context(model1_outputs, market_context)
