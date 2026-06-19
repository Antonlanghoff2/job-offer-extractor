# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Validate a synthetic CV dataset."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Iterable

from src.cv_dataset_core import LABELS, iter_jsonl, print_validation_report, validate_dataset


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "cv" / "synthetic_cv_dataset.jsonl"


def build_parser() -> argparse.ArgumentParser:
    """Build the validator CLI parser."""

    parser = argparse.ArgumentParser(description="Valider un jeu de données de CV synthétiques.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Fichier JSONL à valider.")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    """CLI entry point."""

    args = build_parser().parse_args(argv)
    try:
        input_path = Path(args.input)
        records = list(iter_jsonl(input_path))
        report = validate_dataset(records, set(LABELS))
        print_validation_report(report)
        return 1 if report.has_errors else 0
    except FileNotFoundError:
        print(f"Erreur: fichier introuvable: {args.input}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - exercised through CLI tests.
        print(f"Erreur: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point.
    raise SystemExit(main())

