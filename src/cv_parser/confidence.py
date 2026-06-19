# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Confidence heuristics for CV parsing outputs."""

from __future__ import annotations

from typing import Any


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def education_confidence(title: bool, institution: bool, date: bool, description: bool) -> float:
    score = 0.35 * float(title) + 0.35 * float(institution) + 0.2 * float(date) + 0.1 * float(description)
    return _clamp(score)


def experience_confidence(title: bool, company: bool, date: bool, description: bool, location: bool) -> float:
    score = 0.3 * float(title) + 0.25 * float(company) + 0.2 * float(date) + 0.15 * float(description) + 0.1 * float(location)
    return _clamp(score)


def skill_confidence(source: str, explicit: bool = False) -> float:
    base = {"explicite": 0.96, "experience_professionnelle": 0.9, "deduite_de_formation": 0.72}.get(source, 0.8)
    if explicit:
        base = min(1.0, base + 0.02)
    return _clamp(base)
