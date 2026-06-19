# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Confidence scoring helpers for CV parsing."""

from __future__ import annotations


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def education_confidence(*, title: bool, institution: bool, date: bool, description: bool) -> float:
    score = 0.45 + (0.2 if title else 0.0) + (0.15 if institution else 0.0) + (0.12 if date else 0.0) + (0.08 if description else 0.0)
    return round(clamp(score), 2)


def skill_confidence(source: str, explicit: bool = False) -> float:
    base = {"explicite": 0.96, "experience_professionnelle": 0.9, "deduite_de_formation": 0.72}.get(source, 0.8)
    return round(clamp(base if explicit else base - 0.04), 2)


def experience_confidence(*, title: bool, company: bool, date: bool, description: bool, location: bool) -> float:
    score = 0.4 + (0.22 if title else 0.0) + (0.14 if company else 0.0) + (0.12 if date else 0.0) + (0.07 if location else 0.0) + (0.05 if description else 0.0)
    return round(clamp(score), 2)
