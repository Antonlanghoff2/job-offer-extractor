# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Compatibility wrapper for the new context-aware CV parser package."""

from src.cv_parser.parser import ParsedCV, extract_text_from_cv, parse_cv_file, parse_cv_text

__all__ = ["ParsedCV", "extract_text_from_cv", "parse_cv_file", "parse_cv_text"]
