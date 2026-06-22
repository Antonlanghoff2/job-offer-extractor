#!/usr/bin/env python3
# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Script de réindexation des offres d'emploi.

Ce script retraite toutes les offres déjà enregistrées pour extraire
les compétences, salaires, télétravail et diplômes depuis le texte.

Usage:
    python scripts/reindex_offers.py [--input PATH] [--output PATH] [--limit N]

Options:
    --input PATH    Chemin du fichier JSON d'entrée (défaut: data/raw/offres_france_travail.json)
    --output PATH   Chemin du fichier JSON de sortie (défaut: data/processed/offres_enrichies.json)
    --limit N       Nombre maximum d'offres à traiter (défaut: toutes)
    --force         Forcer le retraitement même si les données existent déjà
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.predict import extract_job_offer


def load_raw_offers(input_path: Path) -> List[Dict[str, Any]]:
    """Charge les offres brutes depuis un fichier JSON."""
    if not input_path.exists():
        print(f"ERREUR: Fichier non trouvé: {input_path}")
        sys.exit(1)
    
    with input_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    
    if not isinstance(data, list):
        print(f"ERREUR: Le fichier doit contenir une liste JSON")
        sys.exit(1)
    
    return [offer for offer in data if isinstance(offer, dict)]


def enrich_offer(offer: Dict[str, Any]) -> Dict[str, Any]:
    """Enrichit une offre avec les données extraites du texte."""
    # Copier l'offre originale
    enriched = offer.copy()
    
    # Extraire le texte complet
    description = offer.get("description", "")
    if not description:
        return enriched
    
    # Exécuter extract_job_offer()
    try:
        extraction = extract_job_offer(description, debug=False)
    except Exception as e:
        print(f"  ⚠️  Erreur lors de l'extraction: {e}")
        return enriched
    
    # Mapper les champs extraits vers les champs attendus par le matching
    # salaires → salaire_min, salaire_max
    salaires = extraction.get("salaires", [])
    if salaires:
        # Parser les salaires pour extraire min/max
        salary_values = []
        for salaire in salaires:
            # Extraire les nombres du texte
            import re
            numbers = re.findall(r'\d[\d\s]{1,6}', salaire)
            for num in numbers:
                cleaned = num.replace(" ", "")
                try:
                    value = int(cleaned)
                    if value >= 1000:  # Ignorer les petits nombres
                        salary_values.append(value)
                except ValueError:
                    pass
        
        if salary_values:
            enriched["salaire_min"] = min(salary_values)
            enriched["salaire_max"] = max(salary_values)
    
    # distanciel → teletravail
    distanciel = extraction.get("distanciel")
    if distanciel:
        enriched["teletravail"] = distanciel
    
    # competences_requises_noms → competences
    competences_noms = extraction.get("competences_requises_noms", [])
    if competences_noms:
        enriched["competences"] = competences_noms
    
    # diplomes_requis → diplomes_requis
    diplomes = extraction.get("diplomes_requis", [])
    if diplomes:
        enriched["diplomes_requis"] = diplomes
    
    # Ajouter les métadonnées d'extraction
    enriched["_extraction_metadata"] = {
        "extracted": True,
        "competences_count": len(competences_noms),
        "diplomes_count": len(diplomes),
        "has_salary": bool(salaires),
        "has_teletravail": distanciel is not None,
    }
    
    return enriched


def generate_report(offers: List[Dict[str, Any]]) -> None:
    """Génère un rapport avant/après."""
    print("\n" + "=" * 80)
    print("  RAPPORT DE RÉINDEXATION")
    print("=" * 80)
    
    total = len(offers)
    with_competences = sum(1 for o in offers if o.get("competences"))
    with_salary = sum(1 for o in offers if o.get("salaire_min") or o.get("salaire_max"))
    with_teletravail = sum(1 for o in offers if o.get("teletravail"))
    with_diplomes = sum(1 for o in offers if o.get("diplomes_requis"))
    
    print(f"\nTotal offres traitées: {total}")
    print(f"\nAvec au moins une compétence: {with_competences} ({with_competences/total*100:.1f}%)")
    print(f"Avec salaire: {with_salary} ({with_salary/total*100:.1f}%)")
    print(f"Avec télétravail: {with_teletravail} ({with_teletravail/total*100:.1f}%)")
    print(f"Avec diplômes: {with_diplomes} ({with_diplomes/total*100:.1f}%)")
    
    print("\n" + "=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Réindexer les offres d'emploi")
    parser.add_argument("--input", type=Path, default=PROJECT_ROOT / "data" / "raw" / "offres_france_travail.json")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "data" / "processed" / "offres_enrichies.json")
    parser.add_argument("--limit", type=int, default=None, help="Nombre maximum d'offres à traiter")
    parser.add_argument("--force", action="store_true", help="Forcer le retraitement")
    args = parser.parse_args()
    
    print(f"Chargement des offres depuis: {args.input}")
    offers = load_raw_offers(args.input)
    print(f"  {len(offers)} offres chargées")
    
    if args.limit:
        offers = offers[:args.limit]
        print(f"  Limité à {len(offers)} offres")
    
    print(f"\nTraitement des offres...")
    enriched_offers = []
    
    for i, offer in enumerate(offers, 1):
        if i % 100 == 0:
            print(f"  Traitement: {i}/{len(offers)}")
        
        enriched = enrich_offer(offer)
        enriched_offers.append(enriched)
    
    print(f"\nSauvegarde vers: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(enriched_offers, f, ensure_ascii=False, indent=2)
    
    print(f"  {len(enriched_offers)} offres sauvegardées")
    
    # Générer le rapport
    generate_report(enriched_offers)
    
    print("\n✅ Réindexation terminée!")
    print(f"\nProchaine étape: Mettre à jour l'application pour utiliser {args.output}")


if __name__ == "__main__":
    main()
