# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""High-level CV parser producing structured JSON for validation."""

from __future__ import annotations

import logging
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - optional dependency
    PdfReader = None

try:
    from docx import Document
except ImportError:  # pragma: no cover - optional dependency
    Document = None

from .block_builder import build_blocks
from .education_extractor import extract_educations
from .experience_extractor import extract_experiences
from .normalizer import collapse_spaces, normalize_section_title
from .schemas import ParsedCV
from .skill_extractor import SkillMatch, extract_explicit_skills, extract_skills_from_text, merge_skill_matches

logger = logging.getLogger(__name__)

TEXT_LIMIT = 300_000
PDF_MIN_TEXT_LENGTH = 20


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
            logger.exception("Échec d'extraction PDF via pypdf")
    text_parts: List[str] = []
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
            logger.exception("Échec d'extraction DOCX via python-docx")
    with zipfile.ZipFile(path) as zf:
        try:
            data = zf.read("word/document.xml")
        except KeyError as exc:
            raise ValueError("Le fichier DOCX est invalide.") from exc
    root = ET.fromstring(data)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: List[str] = []
    for paragraph in root.findall(".//w:p", namespace):
        parts = [node.text for node in paragraph.findall(".//w:t", namespace) if node.text]
        line = "".join(parts).strip()
        if line:
            paragraphs.append(line)
    text = _clean_text("\n".join(paragraphs))
    if not text:
        raise ValueError("Le DOCX ne contient pas de texte exploitable.")
    return text[:TEXT_LIMIT]


def extract_text_from_cv(path: Any) -> str:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf_text(path)
    if suffix == ".docx":
        return _extract_docx_text(path)
    raise ValueError("Format non supporté. Seuls PDF et DOCX sont acceptés.")


def _sections_detected(blocks: List[Any]) -> Dict[str, bool]:
    flags = {"formations": False, "competences": False, "experiences_professionnelles": False}
    for block in blocks:
        section = getattr(block, "section", None)
        if section in flags:
            flags[section] = True
    return flags


def _dedupe(entries: List[Dict[str, Any]], key_fields: Tuple[str, ...]) -> List[Dict[str, Any]]:
    seen: set = set()
    deduped: List[Dict[str, Any]] = []
    for entry in entries:
        key = tuple(
            normalize_section_title(entry.get(field)) if field in {"intitule", "etablissement", "poste", "entreprise"} else collapse_spaces("" if entry.get(field) is None else str(entry.get(field))) or None
            for field in key_fields
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped


def parse_cv_text(text: str) -> Dict[str, Any]:
    cleaned_text = _clean_text(text)
    blocks = build_blocks(cleaned_text)
    sections_detected = _sections_detected(blocks)
    formations: List[Dict[str, Any]] = []
    experiences: List[Dict[str, Any]] = []
    skills: List[SkillMatch] = []
    warnings: List[str] = []

    for block in blocks:
        if block.section == "excluded":
            continue
        if block.section == "competences":
            skills.extend(extract_explicit_skills(block.lines))
            continue
        if block.section == "formations":
            parsed_formations = extract_educations(block.lines)
            formations.extend(parsed_formations)
            for formation in parsed_formations:
                formation_text = " ".join(filter(None, [str(formation.get("intitule") or ""), str(formation.get("description") or ""), str(formation.get("etablissement") or "")]))
                skills.extend(extract_skills_from_text(formation_text, source="deduite_de_formation", formation_source=str(formation.get("intitule") or "")))
            continue
        if block.section == "experiences_professionnelles":
            parsed_experiences = extract_experiences(block.lines)
            experiences.extend(parsed_experiences)
            for experience in parsed_experiences:
                exp_text = " ".join(filter(None, [str(experience.get("poste") or ""), str(experience.get("entreprise") or ""), str(experience.get("lieu") or ""), str(experience.get("description") or "")]))
                skills.extend(extract_skills_from_text(exp_text, source="experience_professionnelle"))
            continue

        parsed_formations = extract_educations(block.lines)
        parsed_experiences = extract_experiences(block.lines)
        if parsed_formations and not parsed_experiences:
            formations.extend(parsed_formations)
            for formation in parsed_formations:
                formation_text = " ".join(filter(None, [str(formation.get("intitule") or ""), str(formation.get("description") or "")]))
                skills.extend(extract_skills_from_text(formation_text, source="deduite_de_formation", formation_source=str(formation.get("intitule") or "")))
            continue
        if parsed_experiences and not parsed_formations:
            experiences.extend(parsed_experiences)
            for experience in parsed_experiences:
                exp_text = " ".join(filter(None, [str(experience.get("poste") or ""), str(experience.get("description") or "")]))
                skills.extend(extract_skills_from_text(exp_text, source="experience_professionnelle"))
            continue
        if len(block.lines) <= 6 and any(any(sep in line for sep in (",", ";", "|", "•")) for line in block.lines):
            skills.extend(extract_explicit_skills(block.lines))

    if not sections_detected["competences"] and not formations and not experiences:
        for block in blocks:
            if block.section not in {"formations", "experiences_professionnelles", "excluded"}:
                skills.extend(extract_explicit_skills(block.lines))

    formations = _dedupe(formations, ("intitule", "etablissement", "date_debut", "date_fin"))
    experiences = _dedupe(experiences, ("poste", "entreprise", "date_debut", "date_fin"))
    skills = merge_skill_matches(skills)

    if not any(sections_detected.values()):
        warnings.append("Aucune section explicite n’a été détectée.")
    if not formations and not experiences and not skills:
        warnings.append("Aucun élément exploitable n’a pu être extrait.")

    return {
        "formations": formations,
        "competences": [skill.as_dict() for skill in skills],
        "experiences_professionnelles": experiences,
        "sections_detectees": sections_detected,
        "texte_brut": cleaned_text,
        "warnings": warnings,
    }


def parse_cv_file(path: Any) -> ParsedCV:
    extracted = extract_text_from_cv(path)
    structured = parse_cv_text(extracted)
    return ParsedCV(text=extracted, structured=structured)
