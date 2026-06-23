# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Tests pour l'extraction de diplôme, salaire et télétravail depuis le texte."""

from __future__ import annotations

import pytest

from src.offer_field_extractors import (
    extract_diplomas_from_text,
    extract_salary_from_text,
    extract_teletravail_from_text,
)


class TestDiplomaExtraction:
    """Tests pour l'extraction de diplômes."""

    def test_bac_plus_3(self):
        """Bac +3 doit être extrait."""
        text = "Bac +3 en informatique requis."
        results = extract_diplomas_from_text(text)
        assert len(results) >= 1
        assert any("bac" in r["label"].lower() for r in results)

    def test_master(self):
        """Master doit être extrait."""
        text = "Master en informatique souhaité."
        results = extract_diplomas_from_text(text)
        assert len(results) >= 1
        assert any("master" in r["label"].lower() for r in results)

    def test_licence(self):
        """Licence doit être extrait."""
        text = "Licence en informatique requise."
        results = extract_diplomas_from_text(text)
        assert len(results) >= 1
        assert any("licence" in r["label"].lower() for r in results)

    def test_bts(self):
        """BTS doit être extrait."""
        text = "BTS SIO requis."
        results = extract_diplomas_from_text(text)
        assert len(results) >= 1
        assert any("bts" in r["label"].lower() for r in results)

    def test_negation(self):
        """Aucun diplôme ne doit être extrait si négation."""
        text = "Aucun diplôme particulier n'est requis."
        results = extract_diplomas_from_text(text)
        assert len(results) == 0

    def test_required_detection(self):
        """Doit détecter si le diplôme est obligatoire."""
        text = "Master requis."
        results = extract_diplomas_from_text(text)
        assert len(results) >= 1
        assert results[0]["required"] is True

    def test_optional_detection(self):
        """Doit détecter si le diplôme est souhaité."""
        text = "Master souhaité."
        results = extract_diplomas_from_text(text)
        assert len(results) >= 1
        assert results[0]["required"] is False


class TestSalaryExtraction:
    """Tests pour l'extraction de salaire."""

    def test_range_salary(self):
        """Fourchette de salaire doit être extraite."""
        text = "Salaire de 35 000 à 42 000 € brut annuel."
        result = extract_salary_from_text(text)
        assert result is not None
        assert result["minimum"] == 35000
        assert result["maximum"] == 42000
        assert result["currency"] == "EUR"
        assert result["period"] == "year"

    def test_single_salary(self):
        """Salaire unique doit être extrait."""
        text = "À partir de 2 300 € par mois."
        result = extract_salary_from_text(text)
        assert result is not None
        assert result["minimum"] == 2300
        assert result["period"] == "month"

    def test_daily_rate(self):
        """Taux journalier doit être extrait."""
        text = "450 € par jour."
        result = extract_salary_from_text(text)
        assert result is not None
        assert result["minimum"] == 450
        assert result["period"] == "day"

    def test_no_salary(self):
        """Texte sans salaire ne doit rien retourner."""
        text = "Selon profil."
        result = extract_salary_from_text(text)
        assert result is None

    def test_gross_detection(self):
        """Doit détecter brut/net."""
        text = "30 000 € net annuel."
        result = extract_salary_from_text(text)
        assert result is not None
        assert result["gross"] is False


class TestTeletravailExtraction:
    """Tests pour l'extraction de télétravail."""

    def test_full_remote(self):
        """Full remote doit être détecté."""
        text = "Poste en full remote."
        result = extract_teletravail_from_text(text)
        assert result is not None
        assert result["mode"] == "remote"

    def test_hybrid(self):
        """Hybride doit être détecté."""
        text = "2 jours de télétravail par semaine."
        result = extract_teletravail_from_text(text)
        assert result is not None
        assert result["mode"] == "hybrid"
        assert result["days_per_week"] == 2

    def test_onsite(self):
        """Présentiel doit être détecté."""
        text = "Poste entièrement sur site."
        result = extract_teletravail_from_text(text)
        assert result is not None
        assert result["mode"] == "onsite"

    def test_no_teletravail(self):
        """Aucun télétravail doit être détecté."""
        text = "Aucun télétravail prévu."
        result = extract_teletravail_from_text(text)
        assert result is not None
        assert result["mode"] == "onsite"

    def test_no_info(self):
        """Texte sans info télétravail ne doit rien retourner."""
        text = "Poste intéressant avec de bons avantages."
        result = extract_teletravail_from_text(text)
        assert result is None


class TestNormalizationIntegration:
    """Tests d'intégration avec la normalisation."""

    def test_normalize_france_travail_with_salary(self):
        """La normalisation doit inclure le salaire extrait du texte."""
        from src.offer_normalization import normalize_france_travail_offer

        raw_offer = {
            "id": "123",
            "intitule": "Développeur Python",
            "description": "Salaire de 38 000 à 45 000 € brut annuel.",
        }
        normalized = normalize_france_travail_offer(raw_offer)
        assert normalized.get("salaire_min") == 38000
        assert normalized.get("salaire_max") == 45000

    def test_normalize_france_travail_with_teletravail(self):
        """La normalisation doit inclure le télétravail extrait du texte."""
        from src.offer_normalization import normalize_france_travail_offer

        raw_offer = {
            "id": "123",
            "intitule": "Développeur Python",
            "description": "2 jours de télétravail par semaine.",
        }
        normalized = normalize_france_travail_offer(raw_offer)
        assert normalized.get("teletravail") == "hybrid"

    def test_normalize_france_travail_with_diploma(self):
        """La normalisation doit inclure les diplômes extraits du texte."""
        from src.offer_normalization import normalize_france_travail_offer

        raw_offer = {
            "id": "123",
            "intitule": "Développeur Python",
            "description": "Bac +3 en informatique requis.",
        }
        normalized = normalize_france_travail_offer(raw_offer)
        assert len(normalized.get("diplomes_requis", [])) >= 1

    def test_normalize_france_travail_with_experience(self):
        """La normalisation doit inclure l'expérience."""
        from src.offer_normalization import normalize_france_travail_offer

        raw_offer = {
            "id": "123",
            "intitule": "Développeur Python",
            "experienceLibelle": "3 ans d'expérience",
        }
        normalized = normalize_france_travail_offer(raw_offer)
        assert normalized.get("experience_requise") == "3 ans d'expérience"
