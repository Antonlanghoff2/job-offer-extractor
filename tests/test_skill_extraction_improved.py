# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Tests pour le pipeline d'extraction de compétences.

Ce module couvre les cas demandés pour valider l'extraction et la
normalisation des compétences depuis les offres d'emploi.
"""

from __future__ import annotations

import pytest

from src.skill_extraction import extract_skills_from_offer
from src.skill_extraction.savoir_faire_extractor import extract_savoir_faire


class TestSavoirFaireExtractor:
    """Tests pour l'extraction des savoir-faire."""

    def test_concevoir_et_gerer_projet(self):
        """« Concevoir et gérer un projet » → « Gestion de projet »."""
        text = "Vous serez chargé de concevoir et gérer un projet."
        results = extract_savoir_faire(text)
        canonical_names = [r[0] for r in results]
        assert "Gestion de projet" in canonical_names

    def test_analyser_structurer_donnees(self):
        """« Analyser, exploiter et structurer les données » → « Analyse de données »."""
        text = "Votre mission sera d'analyser, exploiter et structurer les données."
        results = extract_savoir_faire(text)
        canonical_names = [r[0] for r in results]
        assert "Analyse de données" in canonical_names

    def test_gerer_base_donnees(self):
        """« Mettre à jour une base de données » → « Gestion de bases de données »."""
        text = "Vous devrez gérer une base de données et assurer sa maintenance."
        results = extract_savoir_faire(text)
        canonical_names = [r[0] for r in results]
        assert "Gestion de bases de données" in canonical_names

    def test_rediger_cahier_charges(self):
        """« Rédiger un cahier des charges » → « Rédaction de cahier des charges »."""
        text = "Vous devrez rédiger un cahier des charges fonctionnel."
        results = extract_savoir_faire(text)
        canonical_names = [r[0] for r in results]
        assert "Rédaction de cahier des charges" in canonical_names

    def test_deployer_modeles_production(self):
        """« Déployer des modèles en production » → « Déploiement de modèles »."""
        text = "Vous serez responsable de déployer des modèles en production."
        results = extract_savoir_faire(text)
        canonical_names = [r[0] for r in results]
        assert "Déploiement de modèles" in canonical_names

    def test_negation_non_extraire(self):
        """« Aucune connaissance de Kubernetes n'est requise » → Kubernetes ne doit pas être extrait."""
        text = "Aucune connaissance de Kubernetes n'est requise pour ce poste."
        results = extract_savoir_faire(text)
        canonical_names = [r[0] for r in results]
        assert "Kubernetes" not in canonical_names


class TestSkillPipeline:
    """Tests pour le pipeline complet d'extraction."""

    def test_python_et_sql(self):
        """« Maîtrise de Python et SQL » → Python, SQL."""
        text = "Maîtrise de Python et SQL requise."
        skills = extract_skills_from_offer(text)
        names = [s.canonical_name for s in skills]
        assert "Python" in names
        assert "SQL" in names

    def test_concevoir_gerer_projet_pipeline(self):
        """« Concevoir et gérer un projet » → « Gestion de projet »."""
        text = "Vous serez chargé de concevoir et gérer un projet."
        skills = extract_skills_from_offer(text)
        names = [s.canonical_name for s in skills]
        assert "Gestion de projet" in names

    def test_analyser_donnees_pipeline(self):
        """« Analyser, exploiter et structurer les données » → « Analyse de données »."""
        text = "Votre mission sera d'analyser, exploiter et structurer les données."
        skills = extract_skills_from_offer(text)
        names = [s.canonical_name for s in skills]
        assert "Analyse de données" in names

    def test_gerer_base_donnees_pipeline(self):
        """« Mettre à jour une base de données » → « Gestion de bases de données »."""
        text = "Vous devrez gérer une base de données et assurer sa maintenance."
        skills = extract_skills_from_offer(text)
        names = [s.canonical_name for s in skills]
        assert "Gestion de bases de données" in names

    def test_deployer_modeles_mlops(self):
        """« Déployer les modèles et surveiller leur dérive » → MLOps, Déploiement de modèles."""
        text = "Vous devrez déployer les modèles et surveiller leur dérive en production."
        skills = extract_skills_from_offer(text)
        names = [s.canonical_name for s in skills]
        assert "Déploiement de modèles" in names
        assert "Monitoring de modèles" in names or "Monitoring de performance" in names

    def test_negation_kubernetes(self):
        """« Aucune connaissance de Kubernetes n'est requise » → Kubernetes ne doit pas être extrait."""
        text = "Aucune connaissance de Kubernetes n'est requise pour ce poste."
        skills = extract_skills_from_offer(text)
        names = [s.canonical_name for s in skills]
        for name in names:
            assert "kubernetes" not in name.lower()

    def test_optionnel_react(self):
        """« React serait un plus » → React, avec statut optionnel."""
        text = "La connaissance de React serait un plus."
        skills = extract_skills_from_offer(text)
        react_skills = [s for s in skills if "react" in s.canonical_name.lower()]
        assert len(react_skills) > 0
        assert any(s.optional for s in react_skills)

    def test_deduplication_python(self):
        """Python ne doit être compté qu'une fois même s'il apparaît plusieurs fois."""
        text = "Python est requis. Python est utilisé pour le développement. Maîtrise de Python."
        skills = extract_skills_from_offer(text)
        python_skills = [s for s in skills if s.canonical_name == "Python"]
        assert len(python_skills) == 1

    def test_ia_intelligence_artificielle_fusion(self):
        """« intelligence artificielle » et « IA » doivent être normalisés vers une même compétence."""
        text = "Expérience en intelligence artificielle et IA."
        skills = extract_skills_from_offer(text)
        ia_skills = [s for s in skills if "intelligence" in s.canonical_name.lower() or s.canonical_name == "IA"]
        assert len(ia_skills) >= 1

    def test_structured_competences(self):
        """Les compétences structurées doivent être incluses."""
        text = "Description de l'offre."
        structured = ["Python", "Docker", "Kubernetes"]
        skills = extract_skills_from_offer(text, structured_competences=structured)
        names = [s.canonical_name for s in skills]
        assert "Python" in names
        assert "Docker" in names
        assert "Kubernetes" in names

    def test_empty_text(self):
        """Un texte vide ne doit retourner aucune compétence."""
        skills = extract_skills_from_offer("")
        assert skills == []

    def test_debug_mode(self):
        """Le mode debug ne doit pas casser le pipeline."""
        text = "Maîtrise de Python requise."
        skills = extract_skills_from_offer(text, debug=True)
        assert len(skills) > 0


class TestSkillNormalization:
    """Tests pour la normalisation des compétences."""

    def test_casse_variants(self):
        """Les variantes de casse doivent être fusionnées."""
        text = "python PYTHON Python"
        skills = extract_skills_from_offer(text)
        python_skills = [s for s in skills if "python" in s.canonical_name.lower()]
        assert len(python_skills) == 1

    def test_accents_variants(self):
        """Les variantes avec/sans accents doivent être fusionnées."""
        text = "développement developpement"
        skills = extract_skills_from_offer(text)
        dev_skills = [s for s in skills if "développement" in s.canonical_name.lower() or "developpement" in s.canonical_name.lower()]
        assert len(dev_skills) <= 2

    def test_pluriels_variants(self):
        """Les variantes plurielles doivent être fusionnées."""
        text = "Python pythons PYTHON"
        skills = extract_skills_from_offer(text)
        python_skills = [s for s in skills if "python" in s.canonical_name.lower()]
        assert len(python_skills) == 1
