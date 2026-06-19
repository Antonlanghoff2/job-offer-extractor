# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
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
    assert first == second


def test_different_seed_changes_output() -> None:
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
