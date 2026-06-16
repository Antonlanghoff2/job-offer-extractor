# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""High-level prediction API for job-offer extraction.

Usage
-----
    python -m src.predict

Loads the trained pipeline from ``models/segment_classifier.joblib``,
classifies each line/segment of a raw French job offer, then applies
rule-based post-processing and extractors to produce a structured
JSON-compatible dict.

Hybrid approach
---------------
The scikit-learn pipeline provides an initial label for every segment,
but business rules (noise filtering, company detection, title cleanup,
remote normalisation) override or refine those predictions.  This keeps
the system robust on real-world offers without needing infinite
training data.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import joblib
from sklearn.pipeline import Pipeline

from src.extractors import (
    extract_company,
    extract_contract,
    extract_experience,
    extract_location,
    extract_remote,
    extract_salary,
    extract_skills,
    is_noise_segment,
    is_probable_company_name,
    normalize_remote_label,
    split_offer_into_segments,
)


MODEL_DIR = Path("models")
MODEL_PATH = MODEL_DIR / "segment_classifier.joblib"

_TITLE_APOS = str.maketrans({"’": "'", "ʼ": "'", "‘": "'"})

SAMPLE_OFFER = """Chef.fe de projet Senior – Imagerie, optique & IA - job post
R&D Vision
Saint-Maur-des-Fossés (94)
De 40 000 € à 70 000 € par an - CDI, Statut cadre, Temps plein
Expérience significative en projets techniques complexes
Lieu du poste : En présentiel
Compétences : IA, imagerie, optique, instrumentation, vision par ordinateur, traitement d'images, gestion de projet
Travail à domicile occasionnel
Anglais professionnel courant requis"""


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


def post_process_segments(
    segments_classes: List[Tuple[str, str]],
) -> List[Dict[str, str]]:
    """Clean and refine the list of labelled segments.

    * Removes segments classified as TITLE when they are actually section
      headers or company names.
    * Filters out noise segments.
    * Drops segments whose text is empty after cleaning.

    Parameters
    ----------
    segments_classes : List[Tuple[str, str]]
        Raw ``(text, label)`` pairs from the ML classifier.

    Returns
    -------
    List[Dict[str, str]]
        Cleaned segments as ``{"text": …, "label": …}`` dicts.
    """
    result: List[Dict[str, str]] = []
    for text, label in segments_classes:
        if not text.strip():
            continue
        lower = text.lower()
        if label == "TITLE":
            if is_noise_segment(text) or is_probable_company_name(text):
                label = "OTHER"
        if label in ("TITLE", "OTHER") and (
            lower.startswith("compétence")
            or lower.startswith("competence")
        ):
            label = "SKILLS"
        result.append({"text": text, "label": label})
    return result


def _clean_title(raw: str) -> str | None:
    """Apply business rules to extract a clean job title.

    * Strips the ``- job post`` / ``– job post`` suffix.
    * Normalises fancy apostrophes.
    * Returns ``None`` when the result looks like a section header,
      company name, or generic single word.
    """
    t = raw.translate(_TITLE_APOS)
    t = re.sub(r"\s*[-–]\s*job\s*post\s*$", "", t, flags=re.IGNORECASE).strip()
    if not t:
        return None
    if is_noise_segment(t):
        return None
    if is_probable_company_name(t):
        return None
    words = t.split()
    if len(words) <= 2 and t.lower() in (
        "cdi", "cdd", "stage", "freelance", "h/f", "temps plein", "urgent",
    ):
        return None
    if re.match(r"^[A-ZÀ-Œ][a-zà-ÿ]+(?:\s+\(?\d{2,3}\)?)?$", t):
        return None
    return t


def _resolve_remote(segments: List[Dict[str, str]]) -> str | None:
    """Build a canonical remote / télétravail label.

    Rules
    -----
    * ``"Travail à domicile occasionnel"`` → ``"occasionnel"``
    * ``"Lieu du poste : En présentiel"`` → ``"présentiel"``
    * If both present → ``"présentiel avec télétravail occasionnel"``
    """
    remote_labels: List[str] = []
    for seg in segments:
        raw = extract_remote(seg["text"])
        if raw is None:
            continue
        norm = normalize_remote_label(raw)
        if norm == "télétravail":
            if "occasionnel" in raw.lower():
                remote_labels.append("télétravail occasionnel")
            else:
                remote_labels.append("télétravail")
        elif norm == "présentiel":
            remote_labels.append("présentiel")

    has_presentiel = any("présentiel" in r for r in remote_labels)
    has_remote = any("télétravail" in r for r in remote_labels)

    if has_presentiel and has_remote:
        remote_detail = [r for r in remote_labels if "occasionnel" in r]
        if remote_detail:
            return "présentiel avec télétravail occasionnel"
        return "présentiel et télétravail"
    if has_presentiel:
        return "présentiel"
    if has_remote:
        occ = [r for r in remote_labels if "occasionnel" in r]
        if occ:
            return "télétravail occasionnel"
        return "télétravail"
    return None


def _find_company(
    segments: List[Dict[str, str]],
    title_idx: int | None,
) -> str | None:
    """Find the company name.

    Heuristics (tried in order)
    1. Any segment with an explicit ``Entreprise : …`` prefix.
    2. The segment immediately after the title when it looks like a
       company name.
    """
    for seg in segments:
        company = extract_company(seg["text"])
        if company:
            return company

    if title_idx is not None and title_idx + 1 < len(segments):
        next_seg = segments[title_idx + 1]["text"]
        if is_probable_company_name(next_seg):
            return next_seg
    return None


def _find_title(segments: List[Dict[str, str]]) -> tuple[str | None, int | None]:
    """Find the best job title.

    Strategy
    --------
    1. Prefer the very first non-empty segment in the offer.
    2. Fall back to the first segment labelled TITLE.
    3. Apply ``_clean_title`` to both candidates.
    """
    candidates: list[tuple[int, str]] = []

    for idx, seg in enumerate(segments):
        cleaned = _clean_title(seg["text"])
        if cleaned:
            candidates.append((idx, cleaned))
            break  # first real candidate wins

    title_idx = None
    title_text = None
    if candidates:
        title_idx, title_text = candidates[0]

    return title_text, title_idx


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
    if not segments:
        return _empty_result([])

    pipeline = load_model()
    raw_labelled = classify_segments(pipeline, segments)
    cleaned_segments = post_process_segments(raw_labelled)

    intitule_poste, title_idx = _find_title(cleaned_segments)
    entreprise = _find_company(cleaned_segments, title_idx)

    contrat: str | None = None
    salaire: str | None = None
    localisation: str | None = None
    competences: List[str] = []
    experience: str | None = None

    for seg in cleaned_segments:
        txt = seg["text"]
        label = seg["label"]

        competences.extend(extract_skills(txt))
        if contrat is None and label == "CONTRACT":
            val = extract_contract(txt)
            if val is not None:
                contrat = val
        if salaire is None and label == "SALARY":
            val = extract_salary(txt)
            if val is not None:
                salaire = val
        if experience is None and label == "EXPERIENCE":
            val = extract_experience(txt)
            if val is not None:
                experience = val
        if localisation is None and label == "LOCATION":
            val = extract_location(txt)
            if val is not None:
                localisation = val

    for seg in cleaned_segments:
        txt = seg["text"]
        if contrat is None:
            val = extract_contract(txt)
            if val is not None:
                contrat = val
        if salaire is None:
            val = extract_salary(txt)
            if val is not None:
                salaire = val
        if experience is None:
            val = extract_experience(txt)
            if val is not None:
                experience = val
        if localisation is None:
            val = extract_location(txt)
            if val is not None:
                localisation = val

    competences = list(dict.fromkeys(competences))
    teletravail = _resolve_remote(cleaned_segments)

    return {
        "intitule_poste": intitule_poste,
        "entreprise": entreprise,
        "contrat": contrat,
        "salaire": salaire,
        "localisation": localisation,
        "competences": competences,
        "experience": experience,
        "teletravail": teletravail,
        "segments_classes": cleaned_segments,
    }


def _empty_result(segments: List) -> dict:
    return {
        "intitule_poste": None,
        "entreprise": None,
        "contrat": None,
        "salaire": None,
        "localisation": None,
        "competences": [],
        "experience": None,
        "teletravail": None,
        "segments_classes": segments,
    }


def pretty_print_result(result: dict) -> None:
    """Print the extraction result in a human-friendly format."""
    print("=" * 48)
    print("  EXTRACTION RÉSULTAT")
    print("=" * 48)
    for key in ("intitule_poste", "entreprise", "contrat", "salaire", "localisation"):
        val = result.get(key)
        label = key.replace("_", " ").title()
        if val:
            print(f"  {label:<20} : {val}")
        else:
            print(f"  {label:<20} : (non trouvé)")
    print(
        f"  {'Compétences':<20} : "
        f"{', '.join(result.get('competences', [])) or '(non trouvé)'}"
    )
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
