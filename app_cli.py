# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""
Interactive CLI — paste a French job offer and get extracted JSON.

Usage
-----
    python app_cli.py

Paste the offer text, then type ``END`` on a line by itself to finish.
The script loads the trained model, runs the full extraction pipeline,
and prints the result as indented JSON.
"""

from __future__ import annotations

import json
import os
import sys

MODEL_PATH = "models/segment_classifier.joblib"


def main() -> None:
    print("=" * 52)
    print("  Extracteur d'offres d'emploi")
    print("=" * 52)
    print()
    print("Collez l'offre d'emploi ci-dessous.")
    print("Terminez la saisie avec une ligne contenant uniquement END.")
    print()

    if not os.path.isfile(MODEL_PATH):
        print(
            f"Erreur : modèle non trouvé dans '{MODEL_PATH}'.",
            file=sys.stderr,
        )
        print("Exécutez d'abord :  python -m src.train_classifier", file=sys.stderr)
        sys.exit(1)

    try:
        from src.predict import extract_job_offer
    except ImportError as exc:
        print(f"Erreur d'import : {exc}", file=sys.stderr)
        print("Assurez-vous que les dépendances sont installées :", file=sys.stderr)
        print("  pip install -r requirements.txt", file=sys.stderr)
        sys.exit(1)

    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "END":
            break
        lines.append(line)

    text = "\n".join(lines).strip()

    if not text:
        print("Erreur : aucun texte saisi.", file=sys.stderr)
        sys.exit(1)

    result = extract_job_offer(text)

    print()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
