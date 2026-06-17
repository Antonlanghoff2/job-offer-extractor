# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Prepare model 1 outputs with market context for a future model 2."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

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


def load_market_context(path: str | Path = DEFAULT_CONTEXT_PATH) -> pd.DataFrame:
    """Load the processed France Travail market context."""
    context_path = Path(path)
    if not context_path.exists():
        raise FileNotFoundError(
            f"Contexte marche introuvable: {context_path}. "
            "Lancez d'abord: python src/integrate_series_offres.py"
        )
    return pd.read_csv(context_path)


def load_model1_json(path: str | Path) -> pd.DataFrame:
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
    model1_json_path: str | Path,
    market_context_path: str | Path = DEFAULT_CONTEXT_PATH,
) -> pd.DataFrame:
    """Load model 1 JSON and market context, then return a model 2 frame."""
    model1_outputs = load_model1_json(model1_json_path)
    market_context = load_market_context(market_context_path)
    return merge_model1_with_market_context(model1_outputs, market_context)
