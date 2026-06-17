#!/usr/bin/env python3
# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""CLI for comparing France Travail and Indeed datasets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.source_comparison import compare_from_files


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare France Travail and Indeed offers.")
    parser.add_argument("--france-travail", required=True, help="JSON France Travail raw export.")
    parser.add_argument("--indeed", required=True, help="JSON Indeed export.")
    parser.add_argument("--territoire", default=None, help="Optional territory filter.")
    parser.add_argument("--periode", type=int, default=30, help="Rolling window in days.")
    parser.add_argument("--output", required=True, help="Output JSON path.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = compare_from_files(
        args.france_travail,
        args.indeed,
        territoire=args.territoire,
        periode_jours=args.periode,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print(f"France Travail: {result['france_travail']['nombre_offres']} offres")
    print(f"Indeed: {result['indeed']['nombre_offres']} offres")
    print(f"Écart: {result['comparaison']['ecart_nombre_offres']}")
    print(f"Comparaison enregistrée dans {output_path}")


if __name__ == "__main__":
    main()
