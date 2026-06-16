# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Feature extraction: TF‑IDF vectorisation and custom feature engineering."""

from __future__ import annotations

from typing import List, Tuple

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

from src.preprocessing import clean_text


# Common French stop words for job offers (kept short — no domain terms).
_BASE_STOP_WORDS = frozenset(
    {
        "le", "la", "les", "de", "du", "des", "un", "une", "dans", "pour",
        "par", "sur", "avec", "est", "sont", "nous", "vous", "qui", "que",
        "pas", "plus", "très", "aux", "ces", "ses", "cet", "cette", "ce",
        "et", "ou", "mais", "donc", "car", "ni", "en", "au", "aux",
        "leur", "leurs", "lui", "elle", "ils", "elles", "mon", "ton",
        "son", "mes", "tes", "ses", "nos", "vos", "des",
    }
)


def build_vectorizer(
    max_features: int = 2500,
    ngram_range: Tuple[int, int] = (1, 3),
    min_df: int = 1,
) -> TfidfVectorizer:
    """Build a TF‑IDF vectorizer tuned for French job-offer segments.

    Parameters
    ----------
    max_features : int
        Maximum vocabulary size.
    ngram_range : tuple (min_n, max_n)
        Range of n-grams.
    min_df : int
        Minimum document frequency.

    Returns
    -------
    TfidfVectorizer
        Configured vectorizer (call ``fit_transform`` on training data).
    """
    return TfidfVectorizer(
        max_features=max_features,
        ngram_range=ngram_range,
        min_df=min_df,
        stop_words=list(_BASE_STOP_WORDS),
        lowercase=True,
        sublinear_tf=True,
    )


def _has_digit(text: str) -> bool:
    return any(ch.isdigit() for ch in text)


def _has_currency(text: str) -> bool:
    return "€" in text or "k€" in text or "k" in text.lower()


def _length_bucket(text: str) -> int:
    length = len(text.split())
    if length <= 3:
        return 0
    if length <= 8:
        return 1
    return 2


def _starts_with_keyword(text: str) -> bool:
    keywords = {"titre", "poste", "salaire", "localisation", "compétences",
                "contrat", "expérience", "télétravail"}
    first = text.strip().split()[0].lower() if text.strip() else ""
    return 1 if first in keywords else 0


def build_feature_matrix(
    vectorizer: TfidfVectorizer,
    texts: List[str],
) -> np.ndarray:
    """Build the combined feature matrix (TF‑IDF + hand-crafted features).

    Parameters
    ----------
    vectorizer : TfidfVectorizer
        Fitted vectorizer.
    texts : List[str]
        List of cleaned text segments.

    Returns
    -------
    np.ndarray
        Feature matrix of shape (n_samples, n_features).
    """
    cleaned = [clean_text(t) for t in texts]
    tfidf = vectorizer.transform(cleaned)

    extra_features = []
    for text in cleaned:
        extra_features.append([
            _has_digit(text),
            _has_currency(text),
            _length_bucket(text),
            _starts_with_keyword(text),
        ])

    extra_arr = np.array(extra_features, dtype=np.float64)
    return np.hstack([tfidf.toarray(), extra_arr])


def prepare_data(
    csv_path: str,
    vectorizer: TfidfVectorizer,
) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """Load labelled CSV and return feature matrix + labels.

    Parameters
    ----------
    csv_path : str
        Path to ``train_segments.csv``.
    vectorizer : TfidfVectorizer
        Vectorizer (will be **fit** to the data).

    Returns
    -------
    X : np.ndarray
        Feature matrix.
    y : np.ndarray
        Label array.
    classes : List[str]
        Sorted list of unique class names.
    """
    df = pd.read_csv(csv_path)
    df["text"] = df["text"].apply(clean_text)
    X_tfidf = vectorizer.fit_transform(df["text"])

    extra_features = []
    for text in df["text"]:
        extra_features.append([
            _has_digit(text),
            _has_currency(text),
            _length_bucket(text),
            _starts_with_keyword(text),
        ])

    extra_arr = np.array(extra_features, dtype=np.float64)
    X = np.hstack([X_tfidf.toarray(), extra_arr])

    classes = sorted(df["label"].unique())
    y = df["label"].values
    return X, y, classes
