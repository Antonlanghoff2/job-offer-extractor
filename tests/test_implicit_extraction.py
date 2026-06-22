# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Tests pour l'extraction de compétences implicites.

Ce module couvre les cas demandés pour valider la détection des
compétences implicites depuis les descriptions de missions.
"""

from __future__ import annotations

import pytest

from src.skill_extraction import (
    extract_implicit_skills,
    extract_skills_categorized,
    extract_skills_from_offer,
)
from src.skill_extraction.implicit_extractor import reset_caches


@pytest.fixture(autouse=True)
def clear_caches():
    """Réinitialise les caches avant chaque test."""
    reset_caches()
    yield
    reset_caches()


class TestImplicitExtractor:
    """Tests pour l'extraction implicite de base."""

    def test_mlops_implicite(self):
        """« Vous déploierez les modèles en production et surveillerez leur dérive » → MLOps."""
        text = "Vous déploierez les modèles en production et surveillerez leur dérive."
        skills, _ = extract_implicit_skills(text)
        names = [s.canonical_name for s in skills]
        assert "MLOps" in names or "Déploiement de modèles" in names

    def test_data_engineering_implicite(self):
        """« Vous concevrez des flux d'alimentation, de transformation et de contrôle des données » → Data Engineering."""
        text = "Vous concevrez des flux d'alimentation, de transformation et de contrôle des données."
        skills, _ = extract_implicit_skills(text)
        names = [s.canonical_name for s in skills]
        assert "Data Engineering" in names or "ETL" in names or "Pipelines de données" in names

    def test_backend_implicite(self):
        """« Vous développerez des services capables de traiter plusieurs milliers de requêtes » → Backend."""
        text = "Vous développerez des services capables de traiter plusieurs milliers de requêtes simultanées."
        skills, _ = extract_implicit_skills(text)
        names = [s.canonical_name for s in skills]
        assert "Backend" in names or "Scalabilité" in names or "Programmation concurrente" in names

    def test_securite_implicite(self):
        """« Vous sécuriserez les applications et gérerez l'authentification » → Sécurité."""
        text = "Vous sécuriserez les applications et gérerez l'authentification des utilisateurs."
        skills, _ = extract_implicit_skills(text)
        names = [s.canonical_name for s in skills]
        assert "Sécurité informatique" in names

    def test_gestion_projet_implicite(self):
        """« Vous piloterez le projet et coordonnerez les activités » → Gestion de projet."""
        text = "Vous piloterez le projet et coordonnerez les activités des équipes techniques."
        skills, _ = extract_implicit_skills(text)
        names = [s.canonical_name for s in skills]
        assert "Gestion de projet" in names


class TestNegationDetection:
    """Tests pour la détection des négations."""

    def test_negation_kubernetes(self):
        """« Aucune connaissance de Kubernetes n'est requise » → Kubernetes ne doit pas être extrait."""
        text = "Aucune connaissance de Kubernetes n'est requise pour ce poste."
        skills, _ = extract_implicit_skills(text)
        names = [s.canonical_name for s in skills]
        assert "Kubernetes" not in names

    def test_negation_docker(self):
        """« Vous n'utiliserez pas Docker » → Docker ne doit pas être extrait."""
        text = "Vous n'utiliserez pas Docker dans ce projet."
        skills, _ = extract_implicit_skills(text)
        names = [s.canonical_name for s in skills]
        assert "Docker" not in names

    def test_negation_sql(self):
        """« sans recours à une base SQL » → SQL ne doit pas être extrait."""
        text = "Vous travaillerez sans recours à une base SQL."
        skills, _ = extract_implicit_skills(text)
        names = [s.canonical_name for s in skills]
        assert "SQL" not in names


class TestFalsePositives:
    """Tests pour éviter les faux positifs."""

    def test_generic_team_work(self):
        """« Vous travaillerez dans une équipe dynamique » ne doit pas produire de compétences."""
        text = "Vous travaillerez dans une équipe dynamique et collaborative."
        skills, _ = extract_implicit_skills(text)
        names = [s.canonical_name for s in skills]
        assert "Travail en équipe" not in names
        assert "Communication" not in names
        assert "Leadership" not in names

    def test_generic_soft_skills(self):
        """Les phrases génériques sur les soft skills ne doivent pas produire de compétences."""
        text = "Nous recherchons une personne autonome avec un bon esprit d'équipe."
        skills, _ = extract_implicit_skills(text)
        names = [s.canonical_name for s in skills]
        assert len(names) == 0


class TestMultipleSkillsInSentence:
    """Tests pour plusieurs compétences dans une même phrase."""

    def test_multiple_skills_one_sentence(self):
        """Une phrase peut produire plusieurs compétences implicites."""
        text = "Vous concevrez des flux de données et déploierez les modèles en production."
        skills, _ = extract_implicit_skills(text)
        assert len(skills) >= 2

    def test_max_skills_per_sentence(self):
        """Le nombre de compétences par phrase est limité."""
        text = "Vous concevrez des flux de données, déploierez les modèles, surveillerez la dérive, sécuriserez les APIs, optimiserez les performances."
        skills, _ = extract_implicit_skills(text)
        assert len(skills) <= 15


class TestDeduplication:
    """Tests pour la déduplication entre explicite et implicite."""

    def test_explicit_takes_precedence(self):
        """Si une compétence existe explicitement, la version implicite est supprimée."""
        text = "Python requis. Vous développerez des applications Python."
        result = extract_skills_categorized(text)
        explicit_names = [s.canonical_name for s in result["competences_explicit"]]
        implicit_names = [s.canonical_name for s in result["competences_implicit"]]
        if "Python" in explicit_names:
            assert "Python" not in implicit_names

    def test_categorized_output(self):
        """La sortie catégorisée sépare bien les types d'extraction."""
        text = "Python et Docker requis. Vous déploierez les modèles en production."
        result = extract_skills_categorized(text)
        assert "competences_explicit" in result
        assert "competences_semantic" in result
        assert "competences_implicit" in result

        for skill in result["competences_explicit"]:
            assert skill.extraction_type == "explicit"
        for skill in result["competences_semantic"]:
            assert skill.extraction_type == "semantic"
        for skill in result["competences_implicit"]:
            assert skill.extraction_type == "implicit"


class TestDebugMode:
    """Tests pour le mode debug."""

    def test_debug_returns_info(self):
        """Le mode debug retourne des informations détaillées."""
        text = "Vous déploierez les modèles en production."
        skills, debug_infos = extract_implicit_skills(text, debug=True)
        assert len(debug_infos) > 0
        assert debug_infos[0].sentence is not None

    def test_debug_shows_rejection_reason(self):
        """Le mode debug indique la raison du rejet."""
        text = "Aucune connaissance de Kubernetes n'est requise."
        skills, debug_infos = extract_implicit_skills(text, debug=True)
        assert len(debug_infos) > 0
        assert any(d.is_negated for d in debug_infos)


class TestSkillReason:
    """Tests pour la justification des compétences implicites."""

    def test_implicit_skill_has_reason(self):
        """Chaque compétence implicite a une justification."""
        text = "Vous déploierez les modèles en production."
        skills, _ = extract_implicit_skills(text)
        for skill in skills:
            assert skill.reason is not None
            assert len(skill.reason) > 0

    def test_implicit_skill_has_source_sentence(self):
        """Chaque compétence implicite conserve sa phrase source."""
        text = "Vous déploierez les modèles en production."
        skills, _ = extract_implicit_skills(text)
        for skill in skills:
            assert skill.source_sentence is not None
            assert len(skill.source_sentence) > 0


class TestIntegration:
    """Tests d'intégration avec le pipeline complet."""

    def test_full_pipeline_with_implicit(self):
        """Le pipeline complet inclut les compétences implicites."""
        text = """
        Nous recherchons un Data Scientist.
        
        Missions :
        - Vous déploierez les modèles en production
        - Vous concevrez des flux de données
        - Vous surveillerez la dérive des modèles
        
        Profil :
        - Python et SQL requis
        """
        skills = extract_skills_from_offer(text)
        names = [s.canonical_name for s in skills]
        
        assert "Python" in names
        assert "SQL" in names
        assert any("MLOps" in n or "Déploiement" in n for n in names)

    def test_priority_explicit_over_implicit(self):
        """La priorité est respectée : explicite > sémantique > implicite."""
        text = "Python requis. Vous développerez des applications Python."
        skills = extract_skills_from_offer(text)
        python_skills = [s for s in skills if s.canonical_name == "Python"]
        assert len(python_skills) == 1
        assert python_skills[0].extraction_type == "explicit"
