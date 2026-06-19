# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.model2_market_context import normalize_market_offer
from src.services.formation_recommendation import build_recommendation_context, recommend_training


def _write_config(tmp_path: Path, domain_ids: Optional[List[str]] = None) -> Path:
    config = {
        "domains": [
            {
                "id": "rag_ai",
                "titre": "Développer des applications d’IA générative avec RAG",
                "aliases": ["IA générative", "RAG", "LLM"],
                "competences": [
                    {"nom": "Python", "aliases": ["python"]},
                    {"nom": "LLM", "aliases": ["large language models"]},
                    {"nom": "RAG", "aliases": ["retrieval augmented generation"]},
                    {"nom": "FastAPI", "aliases": ["fast api"]},
                    {"nom": "Docker", "aliases": ["containerisation"]},
                    {"nom": "PostgreSQL", "aliases": ["postgres", "postgresql"]},
                ],
                "metiers": ["Développeur IA", "Data Scientist", "Ingénieur Machine Learning"],
                "public_cible": "Développeurs Python et professionnels de la data",
                "prerequis": ["Bases de Python", "Notions d’API REST"],
                "objectifs": [
                    "Comprendre le fonctionnement des LLM",
                    "Construire un pipeline RAG",
                    "Évaluer la qualité des réponses",
                    "Déployer une API d’inférence",
                ],
                "modules": [
                    {"titre": "Fondamentaux des LLM", "duree_heures": 7},
                    {"titre": "Embeddings et bases vectorielles", "duree_heures": 7},
                    {"titre": "Construction d’un pipeline RAG", "duree_heures": 14},
                    {"titre": "API, Docker et mise en production", "duree_heures": 14},
                ],
            },
            {
                "id": "backend_python",
                "titre": "Concevoir et industrialiser un backend Python",
                "aliases": ["backend python", "api python", "python backend"],
                "competences": [
                    {"nom": "Python", "aliases": ["python"]},
                    {"nom": "FastAPI", "aliases": ["fast api"]},
                    {"nom": "PostgreSQL", "aliases": ["postgres", "postgresql"]},
                    {"nom": "Docker", "aliases": ["containerisation"]},
                    {"nom": "REST API", "aliases": ["api rest"]},
                ],
                "metiers": ["Développeur Python", "Développeur backend", "Ingénieur logiciel"],
                "public_cible": "Développeurs backend",
                "prerequis": ["Bases de Python", "Modélisation des données"],
                "objectifs": ["Construire une API robuste", "Déployer un service Python"],
                "modules": [
                    {"titre": "API REST avec FastAPI", "duree_heures": 14},
                    {"titre": "Persistance PostgreSQL", "duree_heures": 7},
                    {"titre": "Conteneurisation Docker", "duree_heures": 7},
                ],
            },
        ]
    }
    if domain_ids is not None:
        config["domains"] = [domain for domain in config["domains"] if domain.get("id") in set(domain_ids)]
    path = tmp_path / "formation_domains.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return path


def _offer(skills: List[str], metier: str = "Développeur Python", niveau: str = "intermédiaire", description: str = "") -> Dict[str, Any]:
    return {
        "intitule_poste": metier,
        "metier": metier,
        "competences_requises": skills,
        "niveau": niveau,
        "contrat": "CDI",
        "territoire": "Lyon",
        "date_publication": "2026-06-01",
        "description": description,
    }


def test_normalize_market_offer_accepts_both_skill_fields() -> None:
    legacy = normalize_market_offer({"competences_requises": ["Python", "python", "Docker"]})
    modern = normalize_market_offer({"competences": ["Python", "Docker"]})
    assert legacy["competences"] == ["Python", "Docker"]
    assert modern["competences"] == ["Python", "Docker"]


def test_deduplicates_skills_within_offer() -> None:
    normalized = normalize_market_offer({"competences": ["Python", "python", " Python ", "Docker"]})
    assert normalized["competences"] == ["Python", "Docker"]


def test_no_recommendation_under_five_offers(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, ["rag_ai"])
    offers = [_offer(["Python", "Docker"]) for _ in range(4)]
    assert recommend_training(offers, territoire="Lyon", config_path=config_path) is None


def test_rag_recommendation_is_structured(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, ["rag_ai"])
    offers = [
        _offer(["Python", "LLM", "RAG", "FastAPI", "Docker", "PostgreSQL"], metier="Ingénieur IA", description="Développement d’applications IA générative, RAG et LLM"),
        _offer(["Python", "LLM", "RAG", "Docker", "PostgreSQL"], metier="Data Scientist", description="Développement d’applications IA générative, RAG et LLM"),
        _offer(["Python", "FastAPI", "Docker", "PostgreSQL"], metier="Développeur IA", description="Développement d’applications IA générative avec RAG et LLM"),
        _offer(["Python", "RAG", "LLM", "FastAPI", "Docker"], metier="Ingénieur Machine Learning", description="Développement d’applications IA générative, RAG et LLM"),
        _offer(["Python", "LLM", "RAG", "FastAPI", "PostgreSQL"], metier="Data Scientist", description="Développement d’applications IA générative, RAG et LLM"),
        _offer(["Python", "LLM", "RAG", "FastAPI", "Docker", "PostgreSQL"], metier="Développeur IA", description="Développement d’applications IA générative, RAG et LLM"),
    ]
    recommendation = recommend_training(offers, territoire="Lyon", config_path=config_path)
    assert recommendation is not None
    assert "IA générative" in recommendation["titre"]
    assert 0.0 <= recommendation["score_pertinence"] <= 1.0
    assert recommendation["niveau_confiance"] == "faible"
    assert recommendation["nombre_offres_analysees"] == 6
    assert recommendation["competences_cibles"]
    assert recommendation["modules"]
    assert recommendation["justification"]


def test_backend_python_recommendation(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, ["backend_python"])
    offers = [
        _offer(["Python", "FastAPI", "PostgreSQL", "Docker", "REST API"], metier="Développeur Python", description="Backend Python, API REST, Docker et PostgreSQL"),
        _offer(["Python", "FastAPI", "Docker", "PostgreSQL"], metier="Développeur backend", description="Backend Python, API REST, Docker et PostgreSQL"),
        _offer(["Python", "REST API", "Docker", "PostgreSQL"], metier="Ingénieur logiciel", description="Backend Python, API REST, Docker et PostgreSQL"),
        _offer(["Python", "FastAPI", "REST API", "Docker"], metier="Développeur backend", description="Backend Python, API REST, Docker et PostgreSQL"),
        _offer(["Python", "FastAPI", "PostgreSQL", "REST API"], metier="Développeur Python", description="Backend Python, API REST, Docker et PostgreSQL"),
        _offer(["Python", "Docker", "PostgreSQL", "REST API"], metier="Développeur backend", description="Backend Python, API REST, Docker et PostgreSQL"),
        _offer(["Python", "FastAPI", "Docker", "REST API"], metier="Ingénieur logiciel", description="Backend Python, API REST, Docker et PostgreSQL"),
        _offer(["Python", "FastAPI", "PostgreSQL", "Docker"], metier="Développeur Python", description="Backend Python, API REST, Docker et PostgreSQL"),
        _offer(["Python", "REST API", "PostgreSQL", "Docker"], metier="Développeur backend", description="Backend Python, API REST, Docker et PostgreSQL"),
        _offer(["Python", "FastAPI", "REST API", "PostgreSQL"], metier="Ingénieur logiciel", description="Backend Python, API REST, Docker et PostgreSQL"),
        _offer(["Python", "FastAPI", "Docker", "PostgreSQL", "REST API"], metier="Développeur Python", description="Backend Python, API REST, Docker et PostgreSQL"),
        _offer(["Python", "FastAPI", "Docker", "PostgreSQL"], metier="Développeur backend", description="Backend Python, API REST, Docker et PostgreSQL"),
        _offer(["Python", "REST API", "Docker", "PostgreSQL"], metier="Ingénieur logiciel", description="Backend Python, API REST, Docker et PostgreSQL"),
        _offer(["Python", "FastAPI", "REST API", "Docker"], metier="Développeur backend", description="Backend Python, API REST, Docker et PostgreSQL"),
        _offer(["Python", "FastAPI", "PostgreSQL", "REST API"], metier="Développeur Python", description="Backend Python, API REST, Docker et PostgreSQL"),
    ]
    recommendation = recommend_training(offers, territoire="Lyon", config_path=config_path)
    assert recommendation is not None
    assert "backend Python" in recommendation["titre"] or "Python" in recommendation["titre"]
    assert recommendation["niveau_confiance"] == "moyen"
    assert recommendation["score_pertinence"] > 0.0
    assert recommendation["metiers_cibles"]


def test_incoherent_dataset_keeps_bounded_score(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    offers = [
        {"competences": ["Python", "Docker"], "territoire": "Lyon", "date_publication": "2026-06-01"},
        {"competences_requises": ["MIDI", "DMX"], "territoire": "Lyon", "date_publication": "2026-06-01"},
        {"competences": ["LLM", "RAG"], "territoire": "Lyon", "date_publication": "2026-06-01"},
        {"competences": ["PostgreSQL"], "territoire": "Lyon", "date_publication": "2026-06-01"},
        {"competences": ["Python", "FastAPI"], "territoire": "Lyon", "date_publication": "2026-06-01"},
    ]
    recommendation = recommend_training(offers, territoire="Lyon", config_path=config_path)
    assert recommendation is not None
    assert 0.0 <= recommendation["score_pertinence"] <= 1.0
    assert recommendation["limites"]


def test_recommendation_json_is_stable(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    offers = [_offer(["Python", "FastAPI", "Docker", "PostgreSQL", "REST API"], metier="Développeur Python") for _ in range(15)]
    first = recommend_training(offers, territoire="Lyon", config_path=config_path)
    second = recommend_training(offers, territoire="Lyon", config_path=config_path)
    assert first == second


def test_build_recommendation_context_returns_ui_payload(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    offers = [_offer(["Python", "Docker", "PostgreSQL"], metier="Développeur Python") for _ in range(10)]
    context = build_recommendation_context(offers, territoire="Lyon", config_path=config_path)
    assert context["territoire"] == "Lyon"
    assert context["total_offers"] == 10
    assert context["recommendation"] is not None
