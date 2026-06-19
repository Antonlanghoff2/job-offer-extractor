# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

from __future__ import annotations

<<<<<<< HEAD
from src.cv_dataset_generator import CONTACT_LABELS, generate_dataset
from src.validate_cv_dataset import format_report, validate_records


def test_validate_valid_dataset() -> None:
    records = generate_dataset(count=6, seed=42)
    report = validate_records(records)
    assert report.analyzed == 6
    assert report.valid == 6
    assert report.invalid == 0
    assert report.majority_contacts_ok
    assert "CV analysés: 6" in format_report(report)


def test_validate_empty_dataset() -> None:
    report = validate_records([])
    assert report.analyzed == 0
    assert report.valid == 0
    assert report.invalid == 0
    assert report.errors


def test_validate_detects_invalid_annotation() -> None:
    records = generate_dataset(count=1, seed=42)
    records[0]["entities"][0]["end"] += 1
    report = validate_records(records)
    assert report.invalid == 1
    assert any("offsets" in error.lower() for error in report.errors)


def test_validate_requires_majority_contact_and_name() -> None:
    records = generate_dataset(count=4, seed=42)
    for record in records:
        record["entities"] = [entity for entity in record["entities"] if entity["label"] not in CONTACT_LABELS]
    report = validate_records(records)
    assert not report.majority_contacts_ok
    assert any("majorité" in error.lower() for error in report.errors)
=======
import json
from pathlib import Path

from src.cv_dataset_core import LABELS, validate_dataset, write_jsonl
from src.cv_dataset_generator import main as generate_main
from src.validate_cv_dataset import main as validate_main


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_validation_cli_on_empty_dataset(tmp_path: Path) -> None:
    input_path = tmp_path / "empty.jsonl"
    input_path.write_text("", encoding="utf-8")

    exit_code = validate_main(["--input", str(input_path)])

    assert exit_code == 0


def test_validation_cli_detects_invalid_annotation(tmp_path: Path) -> None:
    input_path = tmp_path / "invalid.jsonl"
    write_jsonl(
        [
            {
                "id": "cv_000001",
                "text": "Jean Dupont\nDéveloppeur Python",
                "entities": [
                    {"start": 0, "end": 11, "label": "NAME", "text": "Jean Dupont"},
                    {"start": 0, "end": 5, "label": "JOB_TITLE", "text": "Jean"},
                ],
                "metadata": {"synthetic": True, "template": "classic", "language": "fr"},
            }
        ],
        input_path,
    )

    exit_code = validate_main(["--input", str(input_path)])

    assert exit_code == 1


def test_generated_dataset_validates_successfully(tmp_path: Path) -> None:
    output = tmp_path / "dataset.jsonl"
    assert generate_main(["--count", "20", "--output", str(output), "--seed", "42"]) == 0

    records = read_jsonl(output)
    report = validate_dataset(records, set(LABELS))
    assert report.analyzed == 20
    assert report.invalid == 0
    assert report.valid == 20
    assert report.total_entities > 0
    assert report.cv_with_name_and_contact >= 10


>>>>>>> 5c2ec9682de243a7a10f4df4eeda37509b8341e4
