# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Generate a synthetic, annotated French CV dataset."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Iterable

from src.cv_dataset_core import (
    build_dataset,
    export_records,
    iter_jsonl,
    split_records,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "cv" / "synthetic_cv_dataset.jsonl"


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""

    parser = argparse.ArgumentParser(
        description="Générer un jeu de données de CV synthétiques français annotés.",
    )
    parser.add_argument("--count", type=int, default=1000, help="Nombre de CV à générer.")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Fichier JSONL de sortie ou dossier de base si --split est utilisé.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Graine de reproductibilité.")
    parser.add_argument(
        "--format",
        choices=("jsonl", "spacy", "huggingface"),
        default="jsonl",
        help="Format de sortie.",
    )
    parser.add_argument(
        "--noise-level",
        type=int,
        choices=(0, 1, 2, 3),
        default=0,
        help="Intensité du bruit de type extraction PDF.",
    )
    parser.add_argument("--split", action="store_true", help="Écrit un découpage train/validation/test.")
    parser.add_argument("--train-ratio", type=float, default=0.8, help="Ratio d'entraînement.")
    parser.add_argument("--validation-ratio", type=float, default=0.1, help="Ratio de validation.")
    parser.add_argument("--test-ratio", type=float, default=0.1, help="Ratio de test.")
    return parser


def _validate_ratios(train_ratio: float, validation_ratio: float, test_ratio: float) -> None:
    """Ensure the split ratios sum to 1.0."""

    total = train_ratio + validation_ratio + test_ratio
    if abs(total - 1.0) > 1e-9:
        raise ValueError("La somme des ratios de découpage doit valoir 1.0.")


def convert_jsonl_dataset_to_spacy(input_path: Path, output_path: Path) -> None:
    """Convert the main JSONL dataset to spaCy JSONL."""

    records = list(iter_jsonl(input_path))
    export_records(records, output_path, "spacy")


def convert_jsonl_dataset_to_huggingface(input_path: Path, output_path: Path) -> None:
    """Convert the main JSONL dataset to a Hugging Face-friendly JSONL file."""

    records = list(iter_jsonl(input_path))
    export_records(records, output_path, "huggingface")


def _write_split(records: list[dict[str, object]], output_dir: Path, output_format: str) -> None:
    """Write the three split files in the selected format."""

    output_dir.mkdir(parents=True, exist_ok=True)
    for split_name, split_records in records.items():
        export_records(split_records, output_dir / f"{split_name}.jsonl", output_format)


def _write_single_output(records: list[dict[str, object]], output_path: Path, output_format: str) -> None:
    """Write a single dataset file in the selected format."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    export_records(records, output_path, output_format)


def main(argv: Iterable[str] | None = None) -> int:
    """CLI entry point."""

    args = build_parser().parse_args(argv)
    try:
        if args.split:
            _validate_ratios(args.train_ratio, args.validation_ratio, args.test_ratio)
        if args.count < 0:
            raise ValueError("Le nombre de CV doit être supérieur ou égal à zéro.")
        records = build_dataset(args.count, args.seed, args.noise_level)
        output_path = Path(args.output)

        if args.split:
            split_map = split_records(records, args.seed, args.train_ratio, args.validation_ratio, args.test_ratio)
            output_dir = output_path.parent
            _write_split(split_map, output_dir, args.format)
            print(
                f"Découpage terminé: {len(split_map['train'])} entraînement, "
                f"{len(split_map['validation'])} validation, {len(split_map['test'])} test.",
            )
            print(f"Fichiers écrits dans {output_dir}")
        else:
            _write_single_output(records, output_path, args.format)
            print(f"{len(records)} CV écrits dans {output_path}")
        return 0
    except Exception as exc:  # pragma: no cover - exercised through CLI tests.
        print(f"Erreur: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point.
    raise SystemExit(main())

