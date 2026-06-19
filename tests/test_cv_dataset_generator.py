# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
<<<<<<< HEAD
from argparse import Namespace
from pathlib import Path

import pytest

from src.cv_dataset_generator import (
    TEMPLATE_SPECS,
    SyntheticCVGenerator,
    convert_jsonl_to_huggingface,
    convert_jsonl_to_spacy,
    generate_dataset,
    load_dataset_jsonl,
    run_cli,
    write_dataset,
    split_records,
)


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False))
            handle.write("\n")


def test_reproducible_with_same_seed() -> None:
    first = generate_dataset(count=5, seed=42)
    second = generate_dataset(count=5, seed=42)
=======
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
>>>>>>> 5c2ec9682de243a7a10f4df4eeda37509b8341e4
    assert first == second


def test_different_seed_changes_output() -> None:
<<<<<<< HEAD
    first = generate_dataset(count=5, seed=42)
    second = generate_dataset(count=5, seed=43)
    assert first != second


def test_generates_exact_count_and_all_templates() -> None:
    records = generate_dataset(count=len(TEMPLATE_SPECS) * 3, seed=42)
    assert len(records) == len(TEMPLATE_SPECS) * 3
    assert {record["metadata"]["template"] for record in records} == set(TEMPLATE_SPECS)


def test_offsets_are_valid_and_non_overlapping() -> None:
    records = generate_dataset(count=10, seed=42)
    for record in records:
        text = record["text"]
        previous_end = 0
        for entity in sorted(record["entities"], key=lambda item: (item["start"], item["end"])):
            assert entity["start"] >= previous_end
            assert text[entity["start"] : entity["end"]] == entity["text"]
            previous_end = entity["end"]


def test_noise_level_3_produces_noisy_pdf_text() -> None:
    generator = SyntheticCVGenerator(seed=42, noise_level=3)
    record = generator.generate_record(1, template_name="noisy_pdf")
    assert record["metadata"]["template"] == "noisy_pdf"
    assert "\n" in record["text"]
    assert "  " in record["text"]


def test_export_spacy(tmp_path: Path) -> None:
    source = tmp_path / "dataset.jsonl"
    spacy_output = tmp_path / "spacy.jsonl"
    records = generate_dataset(count=4, seed=42)
    _write_jsonl(source, records)
    convert_jsonl_to_spacy(source, spacy_output)
    lines = spacy_output.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4
    payload = json.loads(lines[0])
    assert set(payload) == {"text", "entities"}
    assert all(isinstance(entity, list) and len(entity) == 3 for entity in payload["entities"])


def test_export_huggingface(tmp_path: Path) -> None:
    source = tmp_path / "dataset.jsonl"
    hf_output = tmp_path / "hf.jsonl"
    records = generate_dataset(count=4, seed=42)
    _write_jsonl(source, records)
    convert_jsonl_to_huggingface(source, hf_output)
    lines = hf_output.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4
    payload = json.loads(lines[0])
    assert len(payload["tokens"]) == len(payload["ner_tags"])
    assert payload["id"].startswith("cv_")
    assert "O" in payload["ner_tags"] or any(tag.startswith("B-") for tag in payload["ner_tags"])


def test_split_train_validation_test(tmp_path: Path) -> None:
    output = tmp_path / "data" / "cv" / "synthetic_cv_dataset.jsonl"
    args = Namespace(
        count=10,
        output=output,
        seed=42,
        format="jsonl",
        noise_level=0,
        split=True,
        train_ratio=0.8,
        validation_ratio=0.1,
        test_ratio=0.1,
    )
    assert run_cli(args) == 0
    train = output.parent / "train.jsonl"
    validation = output.parent / "validation.jsonl"
    test = output.parent / "test.jsonl"
    assert train.exists() and validation.exists() and test.exists()
    total = sum(len(load_dataset_jsonl(path)) for path in (train, validation, test))
    assert total == 10
    ids = [record["id"] for path in (train, validation, test) for record in load_dataset_jsonl(path)]
    assert len(ids) == len(set(ids))


def test_split_ratios_must_sum_to_one() -> None:
    records = generate_dataset(count=10, seed=42)
    with pytest.raises(ValueError):
        split_records(records, 0.7, 0.2, 0.2, seed=42)


def test_creates_directories_automatically(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "more" / "dataset.jsonl"
    records = generate_dataset(count=2, seed=42)
    write_dataset(records, output, output_format="jsonl")
    assert output.exists()
=======
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


>>>>>>> 5c2ec9682de243a7a10f4df4eeda37509b8341e4
