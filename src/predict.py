# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""High-level prediction API for job-offer extraction.

Usage
-----
    python -m src.predict

Loads the trained pipeline from ``models/segment_classifier.joblib``,
classifies each line/segment of a raw French job offer, then applies
rule-based post-processing and extractors to produce a structured
JSON-compatible dict with the following fields:

- ``numero_offre``     – reference number
- ``intitule_poste``   – cleaned job title
- ``salaires``         – all detected salary mentions
- ``lieux_embauche``   – all detected hiring locations
- ``distanciel``       – canonical remote / on-site label
- ``competences_requises`` – deduplicated list of recognised skills
- ``contacts``         – emails, phone numbers, application URLs
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
    deduplicate_keep_order,
    extract_contacts,
    extract_hiring_locations,
    extract_offer_number,
    extract_remote_mode,
    extract_required_skills,
    extract_salaries,
    is_noise_segment,
    is_probable_company_name,
    resolve_remote,
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
    * Reclassifies ``Compétences : …`` lines to SKILLS.
    * Drops empty-text segments.

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
    * Removes ``(H/F)``, ``H/F``, ``F/H``, ``M/F`` trailing markers.
    * Normalises fancy apostrophes.
    * Returns ``None`` when the result looks like a section header,
      company name, or generic single word.
    """
    t = raw.translate(_TITLE_APOS)
    t = re.sub(r"\s*[-–]\s*job\s*post\s*$", "", t, flags=re.IGNORECASE).strip()
    t = re.sub(r"\s*[\(\)]*[HFM]/[HFM][\)]*\s*$", "", t).strip()
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


def _find_title(segments: List[str]) -> str | None:
    """Find the best job title from a list of cleaned segments.

    Strategy
    --------
    Pick the first segment that passes ``_clean_title``.
    """
    for seg in segments:
        cleaned = _clean_title(seg)
        if cleaned:
            return cleaned
    return None


def extract_job_offer(text: str, debug: bool = False) -> dict:
    """Extract structured information from a raw French job-offer text.

    Parameters
    ----------
    text : str
        Raw job-offer text.
    debug : bool
        When ``True``, include the ``segments_classes`` entry in the result.

    Returns
    -------
    dict
        JSON-compatible dictionary with the extracted fields.
    """
    segments = split_offer_into_segments(text)
    if not segments:
        return _empty_result()

    pipeline = load_model()
    raw_labelled = classify_segments(pipeline, segments)
    cleaned_segments = post_process_segments(raw_labelled)

    # ── numero_offre ────────────────────────────────────────────────
    numero_offre: str | None = None
    for seg in cleaned_segments:
        val = extract_offer_number(seg["text"])
        if val is not None:
            numero_offre = val
            break

    # ── intitule_poste ──────────────────────────────────────────────
    intitule_poste = _find_title(segments)

    # ── salaires ────────────────────────────────────────────────────
    salaires: List[str] = []
    for seg in cleaned_segments:
        salaires.extend(extract_salaries(seg["text"]))
    salaires = deduplicate_keep_order(salaires)

    # ── lieux_embauche ──────────────────────────────────────────────
    lieux_embauche: List[str] = []
    for seg in cleaned_segments:
        lieux_embauche.extend(extract_hiring_locations(seg["text"]))
    lieux_embauche = deduplicate_keep_order(lieux_embauche)

    # ── distanciel ──────────────────────────────────────────────────
    segment_modes: List[str | None] = []
    for seg in cleaned_segments:
        segment_modes.append(extract_remote_mode(seg["text"]))
    distanciel = resolve_remote(segment_modes)

    # ── competences_requises ────────────────────────────────────────
    competences_requises: List[str] = []
    for seg in cleaned_segments:
        competences_requises.extend(extract_required_skills(seg["text"]))
    competences_requises = deduplicate_keep_order(competences_requises)

    # ── contacts ────────────────────────────────────────────────────
    contacts: List[str] = []
    for seg in cleaned_segments:
        contacts.extend(extract_contacts(seg["text"]))
    contacts = deduplicate_keep_order(contacts)

    result: dict = {
        "numero_offre": numero_offre,
        "intitule_poste": intitule_poste,
        "salaires": salaires,
        "lieux_embauche": lieux_embauche,
        "distanciel": distanciel,
        "competences_requises": competences_requises,
        "contacts": contacts,
    }

    if debug:
        result["segments_classes"] = cleaned_segments

    return result


def _empty_result() -> dict:
    return {
        "numero_offre": None,
        "intitule_poste": None,
        "salaires": [],
        "lieux_embauche": [],
        "distanciel": None,
        "competences_requises": [],
        "contacts": [],
    }


def pretty_print_result(result: dict) -> None:
    """Print the extraction result in a human-friendly format."""
    print("=" * 48)
    print("  EXTRACTION RÉSULTAT")
    print("=" * 48)
    for key in (
        "numero_offre", "intitule_poste", "distanciel",
    ):
        val = result.get(key)
        label = key.replace("_", " ").title()
        print(f"  {label:<22} : {val or '(non trouvé)'}")
    for key in ("salaires", "lieux_embauche", "competences_requises", "contacts"):
        val = result.get(key, [])
        label = key.replace("_", " ").title()
        display = ", ".join(val) if val else "(non trouvé)"
        print(f"  {label:<22} : {display}")

    if "segments_classes" in result:
        print("-" * 48)
        print("  Segments classés (debug) :")
        for seg in result["segments_classes"]:
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

    debug = "--debug" in sys.argv
    result = extract_job_offer(offer, debug=debug)
    pretty_print_result(result)
    print()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
