# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""
Training pipeline for the segment classifier.

Usage
-----
    python -m src.train_classifier

Reads ``data/train_segments.csv``, trains a logistic-regression pipeline
with TF‑IDF features, and persists the model to ``models/segment_classifier.joblib``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Tuple

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline


DATA_DIR = Path("data")
MODEL_DIR = Path("models")
DEFAULT_CSV = DATA_DIR / "train_segments.csv"
MODEL_PATH = MODEL_DIR / "segment_classifier.joblib"

RANDOM_STATE = 42
TEST_SIZE = 0.2


def load_dataset(csv_path: str = str(DEFAULT_CSV)) -> Tuple[pd.DataFrame, pd.Series]:
    """Load text and labels from the training CSV.

    Parameters
    ----------
    csv_path : str
        Path to the CSV file with ``text`` and ``label`` columns.

    Returns
    -------
    X : pd.DataFrame
        Texts.
    y : pd.Series
        Labels.
    """
    if not os.path.isfile(csv_path):
        print(f"Error: training file not found at '{csv_path}'", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(csv_path)
    if "text" not in df.columns or "label" not in df.columns:
        print(
            "Error: CSV must contain 'text' and 'label' columns",
            file=sys.stderr,
        )
        sys.exit(1)

    return df["text"], df["label"]


def train_model(
    X: pd.DataFrame,
    y: pd.Series,
) -> Tuple[Pipeline, pd.DataFrame, pd.Series, pd.Series]:
    """Build, train and return a scikit-learn pipeline.

    Splits the data into train/test sets, creates a ``Pipeline`` with
    ``TfidfVectorizer`` + ``LogisticRegression``, fits it, and returns
    the fitted pipeline together with the test split for later evaluation.

    Parameters
    ----------
    X : pd.DataFrame
        Texts.
    y : pd.Series
        Labels.

    Returns
    -------
    pipeline : Pipeline
        Fitted pipeline.
    X_test : pd.DataFrame
        Test texts.
    y_test : pd.Series
        True test labels.
    y_pred : pd.Series
        Predicted test labels.
    """
    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size=TEST_SIZE,
        random_state=RANDOM_STATE,
        stratify=y,
    )

    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2))),
        ("clf", LogisticRegression(max_iter=1000, random_state=RANDOM_STATE)),
    ])

    pipeline.fit(X_train, y_train)
    y_pred = pipeline.predict(X_test)

    return pipeline, X_test, y_test, y_pred


def evaluate_model(
    y_test: pd.Series,
    y_pred: pd.Series,
    target_names: list[str] | None = None,
) -> None:
    """Print a scikit-learn classification report.

    Parameters
    ----------
    y_test : pd.Series
        True labels.
    y_pred : pd.Series
        Predicted labels.
    target_names : list[str] | None
        Optional label ordering.
    """
    print("\n=== Classification Report ===\n")
    print(classification_report(y_test, y_pred, target_names=target_names))


def save_model(pipeline: Pipeline, path: str = str(MODEL_PATH)) -> None:
    """Persist the fitted pipeline to disk with ``joblib``.

    Parameters
    ----------
    pipeline : Pipeline
        Fitted scikit-learn pipeline.
    path : str
        Destination path.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    joblib.dump(pipeline, path)
    print(f"Model saved to '{path}'")


def main() -> None:
    X, y = load_dataset()
    pipeline, X_test, y_test, y_pred = train_model(X, y)
    evaluate_model(y_test, y_pred, target_names=sorted(y.unique()))
    save_model(pipeline)


if __name__ == "__main__":
    main()
