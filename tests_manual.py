# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Manual tests for the job-offer extractor.

Usage
-----
    python tests_manual.py

Runs extraction on both built-in sample offers and compares
the output against the expected JSON.
"""

from __future__ import annotations

import json
from src.predict import (
    extract_job_offer,
    SAMPLE_OFFER,
    SAMPLE_OFFER_DENTIST,
    SAMPLE_OFFER_MONTBRISON,
)


EXPECTED_RD = {
    "numero_offre": None,
    "intitule_poste": "Chef.fe de projet Senior – Imagerie, optique & IA",
    "salaires": ["40 000 € à 70 000 €"],
    "lieux_embauche": ["Saint-Maur-des-Fossés (94)"],
    "distanciel": "hybride",
    "competences_requises": [
        "IA", "intelligence artificielle", "imagerie", "optique",
        "instrumentation", "vision", "traitement d'images",
        "gestion de projet", "anglais professionnel",
    ],
    "contacts": [],
}

EXPECTED_DENTIST = {
    "numero_offre": None,
    "intitule_poste": "Chirurgien-Dentiste",
    "salaires": ["27% et 30% bruts/mois", "3500€/mois"],
    "lieux_embauche": ["Loire-Atlantique - 44", "Nantes", "Nantes, 44000"],
    "distanciel": None,
    "competences_requises": [
        "diplôme de chirurgien-dentiste",
        "omnipraticien",
        "plateau technique",
        "assistante dentaire",
        "réglementation médicale",
        "langue française",
        "démarches administratives",
    ],
    "contacts": ["06 24 40 01 67"],
}

EXPECTED_MONTBRISON = {
    "numero_offre": None,
    "intitule_poste": None,
    "salaires": ["1 002,00€ par mois"],
    "lieux_embauche": ["42600 Montbrison"],
    "distanciel": "présentiel",
    "competences_requises": [
        "data",
        "développement",
        "analyse",
        "sécurité informatique",
        "informatique",
        "protection des données",
    ],
    "contacts": [],
}


def _normalise(result: dict) -> dict:
    """Sort list fields for comparison."""
    out = {}
    for k, v in result.items():
        if isinstance(v, list):
            out[k] = sorted(v)
        else:
            out[k] = v
    return out


def test(name: str, result: dict, expected: dict) -> None:
    ok = _normalise(result) == _normalise(expected)
    print(f"{'✅' if ok else '❌'} {name}")
    if not ok:
        print(f"  Got:      {json.dumps(result, ensure_ascii=False)}")
        print(f"  Expected: {json.dumps(expected, ensure_ascii=False)}")


def main() -> None:
    test("R&D Vision", extract_job_offer(SAMPLE_OFFER), EXPECTED_RD)
    test("Dentiste", extract_job_offer(SAMPLE_OFFER_DENTIST), EXPECTED_DENTIST)
    test("Montbrison", extract_job_offer(SAMPLE_OFFER_MONTBRISON), EXPECTED_MONTBRISON)


if __name__ == "__main__":
    main()
