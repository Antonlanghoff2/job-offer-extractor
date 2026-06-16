# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Evaluation utilities for the segment classifier."""

from __future__ import annotations

import argparse
import json
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    f1_score,
)

from src.feature_extraction import build_vectorizer, prepare_data


def evaluate_model(
    csv_path: str = "data/train_segments.csv",
    cv_folds: int = 5,
) -> None:
    """Train and cross-validate, then print detailed metrics.

    Parameters
    ----------
    csv_path : str
        Path to labelled CSV.
    cv_folds : int
        Number of cross-validation folds.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold

    vectorizer = build_vectorizer()
    X, y, classes = prepare_data(csv_path, vectorizer)

    clf = LogisticRegression(
        C=1.0,
        solver="lbfgs",
        max_iter=500,
        random_state=42,
    )

    skf = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=42)
    all_y_true: List[str] = []
    all_y_pred: List[str] = []

    for train_idx, test_idx in skf.split(X, y):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]
        clf.fit(X_train, y_train)
        preds = clf.predict(X_test)
        all_y_true.extend(y_test)
        all_y_pred.extend(preds)

    print("\n=== Classification Report ===\n")
    print(classification_report(all_y_true, all_y_pred, labels=classes))

    cm = confusion_matrix(all_y_true, all_y_pred, labels=classes)
    cm_df = pd.DataFrame(cm, index=classes, columns=classes)
    print("=== Confusion Matrix ===\n")
    print(cm_df)

    macro = f1_score(all_y_true, all_y_pred, average="macro")
    weighted = f1_score(all_y_true, all_y_pred, average="weighted")
    print(f"\nMacro   F1 : {macro:.4f}")
    print(f"Weighted F1 : {weighted:.4f}")


def predict_on_csv(
    csv_path: str,
    model_dir: str = "models",
) -> List[Tuple[str, str, str]]:
    """Run prediction on a CSV and return (text, true_label, pred_label) rows.

    Parameters
    ----------
    csv_path : str
        Path to CSV with ``text`` and ``label`` columns.
    model_dir : str
        Directory with persisted artifacts.

    Returns
    -------
    List[Tuple[str, str, str]]
        Triplets for each row.
    """
    import joblib
    from src.feature_extraction import build_feature_matrix

    vectorizer = joblib.load(f"{model_dir}/vectorizer.joblib")
    classifier = joblib.load(f"{model_dir}/classifier.joblib")
    classes = joblib.load(f"{model_dir}/classes.joblib")

    df = pd.read_csv(csv_path)
    X = build_feature_matrix(vectorizer, df["text"].tolist())
    preds = classifier.predict(X)

    rows: List[Tuple[str, str, str]] = []
    for text, true, pred in zip(df["text"], df["label"], preds):
        rows.append((text, true, pred))
    return rows


def compare_datasets(filepath: str, actual_path: str) -> None:
    """Run evaluation on separate test set and report metrics."""
    rows = predict_on_csv(filepath)
    y_true = [r[1] for r in rows]
    y_pred = [r[2] for r in rows]
    classes = sorted(set(y_true))

    print("\n=== Evaluation on test set ===\n")
    print(classification_report(y_true, y_pred, labels=classes))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate segment classifier")
    parser.add_argument(
        "--csv",
        default="data/train_segments.csv",
        help="Path to labelled CSV",
    )
    parser.add_argument(
        "--cv-folds",
        type=int,
        default=5,
        help="Number of cross-validation folds",
    )
    args = parser.parse_args()
    evaluate_model(csv_path=args.csv, cv_folds=args.cv_folds)
