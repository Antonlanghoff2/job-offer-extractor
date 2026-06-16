# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""High-level prediction API for job-offer extraction.

Usage
-----
    python -m src.predict

Loads the trained pipeline from ``models/segment_classifier.joblib``,
classifies each line/segment of a raw French job offer, then applies
rule-based extractors to produce a structured JSON-compatible dict.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import List, Tuple

import joblib
from sklearn.pipeline import Pipeline

from src.extractors import (
    extract_contract,
    extract_experience,
    extract_location,
    extract_remote,
    extract_salary,
    extract_skills,
    split_offer_into_segments,
)


MODEL_DIR = Path("models")
MODEL_PATH = MODEL_DIR / "segment_classifier.joblib"

SAMPLE_OFFER = """Développeur Full Stack H/F
CDI temps plein
Poste basé à Paris
Salaire entre 45k€ et 55k€ selon profil
Compétences : Python, Django, PostgreSQL, Docker
3 ans d'expérience minimum en développement web
Télétravail partiel possible
Avantages : Mutuelle, tickets restaurants, CE"""


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


def classify_segments(
    pipeline: Pipeline,
    segments: List[str],
) -> List[Tuple[str, str]]:
    """Classify each text segment with the trained pipeline.

    Parameters
    ----------
    pipeline : Pipeline
        Fitted sklearn pipeline.
    segments : List[str]
        List of cleaned text segments.

    Returns
    -------
    List[Tuple[str, str]]
        ``(segment_text, predicted_label)`` pairs.
    """
    preds = pipeline.predict(segments)
    return list(zip(segments, preds))


def extract_job_offer(text: str) -> dict:
    """Extract structured information from a raw French job-offer text.

    Parameters
    ----------
    text : str
        Raw job-offer text.

    Returns
    -------
    dict
        JSON-compatible dictionary with the extracted fields.
    """
    segments = split_offer_into_segments(text)

    pipeline = load_model()
    labelled = classify_segments(pipeline, segments)

    intitule_poste: str | None = None
    contrat: str | None = None
    salaire: str | None = None
    localisation: str | None = None
    competences: List[str] = []
    experience: str | None = None
    teletravail: str | None = None

    for seg_text, label in labelled:
        if label == "TITLE" and intitule_poste is None:
            intitule_poste = seg_text

    for seg_text, label in labelled:
        if label == "SKILLS":
            competences.extend(extract_skills(seg_text))

    competences = sorted(set(competences))

    for seg_text, label in labelled:
        if contrat is None and label == "CONTRACT":
            val = extract_contract(seg_text)
            if val is not None:
                contrat = val

        if salaire is None and label == "SALARY":
            val = extract_salary(seg_text)
            if val is not None:
                salaire = val

        if experience is None and label == "EXPERIENCE":
            val = extract_experience(seg_text)
            if val is not None:
                experience = val

        if teletravail is None and label == "REMOTE":
            val = extract_remote(seg_text)
            if val is not None:
                teletravail = val

        if localisation is None and label == "LOCATION":
            val = extract_location(seg_text)
            if val is not None:
                localisation = val

    for seg_text, _ in labelled:
        if contrat is None:
            val = extract_contract(seg_text)
            if val is not None:
                contrat = val
        if salaire is None:
            val = extract_salary(seg_text)
            if val is not None:
                salaire = val
        if experience is None:
            val = extract_experience(seg_text)
            if val is not None:
                experience = val
        if teletravail is None:
            val = extract_remote(seg_text)
            if val is not None:
                teletravail = val
        if localisation is None:
            val = extract_location(seg_text)
            if val is not None:
                localisation = val

    return {
        "intitule_poste": intitule_poste,
        "contrat": contrat,
        "salaire": salaire,
        "localisation": localisation,
        "competences": competences,
        "experience": experience,
        "teletravail": teletravail,
        "segments_classes": [
            {"text": t, "label": l} for t, l in labelled
        ],
    }


def pretty_print_result(result: dict) -> None:
    """Print the extraction result in a human-friendly format."""
    print("=" * 48)
    print("  EXTRACTION RÉSULTAT")
    print("=" * 48)
    for key in ("intitule_poste", "contrat", "salaire", "localisation"):
        val = result.get(key)
        label = key.replace("_", " ").title()
        if val:
            print(f"  {label:<20} : {val}")
        else:
            print(f"  {label:<20} : (non trouvé)")
    print(f"  {'Compétences':<20} : {', '.join(result.get('competences', [])) or '(non trouvé)'}")
    for key in ("experience", "teletravail"):
        val = result.get(key)
        label = key.replace("_", " ").title()
        if val:
            print(f"  {label:<20} : {val}")
        else:
            print(f"  {label:<20} : (non trouvé)")
    print("-" * 48)
    print("  Segments classés :")
    for seg in result.get("segments_classes", []):
        print(f"    [{seg['label']:>12}] {seg['text']}")
    print("=" * 48)


def main() -> None:
    offer = SAMPLE_OFFER
    if len(sys.argv) > 1 and sys.argv[1] != "-":
        filepath = sys.argv[1]
        try:
            with open(filepath, "r", encoding="utf-8") as fh:
                offer = fh.read()
        except FileNotFoundError:
            print(f"Error: file not found '{filepath}'", file=sys.stderr)
            sys.exit(1)
    elif len(sys.argv) > 1 and sys.argv[1] == "-":
        offer = sys.stdin.read()

    result = extract_job_offer(offer)
    pretty_print_result(result)
    print()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
