# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Text extraction helpers for CV documents."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

try:  # pragma: no cover - optional dependency
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - optional dependency
    PdfReader = None

try:  # pragma: no cover - optional dependency
    from docx import Document
except ImportError:  # pragma: no cover - optional dependency
    Document = None

TEXT_LIMIT = 300_000
PDF_MIN_TEXT_LENGTH = 20


def _clean_text(text: str) -> str:
    text = text.replace("\r", "\n")
    text = text.replace("\x00", " ")
    lines = [line.strip() for line in text.splitlines()]
    cleaned = "\n".join(line for line in lines if line)
    while "\n\n\n" in cleaned:
        cleaned = cleaned.replace("\n\n\n", "\n\n")
    return cleaned.strip()


def _extract_pdf_text(path: Path) -> str:
    raw = path.read_bytes()
    if not raw.startswith(b"%PDF"):
        raise ValueError("Invalid PDF file.")

    if PdfReader is not None:
        try:
            reader = PdfReader(str(path))
            extracted = _clean_text("\n".join(page.extract_text() or "" for page in reader.pages))
            if len(extracted) >= PDF_MIN_TEXT_LENGTH:
                return extracted[:TEXT_LIMIT]
        except Exception:
            pass

    # Fallback for simple text-based PDFs.
    text_parts: list[str] = []
    for match in re.finditer(rb"\(([^)]{1,500})\)\s*T[Jj]", raw):
        candidate = match.group(1).decode("latin-1", errors="ignore")
        candidate = candidate.replace(r"\n", "\n").replace(r"\r", "\r").replace(r"\t", "\t")
        candidate = re.sub(r"\\([()\\])", r"\1", candidate)
        text_parts.append(candidate)
    if not text_parts:
        for chunk in raw.splitlines():
            if b"Tj" in chunk or b"TJ" in chunk:
                candidate = chunk.decode("latin-1", errors="ignore")
                candidate = candidate.replace("\\n", "\n").replace("\\r", "\r").replace("\\t", "\t")
                text_parts.append(candidate)
    text = _clean_text("\n".join(text_parts))
    if len(text) < PDF_MIN_TEXT_LENGTH:
        raise ValueError("The PDF does not contain extractable text.")
    return text[:TEXT_LIMIT]


def _extract_docx_text(path: Path) -> str:
    if Document is not None:
        try:
            document = Document(str(path))
            text = _clean_text("\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text))
            if text:
                return text[:TEXT_LIMIT]
        except Exception:
            pass

    with zipfile.ZipFile(path) as zf:
        try:
            data = zf.read("word/document.xml")
        except KeyError as exc:
            raise ValueError("Invalid DOCX file.") from exc
    root = ET.fromstring(data)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", namespace):
        parts = [node.text for node in paragraph.findall(".//w:t", namespace) if node.text]
        line = "".join(parts).strip()
        if line:
            paragraphs.append(line)
    text = _clean_text("\n".join(paragraphs))
    if not text:
        raise ValueError("The DOCX does not contain extractable text.")
    return text[:TEXT_LIMIT]


def _extract_txt_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        text = path.read_text(encoding="latin-1")
    text = _clean_text(text)
    if not text:
        raise ValueError("The TXT file does not contain extractable text.")
    return text[:TEXT_LIMIT]


def extract_text_from_cv(path: str | Path) -> str:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf_text(path)
    if suffix == ".docx":
        return _extract_docx_text(path)
    if suffix == ".txt":
        return _extract_txt_text(path)
    raise ValueError("Unsupported format. Use PDF, DOCX, or TXT.")
