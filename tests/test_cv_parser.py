# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

from __future__ import annotations

from src.cv_parser.education_extractor import extract_educations
from src.cv_parser.experience_extractor import extract_experiences
from src.cv_parser.parser import parse_cv_text
from src.cv_parser.skill_extractor import extract_explicit_skills, extract_skills_from_text


def test_multiline_education_block_is_grouped_into_one_entry() -> None:
    entries = extract_educations([
        "Mastère spécialisé",
        "Concepteur de Projet Digital",
        "Télécom ParisTech / INA",
        "2012 - 2013",
    ])

    assert len(entries) == 1
    entry = entries[0]
    assert entry["intitule"] == "Mastère spécialisé Concepteur de Projet Digital"
    assert entry["etablissement"] == "Télécom ParisTech / INA"
    assert entry["niveau"] == "Mastère spécialisé"
    assert entry["date_debut"] == "2012"
    assert entry["date_fin"] == "2013"


def test_mooc_formation_and_excluded_section() -> None:
    assert extract_educations(["MOOC Gestion de projet", "Centrale Lille"])[0]["etablissement"] == "Centrale Lille"
    assert extract_educations(["MOOC Symfony", "OpenClassrooms"])[0]["intitule"] == "MOOC Symfony"
    assert extract_educations(["Loisirs", "Voyages"]) == []
    assert extract_educations(["Centrale Lille"]) == []


def test_explicit_skills_deduplicate_variants() -> None:
    skills = extract_explicit_skills([
        "Symfony 5 / Symfony",
        "JS / JavaScript",
        "Postgres / PostgreSQL",
        "gestion projets / gestion de projet",
    ])

    assert [skill.nom for skill in skills] == ["Symfony", "JavaScript", "PostgreSQL", "Gestion de projet"]


def test_skills_detected_in_experience_and_formation_contexts() -> None:
    experience_skills = extract_skills_from_text(
        "Python et gestion de projet dans une expérience",
        source="experience_professionnelle",
    )
    formation_skills = extract_skills_from_text(
        "Mastère spécialisé Concepteur de projet digital",
        source="deduite_de_formation",
        formation_source="Mastère spécialisé Concepteur de projet digital",
    )

    assert {skill.nom for skill in experience_skills} == {"Python", "Gestion de projet"}
    assert formation_skills == []


def test_experience_block_is_grouped_into_one_entry() -> None:
    entries = extract_experiences([
        "Ingénieur du son",
        "Théâtre Exemple - Paris",
        "2018 - 2023",
        "Régie son, préparation du matériel, gestion des équipes techniques",
    ])

    assert len(entries) == 1
    entry = entries[0]
    assert entry["poste"] == "Ingénieur du son"
    assert entry["entreprise"] == "Théâtre Exemple"
    assert entry["lieu"] == "Paris"
    assert entry["date_debut"] == "2018"
    assert entry["date_fin"] == "2023"
    assert "Régie son" in entry["competences_associees"]


def test_two_consecutive_experiences_are_separated() -> None:
    text = "\n".join(
        [
            "Ingénieur du son",
            "Théâtre Exemple - Paris",
            "2018 - 2020",
            "Régie son, installation, exploitation technique",
            "",
            "Régisseur lumière",
            "Studio Lumière - Lyon",
            "2021 - aujourd'hui",
            "DMX, ArtNet, éclairage scénique",
        ]
    )
    parsed = parse_cv_text(text)

    assert len(parsed["experiences_professionnelles"]) == 2
    assert parsed["experiences_professionnelles"][1]["poste"] == "Régisseur lumière"
    assert "DMX" in parsed["competences"][0]["nom"] or any(skill["nom"] == "DMX" for skill in parsed["competences"])


def test_parser_returns_three_lists_and_preserves_brut_text() -> None:
    text = """Mastère spécialisé
Concepteur de Projet Digital
Télécom ParisTech / INA
2012 - 2013

Compétences
Python, SQL, Flask

Ingénieur du son
Théâtre Exemple - Paris
2018 - 2023
Régie son, préparation du matériel, gestion des équipes techniques
"""

    parsed = parse_cv_text(text)

    assert set(parsed) == {
        "formations",
        "competences",
        "experiences_professionnelles",
        "sections_detectees",
        "texte_brut",
        "warnings",
    }
    assert parsed["formations"]
    assert parsed["competences"]
    assert parsed["experiences_professionnelles"]
    assert parsed["texte_brut"].startswith("Mastère spécialisé")


def test_parser_fallback_extracts_content_from_plain_text_cv() -> None:
    text = """Jean Dupont
Développeur backend Python
Python, Flask, Docker
Mastère spécialisé Concepteur de Projet Digital
Télécom ParisTech / INA
2012 - 2013
Ingénieur du son
Théâtre Exemple - Paris
2018 - 2023
Régie son, installation, exploitation technique
"""

    parsed = parse_cv_text(text)

    assert parsed["formations"]
    assert parsed["competences"]
    assert parsed["experiences_professionnelles"]
    assert any(skill["nom"] == "Python" for skill in parsed["competences"])
    assert any(entry["intitule"].startswith("Mastère spécialisé") for entry in parsed["formations"])
    assert any(entry["poste"].startswith("Ingénieur du son") for entry in parsed["experiences_professionnelles"])
