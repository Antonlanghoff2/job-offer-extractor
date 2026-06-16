# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Training pipeline for the segment classifier."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Tuple

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score

from src.feature_extraction import build_vectorizer, prepare_data


def train(
    csv_path: str = "data/train_segments.csv",
    model_dir: str = "models",
    cv_folds: int = 5,
) -> Tuple[LogisticRegression, np.ndarray]:
    """Train a multiclass segment classifier.

    This uses a ``LogisticRegression`` (one-vs-rest) with TF‑IDF + custom
    hand-crafted features.

    Parameters
    ----------
    csv_path : str
        Path to training CSV.
    model_dir : str
        Directory where the fitted vectorizer and classifier are persisted.
    cv_folds : str
        Number of cross-validation folds.

    Returns
    -------
    clf : LogisticRegression
        Fitted classifier.
    class_labels : np.ndarray
        Unique class labels in training order.
    """
    vectorizer = build_vectorizer()
    X, y, classes = prepare_data(csv_path, vectorizer)

    clf = LogisticRegression(
        C=1.0,
        solver="lbfgs",
        max_iter=500,
        random_state=42,
    )

    scores = cross_val_score(clf, X, y, cv=cv_folds, scoring="f1_macro")
    print(f"Cross-validation F1 (macro): {scores.mean():.3f} ± {scores.std():.3f}")

    clf.fit(X, y)

    os.makedirs(model_dir, exist_ok=True)
    joblib.dump(vectorizer, os.path.join(model_dir, "vectorizer.joblib"))
    joblib.dump(clf, os.path.join(model_dir, "classifier.joblib"))
    joblib.dump(classes, os.path.join(model_dir, "classes.joblib"))
    print(f"Models saved to '{model_dir}/'")

    return clf, classes


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train segment classifier")
    parser.add_argument(
        "--csv",
        default="data/train_segments.csv",
        help="Path to training CSV",
    )
    parser.add_argument(
        "--model-dir",
        default="models",
        help="Where to save trained artifacts",
    )
    parser.add_argument(
        "--cv-folds",
        type=int,
        default=5,
        help="Number of cross-validation folds",
    )
    args = parser.parse_args()
    train(csv_path=args.csv, model_dir=args.model_dir, cv_folds=args.cv_folds)
