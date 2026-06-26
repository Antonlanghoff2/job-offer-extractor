# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Tests pytest pour le matching de la page « Mes offres ».

Ces tests verrouillent les règles métier attendues sur les sous-scores
compétences, expérience, diplôme et contrat, ainsi que la cohérence
du score global pondéré.
"""

from __future__ import annotations

import pytest

from src.services.matching_service import (
    calculate_matching_score,
    compute_contract_score,
    compute_diploma_score,
    compute_experience_score,
    compute_skill_score,
)


@pytest.mark.parametrize(
    "profile_skills, offer_skills, expected_reason",
    [
        ([], ["Python", "Django"], "aucune compétence commune"),
        ([{"name": "Python", "normalized_name": "python"}], [], "aucune compétence commune"),
        ([{"name": "Python", "normalized_name": "python"}], ["Java", "Spring"], "aucune compétence commune"),
    ],
)
def test_no_common_skills_returns_zero(profile_skills, offer_skills, expected_reason) -> None:
    result = compute_skill_score(profile_skills, offer_skills)
    assert result.score == 0.0
    assert result.applicable is True
    assert expected_reason in result.details.get("reason", "")


@pytest.mark.parametrize(
    "profile_experiences, offer_experience, expected_reason",
    [
        ([], None, "expérience non renseignée"),
        ([], "3 ans", "aucune expérience compatible"),
        ([{"duration_years": 0.0}], "3 ans", "aucune expérience compatible"),
    ],
)
def test_experience_rules_return_zero(profile_experiences, offer_experience, expected_reason) -> None:
    result = compute_experience_score(profile_experiences, offer_experience)
    assert result.score == 0.0
    assert result.applicable is True
    assert expected_reason in result.details.get("reason", "")


@pytest.mark.parametrize(
    "profile_diplomas, offer_diplomas, expected_reason",
    [
        ([], ["Master Informatique"], "diplôme non renseigné"),
        ([{"title": "Master Informatique"}], [], "aucun diplôme compatible"),
        ([{"title": "Master Informatique"}], ["Licence Économie", "BTS Commerce"], "aucun diplôme compatible"),
    ],
)
def test_diploma_rules_return_zero(profile_diplomas, offer_diplomas, expected_reason) -> None:
    result = compute_diploma_score(profile_diplomas, offer_diplomas)
    assert result.score == 0.0
    assert result.applicable is True
    assert expected_reason in result.details.get("reason", "")


@pytest.mark.parametrize(
    "profile_contract, offer_contract, expected_reason",
    [
        (None, "CDI", "contrat non renseigné"),
        ("CDI", None, "contrat non renseigné"),
        ("CDI", "CDD", "contrat différent"),
    ],
)
def test_contract_rules_return_zero(profile_contract, offer_contract, expected_reason) -> None:
    result = compute_contract_score(profile_contract, offer_contract)
    assert result.score == 0.0
    assert result.applicable is True
    assert expected_reason in result.details.get("reason", "")


def test_exact_match_returns_hundred() -> None:
    profile = {
        "skills": [{"name": "Python", "normalized_name": "Python"}],
        "experiences": [{"duration_years": 3.0}],
        "diplomas": [{"title": "Master Informatique"}],
        "contract_preference": "CDI",
    }
    offer = {
        "id": "match-1",
        "titre": "Développeur Python",
        "competences": ["Python"],
        "experience_requise": "3 ans",
        "diplomes_requis": ["Master Informatique"],
        "contrat": "CDI",
        "source": "France Travail",
    }

    result = calculate_matching_score(profile, offer)

    assert result["skill_score"] == 100.0
    assert result["experience_score"] == 100.0
    assert result["diploma_score"] == 100.0
    assert result["contract_score"] == 100.0
    assert result["global_score"] == 100.0
    assert result["criterion_scores"]["competences"] == 1.0
    assert result["explanation"]["subscores"]["competences"] == 100.0


def test_partial_match_returns_partial_score() -> None:
    profile = {
        "skills": [{"name": "Python", "normalized_name": "Python"}],
        "experiences": [{"duration_years": 1.5}],
        "diplomas": [{"title": "Licence Informatique"}],
        "contract_preference": "CDI",
    }
    offer = {
        "id": "match-2",
        "titre": "Développeur Python",
        "competences": ["Python", "Flask"],
        "experience_requise": "3 ans",
        "diplomes_requis": ["Licence Informatique"],
        "contrat": "CDI",
        "source": "France Travail",
    }

    result = calculate_matching_score(profile, offer)

    assert 1.0 <= result["skill_score"] < 100.0
    assert 1.0 <= result["global_score"] < 100.0


def test_global_score_drops_when_multiple_criteria_are_zero() -> None:
    profile = {
        "skills": [],
        "experiences": [],
        "diplomas": [],
        "contract_preference": None,
    }
    offer = {
        "id": "match-3",
        "titre": "Développeur Python",
        "competences": ["Python", "Flask"],
        "experience_requise": "3 ans",
        "diplomes_requis": ["Master Informatique"],
        "contrat": "CDI",
        "source": "France Travail",
    }

    result = calculate_matching_score(profile, offer)

    assert result["skill_score"] == 0.0
    assert result["experience_score"] == 0.0
    assert result["diploma_score"] == 0.0
    assert result["contract_score"] == 0.0
    assert result["global_score"] == 0.0
    assert result["criterion_scores"]["competences"] == 0.0
    assert result["criterion_scores"]["experience"] == 0.0
    assert result["criterion_scores"]["diplome"] == 0.0
    assert result["criterion_scores"]["contrat"] == 0.0


def test_displayed_scores_use_the_same_values_as_global_computation() -> None:
    profile = {
        "skills": [],
        "experiences": [],
        "diplomas": [],
        "contract_preference": None,
    }
    offer = {
        "id": "match-4",
        "titre": "Développeur Python",
        "competences": ["Python"],
        "experience_requise": "3 ans",
        "diplomes_requis": ["Master Informatique"],
        "contrat": "CDI",
        "source": "France Travail",
    }

    result = calculate_matching_score(profile, offer)

    assert result["skill_score"] == 0.0
    assert result["experience_score"] == 0.0
    assert result["diploma_score"] == 0.0
    assert result["contract_score"] == 0.0
    assert result["explanation"]["subscores"]["competences"] == 0.0
    assert result["explanation"]["subscores"]["experience"] == 0.0
    assert result["explanation"]["subscores"]["diplome"] == 0.0
    assert result["explanation"]["subscores"]["contrat"] == 0.0
