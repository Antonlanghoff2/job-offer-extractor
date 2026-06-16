# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""High-level prediction API."""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from typing import Dict, List, Tuple

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.feature_extraction.text import TfidfVectorizer

from src.extractors import extract_all
from src.feature_extraction import build_feature_matrix
from src.preprocessing import clean_text, segment_offer


def load_models(model_dir: str = "models") -> Tuple[
    TfidfVectorizer, LogisticRegression, np.ndarray
]:
    """Load persisted vectorizer, classifier, and class labels.

    Parameters
    ----------
    model_dir : str
        Directory containing the `.joblib` files.

    Returns
    -------
    vectorizer : TfidfVectorizer
    classifier : LogisticRegression
    classes : np.ndarray
    """
    vectorizer = joblib.load(os.path.join(model_dir, "vectorizer.joblib"))
    classifier = joblib.load(os.path.join(model_dir, "classifier.joblib"))
    classes = joblib.load(os.path.join(model_dir, "classes.joblib"))
    return vectorizer, classifier, classes


def predict_segments(
    segments: List[str],
    vectorizer: TfidfVectorizer,
    classifier: LogisticRegression,
    classes: np.ndarray,
) -> List[Tuple[str, str]]:
    """Classify each segment and return (text, label) pairs.

    Parameters
    ----------
    segments : List[str]
        Cleaned text segments.
    vectorizer : TfidfVectorizer
        Fitted vectorizer.
    classifier : LogisticRegression
        Trained classifier.
    classes : np.ndarray
        Sorted label array.

    Returns
    -------
    List[Tuple[str, str]]
        List of ``(segment_text, predicted_label)`` tuples.
    """
    X = build_feature_matrix(vectorizer, segments)
    preds = classifier.predict(X)
    return list(zip(segments, preds))


def predict_offer(raw_offer: str, model_dir: str = "models") -> Dict[str, object]:
    """Run the full prediction pipeline on a raw job offer text.

    Parameters
    ----------
    raw_offer : str
        Full job offer text.
    model_dir : str
        Directory with persisted model artifacts.

    Returns
    -------
    Dict[str, object]
        Structured extraction result (see ``extractors.extract_all``).
    """
    vectorizer, classifier, classes = load_models(model_dir)
    segments = segment_offer(raw_offer)
    labelled = predict_segments(segments, vectorizer, classifier, classes)

    grouped: Dict[str, List[str]] = defaultdict(list)
    for text, label in labelled:
        grouped[label].append(text)

    result = extract_all(dict(grouped))
    result["_segments"] = labelled
    return result


def predict_from_file(filepath: str, model_dir: str = "models") -> Dict[str, object]:
    """Read a job offer from a text file and extract information.

    Parameters
    ----------
    filepath : str
        Path to the job-offer text file.
    model_dir : str
        Model directory.

    Returns
    -------
    Dict[str, object]
        Extraction result.
    """
    with open(filepath, "r", encoding="utf-8") as fh:
        raw = fh.read()
    return predict_offer(raw, model_dir=model_dir)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract structured info from a French job offer"
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="data/sample_offers.txt",
        help="Path to job-offer text file",
    )
    parser.add_argument(
        "--model-dir",
        default="models",
        help="Directory with trained model artifacts",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output",
    )
    args = parser.parse_args()

    result = predict_from_file(args.input, model_dir=args.model_dir)
    indent = 2 if args.pretty else None
    print(json.dumps(result, ensure_ascii=False, indent=indent))


if __name__ == "__main__":
    main()
