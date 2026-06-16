# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Evaluation script for the segment classifier.

Usage
-----
    python -m src.evaluate

Loads ``models/segment_classifier.joblib``, reproduces the same
train/test split used by ``train_classifier.py``, prints per-class
and overall metrics, and writes a report to
``models/evaluation_report.txt``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Tuple

import joblib
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline


DATA_DIR = Path("data")
MODEL_DIR = Path("models")
DEFAULT_CSV = DATA_DIR / "train_segments.csv"
MODEL_PATH = MODEL_DIR / "segment_classifier.joblib"
REPORT_PATH = MODEL_DIR / "evaluation_report.txt"

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
        print(f"Error: evaluation file not found at '{csv_path}'", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(csv_path)
    if "text" not in df.columns or "label" not in df.columns:
        print(
            "Error: CSV must contain 'text' and 'label' columns",
            file=sys.stderr,
        )
        sys.exit(1)

    return df["text"], df["label"]


def load_model(path: str = str(MODEL_PATH)) -> Pipeline:
    """Load the trained scikit-learn pipeline.

    Parameters
    ----------
    path : str
        Path to the ``.joblib`` file.

    Returns
    -------
    Pipeline
        Fitted pipeline.
    """
    if not os.path.isfile(path):
        print(f"Error: model not found at '{path}'", file=sys.stderr)
        print("Run 'python -m src.train_classifier' first.", file=sys.stderr)
        sys.exit(1)
    return joblib.load(path)


def evaluate() -> None:
    """Run the full evaluation workflow."""
    X, y = load_dataset()

    pipeline = load_model()

    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size=TEST_SIZE,
        random_state=RANDOM_STATE,
        stratify=y,
    )

    y_pred = pipeline.predict(X_test)

    labels = sorted(y.unique())

    print("\n=== Classification Report ===\n")
    print(classification_report(y_test, y_pred, labels=labels, digits=4))

    acc = accuracy_score(y_test, y_pred)
    prec_macro = precision_score(y_test, y_pred, labels=labels, average="macro", zero_division=0)
    prec_weighted = precision_score(y_test, y_pred, labels=labels, average="weighted", zero_division=0)
    rec_macro = recall_score(y_test, y_pred, labels=labels, average="macro", zero_division=0)
    rec_weighted = recall_score(y_test, y_pred, labels=labels, average="weighted", zero_division=0)
    f1_macro = f1_score(y_test, y_pred, labels=labels, average="macro", zero_division=0)
    f1_weighted = f1_score(y_test, y_pred, labels=labels, average="weighted", zero_division=0)

    print("=== Aggregated Metrics ===\n")
    print(f"  Accuracy             : {acc:.4f}")
    print(f"  Precision (macro)    : {prec_macro:.4f}")
    print(f"  Precision (weighted) : {prec_weighted:.4f}")
    print(f"  Recall (macro)       : {rec_macro:.4f}")
    print(f"  Recall (weighted)    : {rec_weighted:.4f}")
    print(f"  F1-score (macro)     : {f1_macro:.4f}")
    print(f"  F1-score (weighted)  : {f1_weighted:.4f}")

    cm = confusion_matrix(y_test, y_pred, labels=labels)
    cm_df = pd.DataFrame(cm, index=labels, columns=labels)

    print("\n=== Confusion Matrix ===\n")
    print(cm_df.to_string())

    lines: list[str] = []
    lines.append("=" * 56)
    lines.append("  EVALUATION REPORT — Segment Classifier")
    lines.append("=" * 56)
    lines.append("")
    lines.append(f"  Model        : {MODEL_PATH}")
    lines.append(f"  Data         : {DEFAULT_CSV}")
    lines.append(f"  Samples      : {len(X)}")
    lines.append(f"  Test size    : {TEST_SIZE}")
    lines.append(f"  Test samples : {len(y_test)}")
    lines.append(f"  Classes      : {len(labels)}")
    lines.append("")
    lines.append("-" * 56)
    lines.append("  Per-class metrics")
    lines.append("-" * 56)
    lines.append("")
    lines.append(classification_report(y_test, y_pred, labels=labels, digits=4))
    lines.append("-" * 56)
    lines.append("  Aggregated metrics")
    lines.append("-" * 56)
    lines.append("")
    lines.append(f"  Accuracy             : {acc:.4f}")
    lines.append(f"  Precision (macro)    : {prec_macro:.4f}")
    lines.append(f"  Precision (weighted) : {prec_weighted:.4f}")
    lines.append(f"  Recall (macro)       : {rec_macro:.4f}")
    lines.append(f"  Recall (weighted)    : {rec_weighted:.4f}")
    lines.append(f"  F1-score (macro)     : {f1_macro:.4f}")
    lines.append(f"  F1-score (weighted)  : {f1_weighted:.4f}")
    lines.append("")
    lines.append("-" * 56)
    lines.append("  Confusion matrix")
    lines.append("-" * 56)
    lines.append("")
    for line in cm_df.to_string().split("\n"):
        lines.append(f"  {line}")
    lines.append("")
    lines.append("=" * 56)

    report = "\n".join(lines)

    os.makedirs(MODEL_DIR, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write(report)

    print(f"\nReport saved to '{REPORT_PATH}'")


if __name__ == "__main__":
    evaluate()
