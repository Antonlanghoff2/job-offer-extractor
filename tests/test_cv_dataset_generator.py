# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict, List

import pytest

from src.cv_dataset_core import LABELS, TEMPLATES, validate_dataset
from src.cv_dataset_generator import (
    _write_jsonl,
    convert_jsonl_dataset_to_huggingface,
    convert_jsonl_dataset_to_spacy,
    generate_dataset,
    load_dataset_jsonl,
    main as generator_main,
    run_cli,
    write_dataset,
)


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_reproducible_with_same_seed() -> None:
    first = generate_dataset(count=5, seed=42)
    second = generate_dataset(count=5, seed=42)
    assert first == second


def test_different_seed_changes_output() -> None:
    first = generate_dataset(count=5, seed=42)
    second = generate_dataset(count=5, seed=43)
    assert first != second


def test_generates_exact_count() -> None:
    records = generate_dataset(count=13, seed=42)
    assert len(records) == 13


def test_offsets_are_valid() -> None:
    records = generate_dataset(count=10, seed=42)
    for record in records:
        text = record["text"]
        previous_end = 0
        for entity in sorted(record["entities"], key=lambda item: (item["start"], item["end"])):
            assert entity["start"] >= previous_end
            assert text[entity["start"]:entity["end"]] == entity["text"]
            previous_end = entity["end"]


def test_all_templates_are_generated() -> None:
    records = generate_dataset(count=len(TEMPLATES) * 2, seed=42)
    templates = {record["metadata"]["template"] for record in records}
    assert templates == set(TEMPLATES)


def test_noise_level_three_is_valid() -> None:
    records = generate_dataset(count=8, seed=42, noise_level=3)
    clean = generate_dataset(count=8, seed=42, noise_level=0)
    assert records != clean
    report = validate_dataset(records, set(LABELS))
    assert report.invalid == 0


def test_export_spacy(tmp_path: Path) -> None:
    source = tmp_path / "dataset.jsonl"
    output = tmp_path / "spacy.jsonl"
    records = generate_dataset(count=4, seed=42)
    _write_jsonl(source, records)

    convert_jsonl_dataset_to_spacy(source, output)

    exported = _read_jsonl(output)
    assert len(exported) == 4
    payload = exported[0]
    assert set(payload) == {"text", "entities"}
    assert all(len(entity) == 3 for entity in payload["entities"])


def test_export_huggingface(tmp_path: Path) -> None:
    source = tmp_path / "dataset.jsonl"
    output = tmp_path / "hf.jsonl"
    records = generate_dataset(count=4, seed=42)
    _write_jsonl(source, records)

    convert_jsonl_dataset_to_huggingface(source, output)

    exported = _read_jsonl(output)
    assert len(exported) == 4
    payload = exported[0]
    assert len(payload["tokens"]) == len(payload["ner_tags"])
    assert payload["id"].startswith("cv_")


def test_split_train_validation_test(tmp_path: Path) -> None:
    output = tmp_path / "data" / "cv" / "synthetic_cv_dataset.jsonl"
    exit_code = generator_main([
        "--count",
        "100",
        "--split",
        "--train-ratio",
        "0.8",
        "--validation-ratio",
        "0.1",
        "--test-ratio",
        "0.1",
        "--output",
        str(output),
    ])

    assert exit_code == 0
    train = _read_jsonl(output.parent / "train.jsonl")
    validation = _read_jsonl(output.parent / "validation.jsonl")
    test = _read_jsonl(output.parent / "test.jsonl")
    assert len(train) + len(validation) + len(test) == 100
    train_ids = {record["id"] for record in train}
    validation_ids = {record["id"] for record in validation}
    test_ids = {record["id"] for record in test}
    assert train_ids.isdisjoint(validation_ids)
    assert train_ids.isdisjoint(test_ids)
    assert validation_ids.isdisjoint(test_ids)


def test_split_ratio_error() -> None:
    records = generate_dataset(count=10, seed=42)
    with pytest.raises(ValueError):
        run_cli(
            Namespace(
                count=10,
                output=Path("/tmp/dataset.jsonl"),
                seed=42,
                format="jsonl",
                noise_level=0,
                split=True,
                train_ratio=0.7,
                validation_ratio=0.2,
                test_ratio=0.2,
            )
        )


def test_directory_creation(tmp_path: Path) -> None:
    output = tmp_path / "a" / "b" / "c" / "dataset.jsonl"
    exit_code = generator_main(["--count", "3", "--output", str(output), "--seed", "42"])
    assert exit_code == 0
    assert output.exists()


def test_write_dataset_creates_parent_directories(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "dataset.jsonl"
    records = generate_dataset(count=2, seed=42)
    write_dataset(records, output, output_format="jsonl")
    assert output.exists()


def test_load_dataset_jsonl_roundtrip(tmp_path: Path) -> None:
    output = tmp_path / "roundtrip.jsonl"
    records = generate_dataset(count=2, seed=42)
    _write_jsonl(output, records)
    loaded = load_dataset_jsonl(output)
    assert loaded == records
