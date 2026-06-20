# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path
from typing import Dict
from unittest.mock import patch

import pytest

from src.matching.scoring import build_scoring_result, calculate_weighted_score
from src.matching.weights import DEFAULT_MATCHING_WEIGHTS, MATCHING_WEIGHT_KEYS, validate_matching_weights
from src.services.matching_service import calculate_matching_score
from src.web_app import create_app


def _default_weights() -> Dict[str, float]:
    return dict(DEFAULT_MATCHING_WEIGHTS)


@pytest.mark.parametrize("key", MATCHING_WEIGHT_KEYS)
def test_default_weights_total_100(key: str) -> None:
    assert round(sum(DEFAULT_MATCHING_WEIGHTS.values()), 2) == 100.0
    assert key in DEFAULT_MATCHING_WEIGHTS


def test_valid_custom_weights_are_accepted() -> None:
    weights = {
        "competences": "10",
        "metier": "15",
        "experience": "10",
        "diplome": "15",
        "localisation": "40",
        "contrat": "5",
        "teletravail": "5",
    }
    normalized, error = validate_matching_weights(weights)
    assert error == ""
    assert normalized == _default_weights()


def test_invalid_total_is_refused() -> None:
    weights = _default_weights()
    weights["competences"] = 9.0
    normalized, error = validate_matching_weights(weights)
    assert normalized == {}
    assert "100" in error


def test_negative_weight_is_refused() -> None:
    weights = _default_weights()
    weights["competences"] = -1.0
    normalized, error = validate_matching_weights(weights)
    assert normalized == {}
    assert "entre 0 et 100" in error


def test_too_large_weight_is_refused() -> None:
    weights = _default_weights()
    weights["competences"] = 120.0
    normalized, error = validate_matching_weights(weights)
    assert normalized == {}
    assert "entre 0 et 100" in error


def test_unknown_weight_key_is_refused() -> None:
    weights = _default_weights()
    weights["inconnu"] = 1.0
    normalized, error = validate_matching_weights(weights)
    assert normalized == {}
    assert "inconnues" in error


def test_absent_field_is_neutralized() -> None:
    score = calculate_weighted_score(
        {
            "competences": 0.8,
            "metier": 1.0,
            "experience": 0.5,
            "diplome": None,
            "localisation": 1.0,
            "contrat": 1.0,
            "teletravail": None,
        },
        _default_weights(),
    )
    assert score == 91.25


def test_present_but_incompatible_field_gets_zero() -> None:
    score = calculate_weighted_score(
        {
            "competences": 0.8,
            "metier": 1.0,
            "experience": 0.5,
            "diplome": 0.0,
            "localisation": 1.0,
            "contrat": 1.0,
            "teletravail": 0.0,
        },
        _default_weights(),
    )
    assert score == 73.0


def test_weight_redistribution_is_correct() -> None:
    result = build_scoring_result(
        {
            "competences": 0.8,
            "metier": 1.0,
            "experience": 0.5,
            "diplome": None,
            "localisation": 1.0,
            "contrat": 1.0,
            "teletravail": None,
        },
        _default_weights(),
        common_skills=["Python"],
        missing_skills=["Docker"],
        source="France Travail",
        url_originale="https://example.com",
    )
    assert result["score_global"] == 91.25
    assert result["sous_scores"]["diplome"]["statut"] == "champ_absent"
    assert result["sous_scores"]["diplome"]["poids_effectif"] == 0.0
    assert result["sous_scores"]["competences"]["poids_effectif"] == 12.5
    assert result["source"] == "France Travail"
    assert result["url_originale"] == "https://example.com"


def test_score_remains_bounded() -> None:
    result = calculate_weighted_score(
        {"competences": 1.0, "metier": 1.0, "experience": 1.0, "diplome": 1.0, "localisation": 1.0, "contrat": 1.0, "teletravail": 1.0},
        _default_weights(),
    )
    assert 0.0 <= result <= 100.0


def test_matching_result_contains_effective_weights_and_details() -> None:
    profile = {
        "skills": [{"name": "Python"}, {"name": "Flask"}],
        "desired_jobs": [{"job_title": "Développeur backend"}],
        "experiences": [{"job_title": "Développeur backend", "duration_years": 4}],
        "diplomas": [{"title": "Master Informatique"}],
        "city": "Lyon",
        "department": "69",
        "search_radius_km": 20,
        "remote_preference": "indifferent",
        "contract_preference": "CDI",
    }
    offer = {
        "id": "off-1",
        "titre": "Développeur backend Python",
        "entreprise": "ACME",
        "competences": ["Python", "Docker"],
        "diplomes_requis": ["Master Informatique"],
        "contrat": "CDI",
        "teletravail": "hybride",
        "lieux": ["Lyon"],
        "experience_requise": "3 ans",
        "url_originale": "https://example.com/of-1",
        "source": "France Travail",
    }

    result = calculate_matching_score(profile, offer, weights=_default_weights())
    assert "sous_scores" in result
    assert "matching_weights" in result
    assert result["sous_scores"]["competences"]["poids_effectif"] > 0
    assert result["criterion_scores"]["diplome"] is not None
    assert 0.0 <= result["global_score"] <= 100.0


@pytest.mark.parametrize("key", MATCHING_WEIGHT_KEYS)
def test_search_page_renders_weight_controls(key: str, tmp_path) -> None:
    app = create_app({"TESTING": True, "SECRET_KEY": "test-secret", "DATABASE_PATH": str(tmp_path / "trendradar.sqlite"), "UPLOAD_FOLDER": str(tmp_path / "uploads")})
    client = app.test_client()

    def _offers(*args, **kwargs):
        return [
            {
                "id": "1",
                "intitule": "Développeur Python",
                "description": "Construire des outils IA.",
                "dateCreation": "2026-06-17T10:00:00Z",
                "territoire": "Lyon",
                "lieuTravail": {"libelle": "Lyon", "commune": "Lyon", "codePostal": "69000"},
                "entreprise": {"nom": "ACME"},
                "typeContratLibelle": "CDI",
                "origineOffre": {"urlOrigine": "https://example.com/1"},
                "competences": [{"libelle": "Python"}],
            }
        ]

    with patch("src.web_app.load_raw_offers", return_value=_offers()), patch("src.web_app.load_market_context_rows", return_value=[]), patch("src.web_app.iter_search_offres", return_value=_offers()):
        response = client.get("/?mots_cles=python")
        body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Personnaliser les critères de matching" in body
    assert "data-matching-weights-form" in body
    assert "data-search-submit" in body


def test_client_side_script_disables_search_when_total_differs() -> None:
    script_path = Path("static/js/matching_weights.js")
    content = script_path.read_text(encoding="utf-8")
    assert "submitButton.disabled = !valid" in content
    assert "Le total des pondérations doit être égal à 100 %" in content


def test_valid_weights_are_kept_in_session(tmp_path) -> None:
    app = create_app({"TESTING": True, "SECRET_KEY": "test-secret", "DATABASE_PATH": str(tmp_path / "trendradar.sqlite"), "UPLOAD_FOLDER": str(tmp_path / "uploads")})
    client = app.test_client()

    offers = [
        {
            "id": "1",
            "intitule": "Développeur Python",
            "description": "Construire des outils IA.",
            "dateCreation": "2026-06-17T10:00:00Z",
            "territoire": "Lyon",
            "lieuTravail": {"libelle": "Lyon", "commune": "Lyon", "codePostal": "69000"},
            "entreprise": {"nom": "ACME"},
            "typeContratLibelle": "CDI",
            "origineOffre": {"urlOrigine": "https://example.com/1"},
            "competences": [{"libelle": "Python"}],
        }
    ]

    query = (
        "/?mots_cles=python&matching_weights_competences=10&matching_weights_metier=15"
        "&matching_weights_experience=10&matching_weights_diplome=15&matching_weights_localisation=40"
        "&matching_weights_contrat=5&matching_weights_teletravail=5"
    )
    with patch("src.web_app.load_raw_offers", return_value=offers), patch("src.web_app.load_market_context_rows", return_value=[]), patch("src.web_app.iter_search_offres", return_value=offers):
        response = client.get(query)
        assert response.status_code == 200
        with client.session_transaction() as sess:
            assert sess["matching_weights"]["competences"] == 10.0

        response = client.get("/?mots_cles=python")
        body = response.get_data(as_text=True)

    assert 'value="10"' in body
