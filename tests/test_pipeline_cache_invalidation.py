# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Tests du pipeline de rafraîchissement et des invalidations de cache.

Ces tests couvrent les points de rupture observés dans le rafraîchissement
complet: validité des extractions mises en cache et recalcul des matchings
malgré les anciens artefacts de cache.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict
from unittest.mock import Mock

import pytest

from src.jobs.cache import CacheStore, compute_hash
from src.jobs.compute_matches import compute_all_matches
from src.jobs.extract_offer_data import EXTRACTION_CACHE_VERSION, extract_all_offer_data, extraction_is_complete
from src.db import SCHEMA_SQL


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _complete_extraction(offer_id: str, source_hash: str) -> Dict[str, Any]:
    return {
        "id": offer_id,
        "description": "Offre enrichie",
        "competences_requises_noms": ["Python"],
        "competences_requises_detaillees": [{"canonical_name": "Python"}],
        "diplomes_requis": [],
        "salaires": [],
        "contacts": [],
        "_extraction_metadata": {
            "extracted": True,
            "complete": True,
            "source_offer_id": offer_id,
            "source_offer_hash": source_hash,
            "extraction_version": EXTRACTION_CACHE_VERSION,
            "extracted_at": "2026-06-26T05:00:00+00:00",
            "competences_count": 1,
            "competences_detaillees_count": 1,
            "diplomes_count": 0,
            "salaires_count": 0,
            "contacts_count": 0,
            "has_salary": False,
            "has_teletravail": False,
        },
    }


class TestExtractionValidity:
    def test_extraction_is_complete_requires_meaningful_metadata(self) -> None:
        offer = _complete_extraction("1", "hash")
        assert extraction_is_complete(offer, EXTRACTION_CACHE_VERSION)

        incomplete = _complete_extraction("1", "hash")
        incomplete["_extraction_metadata"] = {
            **incomplete["_extraction_metadata"],
            "complete": False,
            "extracted": False,
            "competences_count": 0,
            "competences_detaillees_count": 0,
            "diplomes_count": 0,
            "salaires_count": 0,
            "contacts_count": 0,
            "has_salary": False,
            "has_teletravail": False,
        }
        incomplete.pop("competences_requises_noms", None)
        incomplete.pop("competences_requises_detaillees", None)
        assert not extraction_is_complete(incomplete, EXTRACTION_CACHE_VERSION)


class TestExtractOfferDataJob:
    def test_incomplete_cache_is_reprocessed_and_textless_offer_is_skipped(self, tmp_path, monkeypatch) -> None:
        normalized_path = tmp_path / "offres_normalisees.json"
        enriched_path = tmp_path / "offres_enrichies.json"
        cache_dir = tmp_path / "cache"
        cache_store = CacheStore(cache_dir)

        offers = [
            {"id": "1", "description": "Développeur Python", "intitule": "Développeur Python", "source": "France Travail"},
            {"id": "2", "description": "Data engineer", "intitule": "Data engineer", "source": "France Travail"},
            {"id": "3", "description": "", "intitule": "", "source": "France Travail"},
        ]
        _write_json(normalized_path, offers)

        monkeypatch.setattr("src.jobs.extract_offer_data.NORMALIZED_OFFERS_PATH", normalized_path)
        monkeypatch.setattr("src.jobs.extract_offer_data.ENRICHED_OFFERS_PATH", enriched_path)
        monkeypatch.setattr("src.jobs.extract_offer_data.cache_store", cache_store)

        first_hash = compute_hash(offers[0])
        second_hash = compute_hash(offers[1])

        cache_store.set(
            f"offer_extraction:v{EXTRACTION_CACHE_VERSION}:1",
            _complete_extraction("1", first_hash),
            input_hash=first_hash,
            source_version=EXTRACTION_CACHE_VERSION,
            model_version=EXTRACTION_CACHE_VERSION,
        )

        incomplete_cached = _complete_extraction("2", second_hash)
        incomplete_cached["_extraction_metadata"] = {
            **incomplete_cached["_extraction_metadata"],
            "complete": False,
            "extracted": False,
            "competences_count": 0,
            "competences_detaillees_count": 0,
            "diplomes_count": 0,
            "salaires_count": 0,
            "contacts_count": 0,
            "has_salary": False,
            "has_teletravail": False,
        }
        incomplete_cached.pop("competences_requises_noms", None)
        incomplete_cached.pop("competences_requises_detaillees", None)
        cache_store.set(
            f"offer_extraction:v{EXTRACTION_CACHE_VERSION}:2",
            incomplete_cached,
            input_hash=second_hash,
            source_version=EXTRACTION_CACHE_VERSION,
            model_version=EXTRACTION_CACHE_VERSION,
        )

        extraction_stub = Mock(return_value={
            "competences_requises_noms": ["Python"],
            "competences_requises_detaillees": [{"canonical_name": "Python"}],
            "diplomes_requis": [],
            "salaires": [],
            "contacts": [],
            "distanciel": None,
        })
        monkeypatch.setattr("src.jobs.extract_offer_data.extract_job_offer", extraction_stub)

        stats = extract_all_offer_data()
        enriched = json.loads(enriched_path.read_text(encoding="utf-8"))

        assert stats["total_offers"] == 3
        assert stats["processed"] == 1
        assert stats["skipped"] == 2
        assert stats["reasons"]["déjà extraite et valide"] == 1
        assert stats["reasons"]["texte absent"] == 1
        assert extraction_stub.call_count == 1
        assert enriched[0]["_extraction_metadata"]["complete"] is True
        assert enriched[1]["_extraction_metadata"]["complete"] is True
        assert enriched[2]["id"] == "3"


class TestComputeMatchesJob:
    def test_versioned_cache_forces_recompute_for_existing_users(self, tmp_path, monkeypatch) -> None:
        db_path = tmp_path / "trendradar.sqlite"
        offers_path = tmp_path / "offres_enrichies.json"
        matches_path = tmp_path / "matches.json"
        cache_store = CacheStore(tmp_path / "cache")

        conn = sqlite3.connect(db_path)
        try:
            conn.executescript(SCHEMA_SQL)
            conn.execute(
                "INSERT INTO users(email, password_hash, created_at, updated_at) VALUES (?, ?, ?, ?)",
                ("user@example.com", "hash", "2026-06-26T00:00:00+00:00", "2026-06-26T00:00:00+00:00"),
            )
            conn.commit()
        finally:
            conn.close()

        offers = [
            {
                "id": "offer-1",
                "titre": "Développeur Python",
                "description": "Développer des outils Python",
                "competences": ["Python"],
                "contrat": "CDI",
                "source": "France Travail",
            }
        ]
        _write_json(offers_path, offers)

        monkeypatch.setattr("src.jobs.compute_matches.DB_PATH", db_path)
        monkeypatch.setattr("src.jobs.compute_matches.ENRICHED_OFFERS_PATH", offers_path)
        monkeypatch.setattr("src.jobs.compute_matches.MATCHES_PATH", matches_path)
        monkeypatch.setattr("src.jobs.compute_matches.cache_store", cache_store)

        cache_store.set(
            "matches:user:1",
            [{"offer_id": "legacy", "score": 99.0}],
            input_hash="legacy",
        )

        compute_stub = Mock(return_value={
            "offer_identifier": "offer-1",
            "global_score": 88.0,
            "matching_skills": ["Python"],
            "missing_skills": [],
            "skill_score": 1.0,
            "job_score": 0.0,
            "experience_score": 0.0,
            "diploma_score": 0.0,
            "location_score": 0.0,
            "contract_score": 1.0,
            "remote_score": 0.0,
            "salary_score": 0.0,
            "explanation": {},
            "offer": offers[0],
        })
        monkeypatch.setattr("src.jobs.compute_matches.compute_match", compute_stub)

        stats = compute_all_matches()
        result = json.loads(matches_path.read_text(encoding="utf-8"))

        assert stats["total_users"] == 1
        assert stats["users_processed"] == 1
        assert stats["matches_computed"] == 1
        assert compute_stub.call_count == 1
        assert result["1"][0]["offer_id"] == "offer-1"
