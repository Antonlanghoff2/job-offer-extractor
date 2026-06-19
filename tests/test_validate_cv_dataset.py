# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

from __future__ import annotations

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
