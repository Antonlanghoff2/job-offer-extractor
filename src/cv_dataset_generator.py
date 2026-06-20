# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Generate a synthetic, annotated French CV dataset."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

from src.cv_dataset_core import (
    CONTACT_LABELS,
    LABELS as ALLOWED_LABELS,
    TEMPLATES,
    build_dataset,
    convert_record_to_huggingface,
    convert_record_to_spacy,
    export_records,
    iter_jsonl,
    split_records,
    write_jsonl,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "cv" / "synthetic_cv_dataset.jsonl"
TEMPLATE_SPECS = TEMPLATES


class SyntheticCVGenerator:
    """Backward-compatible wrapper around the deterministic dataset builder."""

    def __init__(self, seed: int = 42, noise_level: int = 0) -> None:
        self.seed = seed
        self.noise_level = noise_level

    def generate_record(self, index: int, template_name: Optional[str] = None) -> Dict[str, Any]:
        records = build_dataset(index + 1, self.seed, self.noise_level)
        record = records[index]
        if template_name is not None and record.get("metadata", {}).get("template") != template_name:
            raise ValueError("Le template demandé n'est pas disponible pour cet index.")
        return record


def generate_dataset(count: int = 1000, seed: int = 42, noise_level: int = 0) -> List[Dict[str, Any]]:
    return build_dataset(count, seed, noise_level)


def _write_jsonl(path: Path, records: Iterable[Dict[str, Any]]) -> None:
    write_jsonl(list(records), path)


def load_dataset_jsonl(path: Union[str, Path]) -> List[Dict[str, Any]]:
    return list(iter_jsonl(Path(path)))


def convert_to_spacy_records(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [convert_record_to_spacy(record) for record in records]


def convert_to_huggingface_records(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [convert_record_to_huggingface(record) for record in records]


def write_dataset(records: List[Dict[str, Any]], output: Union[str, Path], output_format: str = "jsonl") -> Path:
    path = Path(output)
    export_records(list(records), path, output_format)
    return path


def convert_jsonl_dataset_to_spacy(input_path: Union[str, Path], output_path: Union[str, Path]) -> Path:
    records = load_dataset_jsonl(input_path)
    return write_dataset(records, output_path, output_format="spacy")


def convert_jsonl_dataset_to_huggingface(input_path: Union[str, Path], output_path: Union[str, Path]) -> Path:
    records = load_dataset_jsonl(input_path)
    return write_dataset(records, output_path, output_format="huggingface")


def build_output_paths(base_output: Union[str, Path]) -> Dict[str, Path]:
    path = Path(base_output)
    parent = path.parent
    return {
        "train": parent / "train.jsonl",
        "validation": parent / "validation.jsonl",
        "test": parent / "test.jsonl",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Générer un jeu de données de CV synthétiques français annotés.")
    parser.add_argument("--count", type=int, default=1000, help="Nombre de CV à générer.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Fichier JSONL de sortie ou dossier de base si --split est utilisé.")
    parser.add_argument("--seed", type=int, default=42, help="Graine de reproductibilité.")
    parser.add_argument("--format", choices=("jsonl", "spacy", "huggingface"), default="jsonl", help="Format de sortie.")
    parser.add_argument("--noise-level", type=int, choices=(0, 1, 2, 3), default=0, help="Intensité du bruit de type extraction PDF.")
    parser.add_argument("--split", action="store_true", help="Écrit un découpage train/validation/test.")
    parser.add_argument("--train-ratio", type=float, default=0.8, help="Ratio d'entraînement.")
    parser.add_argument("--validation-ratio", type=float, default=0.1, help="Ratio de validation.")
    parser.add_argument("--test-ratio", type=float, default=0.1, help="Ratio de test.")
    return parser


def _validate_ratios(train_ratio: float, validation_ratio: float, test_ratio: float) -> None:
    total = train_ratio + validation_ratio + test_ratio
    if abs(total - 1.0) > 1e-9:
        raise ValueError("La somme des ratios de découpage doit valoir 1.0.")


def _write_split(split_map: Dict[str, List[Dict[str, Any]]], output_dir: Path, output_format: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for split_name, split_records in split_map.items():
        export_records(split_records, output_dir / f"{split_name}.jsonl", output_format)


def _write_single_output(records: List[Dict[str, Any]], output_path: Path, output_format: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    export_records(records, output_path, output_format)


def run_cli(args: argparse.Namespace) -> int:
    if args.count < 0:
        raise SystemExit("Le nombre de CV doit être positif.")
    records = generate_dataset(args.count, args.seed, args.noise_level)
    output_path = Path(args.output)
    if args.split:
        if args.format != "jsonl":
            raise SystemExit("Le découpage train/validation/test est disponible uniquement en JSONL.")
        _validate_ratios(args.train_ratio, args.validation_ratio, args.test_ratio)
        split_map = split_records(records, args.seed, args.train_ratio, args.validation_ratio, args.test_ratio)
        _write_split(split_map, output_path.parent, args.format)
        print(f"Dataset généré avec séparation train/validation/test dans {output_path.parent}")
        return 0
    _write_single_output(records, output_path, args.format)
    print(f"Dataset généré: {output_path}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run_cli(args)
    except Exception as exc:  # pragma: no cover - exercised through CLI tests.
        print(f"Erreur: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
