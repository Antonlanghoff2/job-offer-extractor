# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Transformer-backed CV NER helpers with a local rule-based fallback.

The module is designed to work fully offline. If a trained checkpoint is
available locally, it is used for token classification. Otherwise, the
pipeline falls back to deterministic extraction so the CV flow remains usable.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Iterator

from src.services.cv_sections import detect_sections, first_lines, split_lines

PROJECT_ROOT = Path(__file__).resolve().parents[2]

try:  # pragma: no cover - optional dependency
    import torch
except ImportError:  # pragma: no cover - optional dependency
    torch = None

try:  # pragma: no cover - optional dependency
    from transformers import AutoModelForTokenClassification, AutoTokenizer, pipeline
except ImportError:  # pragma: no cover - optional dependency
    AutoModelForTokenClassification = None
    AutoTokenizer = None
    pipeline = None

MODEL_DEFAULT_NAME = "camembert-base"
MODEL_FALLBACK_NAME = "xlm-roberta-base"
LABEL_SKILL = "SKILL"
LABEL_DEGREE = "DEGREE"
LABEL_SCHOOL = "SCHOOL"
LABEL_COMPANY = "COMPANY"
LABEL_JOB = "JOB_TITLE"
LABEL_DATE = "DATE"
LABEL_EMAIL = "EMAIL"
LABEL_PHONE = "PHONE"
LABEL_LOCATION = "LOCATION"
LABEL_NAME = "NAME"


@dataclass(frozen=True)
class CvEntity:
    label: str
    text: str
    score: float | None = None
    start: int | None = None
    end: int | None = None
    section: str | None = None


@dataclass(frozen=True)
class CvNerConfig:
    """Configuration for the local CV extractor."""

    model_name: str = MODEL_DEFAULT_NAME
    model_dir: str | None = None
    local_files_only: bool = True
    force_fallback: bool = False
    max_chunk_chars: int = 2800


def _normalize_label(label: str | None) -> str:
    if not label:
        return ""
    value = str(label).upper().strip()
    for prefix in ("B-", "I-", "L-", "U-"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
    if "-" in value:
        value = value.split("-")[-1]
    return value


def _strip_bpe_token(token: str) -> str:
    return token.replace("##", "").strip()


def _dedupe(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = re.sub(r"\s+", " ", value).strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def _dedupe_skill_dicts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        name = re.sub(r"\s+", " ", str(item.get("nom") or "")).strip()
        key = name.lower()
        if not name or key in seen:
            continue
        seen.add(key)
        result.append({**item, "nom": name})
    return result


def _dedupe_degree_dicts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        title = re.sub(r"\s+", " ", str(item.get("intitule") or "")).strip()
        school = re.sub(r"\s+", " ", str(item.get("etablissement") or "")).strip()
        key = f"{title.lower()}|{school.lower()}"
        if not title and not school or key in seen:
            continue
        seen.add(key)
        result.append({**item, "intitule": title, "etablissement": school or None})
    return result


def _dedupe_experience_dicts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        title = re.sub(r"\s+", " ", str(item.get("poste") or "")).strip()
        company = re.sub(r"\s+", " ", str(item.get("entreprise") or "")).strip()
        key = f"{title.lower()}|{company.lower()}"
        if not title and not company or key in seen:
            continue
        seen.add(key)
        result.append({**item, "poste": title, "entreprise": company or None})
    return result


def _chunk_text(text: str, max_chars: int) -> list[str]:
    lines = split_lines(text)
    if not lines:
        return [text[:max_chars]]
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for line in lines:
        line_size = len(line) + 1
        if current and size + line_size > max_chars:
            chunks.append("\n".join(current))
            current = [line]
            size = line_size
        else:
            current.append(line)
            size += line_size
    if current:
        chunks.append("\n".join(current))
    return chunks or [text[:max_chars]]


def _has_checkpoint(model_dir: Path) -> bool:
    return any(
        (model_dir / candidate).exists()
        for candidate in ("config.json", "pytorch_model.bin", "model.safetensors")
    )


class CvNerModel:
    """Load and run a local token-classification model when available."""

    def __init__(self, config: CvNerConfig | None = None) -> None:
        self.config = config or CvNerConfig()
        self._pipeline = None
        self.model_source = "rules"
        self._load()

    @property
    def available(self) -> bool:
        return self._pipeline is not None

    def _load(self) -> None:
        if self.config.force_fallback:
            return
        if torch is None or pipeline is None or AutoTokenizer is None or AutoModelForTokenClassification is None:
            return

        locations: list[str] = []
        latest = PROJECT_ROOT / "models" / "cv_ner" / "latest"
        if latest.exists():
            locations.append(str(latest))
        if self.config.model_dir:
            locations.append(self.config.model_dir)
        locations.append(self.config.model_name)
        if MODEL_FALLBACK_NAME not in locations:
            locations.append(MODEL_FALLBACK_NAME)

        for location in locations:
            try:
                candidate = Path(location)
                if candidate.exists() and candidate.is_dir() and not _has_checkpoint(candidate):
                    continue
                tokenizer = AutoTokenizer.from_pretrained(location, local_files_only=self.config.local_files_only)
                model = AutoModelForTokenClassification.from_pretrained(
                    location,
                    local_files_only=self.config.local_files_only,
                )
                device = 0 if torch.cuda.is_available() else -1
                self._pipeline = pipeline(
                    "token-classification",
                    model=model,
                    tokenizer=tokenizer,
                    aggregation_strategy="simple",
                    device=device,
                )
                self.model_source = location
                return
            except Exception:
                continue

    def predict(self, text: str) -> list[CvEntity]:
        if not self.available:
            return []
        entities: list[CvEntity] = []
        for chunk in _chunk_text(text, self.config.max_chunk_chars):
            try:
                predictions = self._pipeline(chunk) or []
            except Exception:
                continue
            for item in predictions:
                label = _normalize_label(item.get("entity_group") or item.get("entity"))
                word = _strip_bpe_token(str(item.get("word") or item.get("text") or ""))
                if not label or not word:
                    continue
                entities.append(
                    CvEntity(
                        label=label,
                        text=word,
                        score=float(item.get("score") or 0.0),
                        start=item.get("start"),
                        end=item.get("end"),
                    )
                )
        return entities


def _find_lines_with_pattern(lines: list[str], pattern: str) -> list[str]:
    regex = re.compile(pattern, re.IGNORECASE)
    return [line for line in lines if regex.search(line)]


def _extract_contacts(text: str) -> dict[str, str]:
    email = re.search(r"[\w.\-+]+@[\w.\-]+\.\w+", text)
    phone = re.search(r"(?:\+?\d[\d .\-()]{7,}\d)", text)
    linkedin = re.search(r"https?://(?:www\.)?linkedin\.com/[^\s)]+", text, re.IGNORECASE)
    website = re.search(r"https?://[^\s)]+", text, re.IGNORECASE)
    return {
        "email": email.group(0) if email else "",
        "phone": phone.group(0) if phone else "",
        "linkedin": linkedin.group(0) if linkedin else "",
        "website": website.group(0) if website else "",
    }


def _extract_skill_candidates(lines: list[str], entities: list[CvEntity]) -> list[dict[str, Any]]:
    skills: list[dict[str, Any]] = []
    for entity in entities:
        if entity.label != LABEL_SKILL:
            continue
        skills.append({"nom": entity.text, "niveau": None, "annees_experience": None, "source": "ner"})

    for line in lines:
        parts = [part.strip() for part in re.split(r"[,;/|]", line) if part.strip()]
        if len(parts) < 2 and len(line.split()) > 6:
            continue
        for part in parts or [line]:
            if len(part) < 2:
                continue
            if re.search(r"\b(?:competence|competences|skills|stack|langages|outils)\b", part, re.I):
                continue
            skills.append({"nom": part, "niveau": None, "annees_experience": None, "source": "rules"})
    return _dedupe_skill_dicts(skills)


def _extract_degree_candidates(lines: list[str], entities: list[CvEntity]) -> list[dict[str, Any]]:
    degrees: list[dict[str, Any]] = []
    for entity in entities:
        if entity.label in {LABEL_DEGREE, LABEL_SCHOOL}:
            degrees.append(
                {
                    "intitule": entity.text if entity.label == LABEL_DEGREE else "",
                    "niveau": None,
                    "etablissement": entity.text if entity.label == LABEL_SCHOOL else None,
                    "annee": None,
                    "description": "",
                    "source": "ner",
                }
            )
    for line in lines:
        if len(line) < 3:
            continue
        if re.search(r"\b(?:diplome|master|licence|baccalaureat|ingenieur|engineering|msc|mba|bsc)\b", line, re.I):
            degrees.append(
                {
                    "intitule": line,
                    "niveau": None,
                    "etablissement": None,
                    "annee": None,
                    "description": "",
                    "source": "rules",
                }
            )
    return _dedupe_degree_dicts(degrees)


def _extract_experience_candidates(lines: list[str], entities: list[CvEntity]) -> list[dict[str, Any]]:
    experiences: list[dict[str, Any]] = []
    for entity in entities:
        if entity.label in {LABEL_JOB, LABEL_COMPANY}:
            experiences.append(
                {
                    "poste": entity.text if entity.label == LABEL_JOB else "",
                    "entreprise": entity.text if entity.label == LABEL_COMPANY else None,
                    "date_debut": None,
                    "date_fin": None,
                    "description": "",
                    "source": "ner",
                }
            )
    for line in lines:
        cleaned = line.strip()
        if not cleaned:
            continue
        parts = [part.strip() for part in re.split(r"\s+[-–|]\s+", cleaned) if part.strip()]
        experiences.append(
            {
                "poste": parts[0] if parts else cleaned,
                "entreprise": parts[1] if len(parts) > 1 else None,
                "date_debut": None,
                "date_fin": None,
                "description": "",
                "source": "rules",
            }
        )
    return _dedupe_experience_dicts(experiences)


def _detect_job_titles(text: str, entities: list[CvEntity], experiences: list[dict[str, Any]]) -> list[str]:
    titles = [entity.text for entity in entities if entity.label == LABEL_JOB]
    titles.extend(item.get("poste") for item in experiences if item.get("poste"))
    titles.extend(first_lines(text, 8))
    return _dedupe(str(title) for title in titles if title)


def build_structured_cv(text: str, entities: list[CvEntity] | None = None) -> dict[str, Any]:
    """Build a structured JSON payload from raw CV text."""

    entities = list(entities or [])
    sections = detect_sections(text)
    section_lines = sections.get("competences") or sections.get("misc") or split_lines(text)
    skill_lines = sections.get("competences") or section_lines
    diploma_lines = sections.get("diplomes") or sections.get("misc") or split_lines(text)
    experience_lines = sections.get("experiences") or sections.get("misc") or split_lines(text)

    skills = _extract_skill_candidates(skill_lines, entities)
    diplomas = _extract_degree_candidates(diploma_lines, entities)
    experiences = _extract_experience_candidates(experience_lines, entities)
    contacts = _extract_contacts(text)
    job_titles = _detect_job_titles(text, entities, experiences)

    return {
        "competences": skills,
        "diplomes": diplomas,
        "experiences": experiences,
        "metiers_detectes": job_titles,
        "contacts": contacts,
        "sections": sections,
    }


def load_jsonl_annotations(path: str | Path) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict) and payload.get("text"):
                samples.append(payload)
    return samples
