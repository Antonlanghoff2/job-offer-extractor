#!/usr/bin/env python3
# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Script de validation avant/après pour l'extraction de compétences.

Ce script compare les résultats d'extraction de compétences avant et après
la correction du pipeline sur un échantillon d'offres France Travail.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.offer_normalization import normalize_france_travail_offer
from src.skill_extraction import extract_skills_from_offer
from src.trend_aggregation import aggregate_trends


def load_offres(path: Path) -> list[dict]:
    """Charge les offres depuis un fichier JSON."""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def extract_skills_old_way(offer: dict) -> list[str]:
    """Extrait les compétences à l'ancienne manière (champs structurés uniquement)."""
    competences = []
    for key in ("competences", "competences_requises", "competences_requises_noms"):
        for item in offer.get(key) or []:
            if isinstance(item, dict):
                label = item.get("libelle") or item.get("code") or item.get("name")
            else:
                label = item
            if label:
                competences.append(str(label).strip())
    return competences


def extract_skills_new_way(offer: dict) -> list[str]:
    """Extrait les compétences avec le nouveau pipeline."""
    description = offer.get("description") or ""
    structured = []
    for key in ("competences", "competences_requises"):
        for item in offer.get(key) or []:
            if isinstance(item, dict):
                label = item.get("libelle") or item.get("code")
            else:
                label = item
            if label:
                structured.append(str(label).strip())

    skills = extract_skills_from_offer(description, structured_competences=structured)
    return [s.canonical_name for s in skills if not s.negated]


def validate_sample(offres: list[dict], sample_size: int = 30) -> dict:
    """Valide l'extraction sur un échantillon d'offres."""
    sample = offres[:sample_size]

    old_results = {
        "total_offers": len(sample),
        "offers_with_skills": 0,
        "total_skills": 0,
        "skills_counter": Counter(),
        "examples": [],
    }

    new_results = {
        "total_offers": len(sample),
        "offers_with_skills": 0,
        "total_skills": 0,
        "skills_counter": Counter(),
        "examples": [],
    }

    for offer in sample:
        normalized = normalize_france_travail_offer(offer)

        old_skills = extract_skills_old_way(offer)
        if old_skills:
            old_results["offers_with_skills"] += 1
            old_results["total_skills"] += len(old_skills)
            for skill in old_skills:
                old_results["skills_counter"][skill] += 1

        new_skills = extract_skills_new_way(offer)
        if new_skills:
            new_results["offers_with_skills"] += 1
            new_results["total_skills"] += len(new_skills)
            for skill in new_skills:
                new_results["skills_counter"][skill] += 1

        if len(old_results["examples"]) < 5:
            old_results["examples"].append({
                "titre": normalized.get("intitule", ""),
                "old_skills": old_skills[:10],
                "new_skills": new_skills[:10],
            })

    return {
        "old": old_results,
        "new": new_results,
    }


def print_comparison(results: dict) -> None:
    """Affiche la comparaison avant/après."""
    old = results["old"]
    new = results["new"]

    print("=" * 80)
    print("VALIDATION AVANT/APRÈS EXTRACTION DE COMPÉTENCES")
    print("=" * 80)
    print()

    print("AVANT CORRECTION (champs structurés uniquement):")
    print(f"  - Offres analysées: {old['total_offers']}")
    print(f"  - Offres avec compétences: {old['offers_with_skills']}")
    print(f"  - Total compétences: {old['total_skills']}")
    print(f"  - Moyenne par offre: {old['total_skills'] / max(old['total_offers'], 1):.2f}")
    print(f"  - Compétences distinctes: {len(old['skills_counter'])}")
    print()

    print("APRÈS CORRECTION (pipeline hybride):")
    print(f"  - Offres analysées: {new['total_offers']}")
    print(f"  - Offres avec compétences: {new['offers_with_skills']}")
    print(f"  - Total compétences: {new['total_skills']}")
    print(f"  - Moyenne par offre: {new['total_skills'] / max(new['total_offers'], 1):.2f}")
    print(f"  - Compétences distinctes: {len(new['skills_counter'])}")
    print()

    print("AMÉLIORATION:")
    print(f"  - Offres avec compétences: +{new['offers_with_skills'] - old['offers_with_skills']}")
    print(f"  - Total compétences: +{new['total_skills'] - old['total_skills']}")
    print(f"  - Compétences distinctes: +{len(new['skills_counter']) - len(old['skills_counter'])}")
    print()

    print("TOP 10 AVANT:")
    for skill, count in old["skills_counter"].most_common(10):
        print(f"  {skill}: {count}")
    print()

    print("TOP 10 APRÈS:")
    for skill, count in new["skills_counter"].most_common(10):
        print(f"  {skill}: {count}")
    print()

    print("EXEMPLES:")
    for i, example in enumerate(new["examples"][:5], 1):
        print(f"\n  Offre {i}: {example['titre'][:60]}...")
        print(f"    AVANT: {example['old_skills'][:5]}")
        print(f"    APRÈS: {example['new_skills'][:5]}")


def main() -> None:
    """Point d'entrée principal."""
    data_dir = Path(__file__).resolve().parents[1] / "data" / "raw"
    offres_file = data_dir / "offres_france_travail.json"

    if not offres_file.exists():
        print(f"Fichier introuvable: {offres_file}")
        print("Veuillez d'abord exécuter: python -m src.import_offres")
        sys.exit(1)

    print(f"Chargement des offres depuis {offres_file}...")
    offres = load_offres(offres_file)
    print(f"{len(offres)} offres chargées.")
    print()

    results = validate_sample(offres, sample_size=30)
    print_comparison(results)


if __name__ == "__main__":
    main()
