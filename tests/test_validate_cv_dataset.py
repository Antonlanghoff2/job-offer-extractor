# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

from __future__ import annotations

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


