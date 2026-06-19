# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Build context-aware blocks from raw CV lines."""

from __future__ import annotations

from dataclasses import dataclass, field

from .normalizer import split_clean_lines
from .section_detector import SectionKind, detect_section


@dataclass(slots=True)
class CVBlock:
    section: SectionKind = "other"
    lines: list[str] = field(default_factory=list)
    start_line: int = 0
    end_line: int = 0
    header: str | None = None

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def build_blocks(text: str) -> list[CVBlock]:
    raw_lines = text.replace("\r", "\n").split("\n")
    blocks: list[CVBlock] = []
    current = CVBlock()
    current_section: SectionKind = "other"

    def flush(end_index: int) -> None:
        nonlocal current, current_section
        if current.lines:
            current.end_line = end_index
            blocks.append(current)
        current_section = "other"
        current = CVBlock(section=current_section, start_line=end_index + 1, end_line=end_index + 1)

    for index, raw_line in enumerate(raw_lines):
        line = raw_line.strip()
        if not line:
            if current.lines:
                flush(index)
            continue
        match = detect_section(line)
        if match:
            if current.lines:
                flush(index - 1 if index > 0 else 0)
            current_section = match.kind
            current = CVBlock(section=match.kind, header=match.raw, start_line=index + 1, end_line=index + 1)
            continue
        if not current.lines:
            current = CVBlock(section=current_section, start_line=index + 1, end_line=index + 1)
        current.lines.append(line)
        current.end_line = index + 1
    if current.lines:
        blocks.append(current)
    return blocks


def split_lines_for_block(text: str) -> list[str]:
    return split_clean_lines(text)
