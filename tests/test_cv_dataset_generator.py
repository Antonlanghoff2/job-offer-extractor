# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
from pathlib import Path

from src.cv_dataset_core import (
    LABELS,
    TEMPLATES,
    build_dataset,
    export_records,
    validate_dataset,
    write_jsonl,
)
from src.cv_dataset_generator import (
    convert_jsonl_dataset_to_huggingface,
    convert_jsonl_dataset_to_spacy,
    main as generate_main,
)


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_reproducibility_with_identical_seed() -> None:
    first = build_dataset(5, 42, 0)
    second = build_dataset(5, 42, 0)
    assert first == second


def test_different_seed_changes_output() -> None:
    first = build_dataset(5, 42, 0)
    second = build_dataset(5, 43, 0)
    assert first != second


def test_exact_count_and_offset_validity() -> None:
    records = build_dataset(12, 42, 0)
    assert len(records) == 12
    report = validate_dataset(records, set(LABELS))
    assert report.invalid == 0
    assert report.valid == 12
    for record in records:
        text = record["text"]
        for entity in record["entities"]:
            assert text[entity["start"] : entity["end"]] == entity["text"]


def test_all_templates_are_generated() -> None:
    records = build_dataset(28, 42, 0)
    templates = {record["metadata"]["template"] for record in records}
    assert templates == set(TEMPLATES)


def test_noise_level_three_still_produces_valid_offsets() -> None:
    clean = build_dataset(8, 42, 0)
    noisy = build_dataset(8, 42, 3)
    assert clean != noisy
    assert validate_dataset(noisy, set(LABELS)).invalid == 0


def test_spacy_export(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    output = tmp_path / "spacy.jsonl"
    records = build_dataset(4, 42, 0)
    write_jsonl(records, source)

    convert_jsonl_dataset_to_spacy(source, output)

    exported = read_jsonl(output)
    assert len(exported) == 4
    for line, record in zip(exported, records, strict=True):
        assert line["text"] == record["text"]
        assert all(len(entity) == 3 for entity in line["entities"])


def test_huggingface_export(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    output = tmp_path / "hf.jsonl"
    records = build_dataset(4, 42, 0)
    write_jsonl(records, source)

    convert_jsonl_dataset_to_huggingface(source, output)

    exported = read_jsonl(output)
    assert len(exported) == 4
    for line in exported:
        assert len(line["tokens"]) == len(line["ner_tags"])
        assert line["id"].startswith("cv_")


def test_split_train_validation_test(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "dataset.jsonl"
    exit_code = generate_main(
        [
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
        ]
    )

    assert exit_code == 0
    train = read_jsonl(output.parent / "train.jsonl")
    validation = read_jsonl(output.parent / "validation.jsonl")
    test = read_jsonl(output.parent / "test.jsonl")
    assert len(train) + len(validation) + len(test) == 100
    train_ids = {record["id"] for record in train}
    validation_ids = {record["id"] for record in validation}
    test_ids = {record["id"] for record in test}
    assert train_ids.isdisjoint(validation_ids)
    assert train_ids.isdisjoint(test_ids)
    assert validation_ids.isdisjoint(test_ids)


def test_split_ratio_error(tmp_path: Path) -> None:
    output = tmp_path / "dataset.jsonl"
    exit_code = generate_main(
        [
            "--count",
            "10",
            "--split",
            "--train-ratio",
            "0.7",
            "--validation-ratio",
            "0.2",
            "--test-ratio",
            "0.2",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 1


def test_directory_creation(tmp_path: Path) -> None:
    output = tmp_path / "a" / "b" / "c" / "dataset.jsonl"
    exit_code = generate_main(["--count", "3", "--output", str(output), "--seed", "42"])

    assert exit_code == 0
    assert output.exists()


