# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Deterministic CV parsing helpers for PDF and DOCX uploads."""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - optional dependency
    PdfReader = None

try:
    from docx import Document
except ImportError:  # pragma: no cover - optional dependency
    Document = None

TEXT_LIMIT = 300_000
PDF_MIN_TEXT_LENGTH = 20


@dataclass
class ParsedCV:
    text: str
    structured: dict[str, Any]
    message: str | None = None


SECTION_HEADINGS = {
    "competences": {"competences", "compétences", "skills", "skill", "tech stack"},
    "diplomes": {"diplomes", "diplômes", "formation", "education", "etudes", "études"},
    "experiences": {"experiences", "expériences", "experience professionnelle", "professional experience", "experience"},
}

JOB_TITLES = [
    "développeur",
    "developpeur",
    "data scientist",
    "data engineer",
    "software engineer",
    "backend",
    "frontend",
    "full stack",
    "consultant",
    "chef de projet",
    "ingénieur",
    "ingenieur",
    "analyst",
    "analyste",
]


def _clean_text(text: str) -> str:
    text = text.replace("\r", "\n")
    text = re.sub(r"[\t ]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_pdf_text(path: Path) -> str:
    raw = path.read_bytes()
    if not raw.startswith(b"%PDF"):
        raise ValueError("Le fichier PDF est invalide.")

    if PdfReader is not None:
        try:
            reader = PdfReader(str(path))
            extracted = _clean_text("\n".join(page.extract_text() or "" for page in reader.pages))
            if len(extracted) >= PDF_MIN_TEXT_LENGTH:
                return extracted[:TEXT_LIMIT]
        except Exception:
            pass

    text_parts: list[str] = []
    for match in re.finditer(rb"\(([^\)]{1,500})\)\s*T[Jj]", raw):
        candidate = match.group(1).decode("latin-1", errors="ignore")
        candidate = candidate.replace(r"\n", "\n").replace(r"\r", "\r").replace(r"\t", "\t")
        candidate = re.sub(r"\\([()\\])", r"\1", candidate)
        text_parts.append(candidate)
    if not text_parts:
        ascii_chunks = re.findall(rb"[A-Za-z0-9\x80-\xff][A-Za-z0-9\x80-\xff ,;:\-/'()]{2,}", raw)
        for chunk in ascii_chunks:
            candidate = chunk.decode("latin-1", errors="ignore")
            if len(candidate.strip()) > 2:
                text_parts.append(candidate)
    text = _clean_text("\n".join(text_parts))
    if len(text) < PDF_MIN_TEXT_LENGTH:
        raise ValueError("Le PDF ne contient pas de texte exploitable.")
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
            raise ValueError("Le fichier DOCX est invalide.") from exc
    root = ET.fromstring(data)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for paragraph in root.findall('.//w:p', namespace):
        parts = [node.text for node in paragraph.findall('.//w:t', namespace) if node.text]
        line = ''.join(parts).strip()
        if line:
            paragraphs.append(line)
    text = _clean_text("\n".join(paragraphs))
    if not text:
        raise ValueError("Le DOCX ne contient pas de texte exploitable.")
    return text[:TEXT_LIMIT]


def extract_text_from_cv(path: str | Path) -> str:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf_text(path)
    if suffix == ".docx":
        return _extract_docx_text(path)
    raise ValueError("Format non supporte. Seuls PDF et DOCX sont acceptes.")


def _split_lines(text: str) -> list[str]:
    return [line.strip(" •-\t") for line in text.splitlines() if line.strip()]


def _is_heading(line: str) -> str | None:
    normalized = re.sub(r"[^a-z]+", " ", line.lower()).strip()
    for section, headings in SECTION_HEADINGS.items():
        if normalized in headings:
            return section
    return None


def _extract_level(text: str) -> str | None:
    lowered = text.lower()
    if any(token in lowered for token in ("expert", "senior", "avance", "avancé")):
        return "expert"
    if any(token in lowered for token in ("intermediaire", "intermédiaire", "mid")):
        return "intermediaire"
    if any(token in lowered for token in ("debutant", "débutant", "junior")):
        return "debutant"
    return None


def _extract_year(text: str) -> int | None:
    match = re.search(r"(19|20)\d{2}", text)
    return int(match.group(0)) if match else None


def _parse_skills(lines: list[str]) -> list[dict[str, Any]]:
    skills: list[dict[str, Any]] = []
    for line in lines:
        items = [part.strip() for part in re.split(r"[,;/|]", line) if part.strip()]
        if not items:
            items = [line]
        for item in items:
            skill = {"nom": item, "niveau": None, "annees_experience": None}
            level = _extract_level(item)
            if level:
                skill["niveau"] = level
            years = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:ans|années|annees)", item.lower())
            if years:
                skill["annees_experience"] = float(years.group(1).replace(",", "."))
            skills.append(skill)
    return skills


def _parse_diplomas(lines: list[str]) -> list[dict[str, Any]]:
    diplomas: list[dict[str, Any]] = []
    for line in lines:
        level = _extract_level(line)
        diplomas.append(
            {
                "intitule": line,
                "niveau": level or None,
                "etablissement": None,
                "annee": _extract_year(line),
                "description": "",
            }
        )
    return diplomas


def _parse_experiences(lines: list[str]) -> list[dict[str, Any]]:
    experiences: list[dict[str, Any]] = []
    for line in lines:
        cleaned = line.strip()
        if not cleaned:
            continue
        parts = [part.strip() for part in re.split(r"\s+[-–|]\s+", cleaned) if part.strip()]
        poste = parts[0] if parts else cleaned
        company = parts[1] if len(parts) > 1 else None
        experiences.append(
            {
                "poste": poste,
                "entreprise": company,
                "date_debut": None,
                "date_fin": None,
                "description": "",
            }
        )
    return experiences


def _detect_jobs(lines: list[str]) -> list[str]:
    detected: list[str] = []
    for line in lines:
        lowered = line.lower()
        if any(title in lowered for title in JOB_TITLES):
            detected.append(line)
    return list(dict.fromkeys(detected))


def parse_cv_text(text: str) -> dict[str, Any]:
    lines = _split_lines(text)
    sections: dict[str, list[str]] = {"competences": [], "diplomes": [], "experiences": []}
    current: str | None = None
    for line in lines:
        heading = _is_heading(line)
        if heading:
            current = heading
            continue
        if current in sections:
            sections[current].append(line)
    competences = _parse_skills(sections["competences"])
    diplomas = _parse_diplomas(sections["diplomes"])
    experiences = _parse_experiences(sections["experiences"])
    metiers = _detect_jobs(lines + [item["poste"] for item in experiences])
    return {
        "competences": [
            {
                "nom": item["nom"],
                "niveau": item["niveau"],
                "annees_experience": item["annees_experience"],
            }
            for item in competences
        ],
        "diplomes": [
            {
                "intitule": item["intitule"],
                "niveau": item["niveau"],
                "etablissement": item["etablissement"],
                "annee": item["annee"],
                "description": item["description"],
            }
            for item in diplomas
        ],
        "experiences": experiences,
        "metiers_detectes": list(dict.fromkeys(metiers)),
    }


def parse_cv_file(path: str | Path) -> ParsedCV:
    extracted = extract_text_from_cv(path)
    structured = parse_cv_text(extracted)
    return ParsedCV(text=extracted, structured=structured)
