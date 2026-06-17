# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import sys

from src.predict import extract_job_offer
from collections import Counter
import json
import re
from pathlib import Path

COMPETENCES = [
    "Python", "SQL", "JavaScript", "FastAPI", "Django",
    "Machine Learning", "Deep Learning", "NLP", "LLM",
    "RAG", "LangChain", "OpenAI", "Hugging Face",
    "PyTorch", "TensorFlow", "Scikit-learn",
    "Docker", "Kubernetes", "MLOps", "Git", "Linux"
]


def detect_competences(text: str) -> list[str]:
    text = text.lower()
    found = []

    for competence in COMPETENCES:
        pattern = r"\b" + re.escape(competence.lower()) + r"\b"
        if re.search(pattern, text):
            found.append(competence)

    return found


def detect_niveau(text: str) -> str:
    text = text.lower()

    if any(w in text for w in ["junior", "débutant", "debutant", "0 à 2 ans", "0-2 ans"]):
        return "junior"

    if any(w in text for w in ["senior", "expert", "lead", "confirmé", "confirme", "5 ans"]):
        return "senior"

    if any(w in text for w in ["3 ans", "4 ans", "2 à 5 ans"]):
        return "intermediaire"

    return "non_precise"


def get_lieu(offre: dict) -> str:
    lieu = offre.get("lieuTravail", {})
    if isinstance(lieu, dict):
        return lieu.get("commune") or lieu.get("libelle") or "non_precise"
    return "non_precise"


def analyser_tendances():
    input_path = Path("data/raw/offres_france_travail.json")
    output_path = Path("data/processed/tendances.json")

    with input_path.open("r", encoding="utf-8") as f:
        offres = json.load(f)

    competences = Counter()
    metiers = Counter()
    territoires = Counter()
    niveaux = Counter()

    for offre in offres:
        intitule = offre.get("intitule", "")
        description = offre.get("description", "")
        rome = offre.get("romeLibelle", "")

        texte = f"{intitule} {description} {rome}"

        competences.update(detect_competences(texte))
        metiers.update([rome or intitule or "non_precise"])
        territoires.update([get_lieu(offre)])
        niveaux.update([detect_niveau(texte)])

    tendances = {
        "nombre_offres": len(offres),
        "competences": dict(competences.most_common()),
        "metiers": dict(metiers.most_common()),
        "territoires": dict(territoires.most_common()),
        "niveau": dict(niveaux.most_common()),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(tendances, f, ensure_ascii=False, indent=2)

    print(json.dumps(tendances, ensure_ascii=False, indent=2))

def main() -> None:
    debug = "--debug" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if args and args[0] == "-":
        text = sys.stdin.read()
    elif args:
        try:
            with open(args[0], encoding="utf-8") as fh:
                text = fh.read()
        except FileNotFoundError:
            print(f"Error: file not found '{args[0]}'", file=sys.stderr)
            sys.exit(1)
    else:
        print("Usage: python app_cli.py [--debug] <file>|-", file=sys.stderr)
        sys.exit(1)

    result = extract_job_offer(text, debug=debug)

    if debug and "segments_classes" in result:
        print("--- Segments classés (debug) ---")
        for seg in result["segments_classes"]:
            print(f"  [{seg['label']:>12}] {seg['text']}")
        print()

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
