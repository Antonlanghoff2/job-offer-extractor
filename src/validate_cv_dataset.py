# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Validate synthetic CV datasets produced by ``src.cv_dataset_generator``."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.cv_dataset_generator import ALLOWED_LABELS, CONTACT_LABELS, load_dataset_jsonl


@dataclass
class ValidationReport:
    analyzed: int = 0
    valid: int = 0
    invalid: int = 0
    total_entities: int = 0
    label_counts: Counter[str] = field(default_factory=Counter)
    template_counts: Counter[str] = field(default_factory=Counter)
    errors: list[str] = field(default_factory=list)
    name_coverage: int = 0
    contact_coverage: int = 0

    @property
    def average_entities(self) -> float:
        return self.total_entities / self.valid if self.valid else 0.0

    @property
    def majority_contacts_ok(self) -> bool:
        if self.analyzed == 0:
            return False
        threshold = math.ceil(self.analyzed / 2)
        return self.name_coverage >= threshold and self.contact_coverage >= threshold


def _iter_records(path: Path) -> list[dict[str, Any]]:
    return load_dataset_jsonl(path)


def _validate_entity(entity: dict[str, Any], text: str, previous_end: int, seen: set[tuple[int, int, str, str]]) -> tuple[bool, str | None, int]:
    required_keys = {"start", "end", "label", "text"}
    if not required_keys.issubset(entity):
        return False, "Entité incomplète.", previous_end
    try:
        start = int(entity["start"])
        end = int(entity["end"])
    except (TypeError, ValueError):
        return False, "Offsets non numériques.", previous_end
    label = str(entity["label"])
    value = str(entity["text"])
    if label not in ALLOWED_LABELS:
        return False, f"Label interdit: {label}", previous_end
    if start < 0:
        return False, "start < 0.", previous_end
    if end > len(text):
        return False, "end dépasse la longueur du texte.", previous_end
    if start >= end:
        return False, "start doit être strictement inférieur à end.", previous_end
    if text[start:end] != value:
        return False, "Le texte annoté ne correspond pas aux offsets.", previous_end
    if start < previous_end:
        return False, "Chevauchement d'entités.", previous_end
    key = (start, end, label, value)
    if key in seen:
        return False, "Doublon exact d'entité.", previous_end
    seen.add(key)
    return True, None, end


def _entity_sort_key(entity: object) -> tuple[int, int]:
    if not isinstance(entity, dict):
        return (0, 0)
    try:
        start = int(entity.get("start", 0))
    except (TypeError, ValueError):
        start = 0
    try:
        end = int(entity.get("end", 0))
    except (TypeError, ValueError):
        end = 0
    return start, end


def validate_records(records: list[dict[str, Any]]) -> ValidationReport:
    report = ValidationReport()
    if not records:
        report.errors.append("Le dataset est vide.")
        return report

    ids_seen: set[str] = set()
    for index, record in enumerate(records, start=1):
        report.analyzed += 1
        if not isinstance(record, dict):
            report.invalid += 1
            report.errors.append(f"CV {index}: entrée JSON invalide.")
            continue

        record_id = str(record.get("id") or "")
        text = record.get("text")
        entities = record.get("entities")
        metadata = record.get("metadata") or {}

        if not record_id:
            report.invalid += 1
            report.errors.append(f"CV {index}: identifiant manquant.")
            continue
        if record_id in ids_seen:
            report.invalid += 1
            report.errors.append(f"CV {record_id}: identifiant dupliqué.")
            continue
        ids_seen.add(record_id)

        if not isinstance(text, str) or not text.strip():
            report.invalid += 1
            report.errors.append(f"CV {record_id}: texte manquant.")
            continue
        if not isinstance(entities, list):
            report.invalid += 1
            report.errors.append(f"CV {record_id}: liste entities manquante.")
            continue

        if isinstance(metadata, dict):
            template = str(metadata.get("template") or "unknown")
            report.template_counts[template] += 1

        seen_entities: set[tuple[int, int, str, str]] = set()
        previous_end = 0
        has_name = False
        has_contact = False
        record_invalid = False

        ordered_entities = sorted(
            entities,
            key=_entity_sort_key,
        )

        for entity in ordered_entities:
            if not isinstance(entity, dict):
                report.invalid += 1
                report.errors.append(f"CV {record_id}: entité JSON invalide.")
                record_invalid = True
                break
            valid, error, previous_end = _validate_entity(entity, text, previous_end, seen_entities)
            if not valid:
                report.invalid += 1
                report.errors.append(f"CV {record_id}: {error}")
                record_invalid = True
                break
            report.total_entities += 1
            label = str(entity["label"])
            report.label_counts[label] += 1
            if label == "NAME":
                has_name = True
            if label in CONTACT_LABELS:
                has_contact = True

        if record_invalid:
            continue

        if has_name:
            report.name_coverage += 1
        if has_contact:
            report.contact_coverage += 1
        report.valid += 1

    if not report.majority_contacts_ok:
        report.errors.append("La couverture NAME/contact n'atteint pas la majorité requise.")
    return report


def format_report(report: ValidationReport) -> str:
    lines = [
        f"CV analysés: {report.analyzed}",
        f"CV valides: {report.valid}",
        f"CV invalides: {report.invalid}",
        f"Nombre total d'entités: {report.total_entities}",
        f"Nombre moyen d'entités par CV: {report.average_entities:.2f}",
        "Répartition par label:",
    ]
    for label in ALLOWED_LABELS:
        lines.append(f"  - {label}: {report.label_counts.get(label, 0)}")
    lines.append("Répartition par template:")
    for template, count in sorted(report.template_counts.items()):
        lines.append(f"  - {template}: {count}")
    lines.append(f"Présence NAME/contact (majorité): {'oui' if report.majority_contacts_ok else 'non'}")
    if report.errors:
        lines.append("Erreurs rencontrées:")
        for error in report.errors[:50]:
            lines.append(f"  - {error}")
    return "\n".join(lines)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Valide un dataset CV synthétique annoté.")
    parser.add_argument("--input", type=Path, required=True, help="Fichier JSONL à valider.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    try:
        records = _iter_records(args.input)
    except FileNotFoundError:
        print(f"Fichier introuvable: {args.input}")
        return 1
    except json.JSONDecodeError as exc:
        print(f"JSON invalide: {exc}")
        return 1

    report = validate_records(records)
    print(format_report(report))
    return 0 if report.valid == report.analyzed and not report.errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
