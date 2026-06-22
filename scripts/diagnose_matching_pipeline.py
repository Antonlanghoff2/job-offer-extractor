#!/usr/bin/env python3
# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Diagnostic complet du pipeline de matching.

Ce script trace le flux complet des données pour une offre donnée et
identifie exactement où les données disparaissent.

Usage:
    python scripts/diagnose_matching_pipeline.py [offer_id]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.offer_normalization import normalize_france_travail_offer
from src.services.offer_normalization import normalize_offer_for_matching


def load_enriched_offers():
    """Charge les offres enrichies."""
    enriched_path = PROJECT_ROOT / "data" / "processed" / "offres_enrichies.json"
    if not enriched_path.exists():
        print(f"ERREUR: Fichier non trouvé: {enriched_path}")
        print("Exécutez d'abord: python scripts/reindex_offers.py")
        sys.exit(1)
    
    with enriched_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def find_offer(offers, offer_id=None):
    """Trouve une offre par ID ou retourne la première."""
    if offer_id:
        for offer in offers:
            if str(offer.get("id")) == str(offer_id):
                return offer
        print(f"ERREUR: Offre {offer_id} non trouvée")
        sys.exit(1)
    return offers[0] if offers else None


def print_section(title):
    """Affiche un séparateur de section."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def check_field(offer, field_name, expected=True):
    """Vérifie si un champ est présent et non vide."""
    value = offer.get(field_name)
    has_value = value is not None and value != [] and value != ""
    
    if expected and not has_value:
        return f"❌ {field_name}: ABSENT"
    elif not expected and has_value:
        return f"⚠️  {field_name}: présent (inattendu)"
    else:
        return f"✓ {field_name}: OK"


def main():
    offer_id = sys.argv[1] if len(sys.argv) > 1 else None
    
    print_section("CHARGEMENT DES OFFRES ENRICHIES")
    offers = load_enriched_offers()
    print(f"  {len(offers)} offres chargées")
    
    offer = find_offer(offers, offer_id)
    if not offer:
        print("ERREUR: Aucune offre disponible")
        sys.exit(1)
    
    print(f"\n  Offre sélectionnée: {offer.get('id')}")
    print(f"  Titre: {offer.get('intitule', 'N/A')[:80]}")
    
    # Étape 1: Offre enrichie (sortie de reindex_offers.py)
    print_section("ÉTAPE 1: OFFRE ENRICHIE (après réindexation)")
    print(f"\nChamps extraits:")
    print(f"  competences: {len(offer.get('competences', []))} compétences")
    if offer.get('competences'):
        for i, comp in enumerate(offer['competences'][:5], 1):
            print(f"    {i}. {comp}")
        if len(offer['competences']) > 5:
            print(f"    ... et {len(offer['competences']) - 5} autres")
    
    print(f"\n  salaire_min: {offer.get('salaire_min')}")
    print(f"  salaire_max: {offer.get('salaire_max')}")
    print(f"  teletravail: {offer.get('teletravail')}")
    print(f"  diplomes_requis: {len(offer.get('diplomes_requis', []))} diplômes")
    if offer.get('diplomes_requis'):
        for diploma in offer['diplomes_requis'][:3]:
            print(f"    - {diploma.get('label', 'N/A')} (niveau {diploma.get('level', '?')})")
    
    print(f"\n  experience_requise: {offer.get('experienceLibelle', 'N/A')}")
    
    # Étape 2: Normalisation (normalize_france_travail_offer)
    print_section("ÉTAPE 2: APRÈS normalize_france_travail_offer()")
    normalized = normalize_france_travail_offer(offer)
    
    print(f"\nChamps après normalisation:")
    print(f"  competences: {len(normalized.get('competences', []))} compétences")
    if normalized.get('competences'):
        for i, comp in enumerate(normalized['competences'][:5], 1):
            print(f"    {i}. {comp}")
    
    print(f"\n  salaire_min: {normalized.get('salaire_min')}")
    print(f"  salaire_max: {normalized.get('salaire_max')}")
    print(f"  teletravail: {normalized.get('teletravail')}")
    print(f"  diplomes_requis: {len(normalized.get('diplomes_requis', []))} diplômes")
    print(f"  experience_requise: {normalized.get('experience_requise')}")
    
    # Étape 3: Normalisation pour matching (normalize_offer_for_matching)
    print_section("ÉTAPE 3: APRÈS normalize_offer_for_matching()")
    offer_for_matching = normalize_offer_for_matching(normalized)
    
    print(f"\nChamps transmis au matching:")
    print(f"  competences: {len(offer_for_matching.get('competences', []))} compétences")
    if offer_for_matching.get('competences'):
        for i, comp in enumerate(offer_for_matching['competences'][:5], 1):
            print(f"    {i}. {comp}")
    
    print(f"\n  salaire_min: {offer_for_matching.get('salaire_min')}")
    print(f"  salaire_max: {offer_for_matching.get('salaire_max')}")
    print(f"  teletravail: {offer_for_matching.get('teletravail')}")
    print(f"  diplomes_requis: {len(offer_for_matching.get('diplomes_requis', []))} diplômes")
    print(f"  experience_requise: {offer_for_matching.get('experience_requise')}")
    
    # Analyse des pertes
    print_section("ANALYSE DES PERTES DE DONNÉES")
    
    issues = []
    
    # Compétences
    enriched_skills = len(offer.get('competences', []))
    normalized_skills = len(normalized.get('competences', []))
    matching_skills = len(offer_for_matching.get('competences', []))
    
    print(f"\nCompétences:")
    print(f"  Après réindexation: {enriched_skills}")
    print(f"  Après normalisation: {normalized_skills}")
    print(f"  Transmises au matching: {matching_skills}")
    
    if enriched_skills > 0 and normalized_skills == 0:
        issues.append("❌ Compétences perdues lors de normalize_france_travail_offer()")
    elif normalized_skills > 0 and matching_skills == 0:
        issues.append("❌ Compétences perdues lors de normalize_offer_for_matching()")
    elif matching_skills > 0:
        print(f"  ✓ Compétences transmises correctement")
    
    # Salaire
    enriched_salary = offer.get('salaire_min') or offer.get('salaire_max')
    normalized_salary = normalized.get('salaire_min') or normalized.get('salaire_max')
    matching_salary = offer_for_matching.get('salaire_min') or offer_for_matching.get('salaire_max')
    
    print(f"\nSalaire:")
    print(f"  Après réindexation: {enriched_salary}")
    print(f"  Après normalisation: {normalized_salary}")
    print(f"  Transmis au matching: {matching_salary}")
    
    if enriched_salary and not normalized_salary:
        issues.append("❌ Salaire perdu lors de normalize_france_travail_offer()")
    elif normalized_salary and not matching_salary:
        issues.append("❌ Salaire perdu lors de normalize_offer_for_matching()")
    elif matching_salary:
        print(f"  ✓ Salaire transmis correctement")
    else:
        print(f"  ⚠️  Aucun salaire extrait (normal si non mentionné)")
    
    # Télétravail
    enriched_teletravail = offer.get('teletravail')
    normalized_teletravail = normalized.get('teletravail')
    matching_teletravail = offer_for_matching.get('teletravail')
    
    print(f"\nTélétravail:")
    print(f"  Après réindexation: {enriched_teletravail}")
    print(f"  Après normalisation: {normalized_teletravail}")
    print(f"  Transmis au matching: {matching_teletravail}")
    
    if enriched_teletravail and not normalized_teletravail:
        issues.append("❌ Télétravail perdu lors de normalize_france_travail_offer()")
    elif normalized_teletravail and not matching_teletravail:
        issues.append("❌ Télétravail perdu lors de normalize_offer_for_matching()")
    elif matching_teletravail:
        print(f"  ✓ Télétravail transmis correctement")
    else:
        print(f"  ⚠️  Aucun télétravail extrait (normal si non mentionné)")
    
    # Diplômes
    enriched_diplomes = len(offer.get('diplomes_requis', []))
    normalized_diplomes = len(normalized.get('diplomes_requis', []))
    matching_diplomes = len(offer_for_matching.get('diplomes_requis', []))
    
    print(f"\nDiplômes:")
    print(f"  Après réindexation: {enriched_diplomes}")
    print(f"  Après normalisation: {normalized_diplomes}")
    print(f"  Transmis au matching: {matching_diplomes}")
    
    if enriched_diplomes > 0 and normalized_diplomes == 0:
        issues.append("❌ Diplômes perdus lors de normalize_france_travail_offer()")
    elif normalized_diplomes > 0 and matching_diplomes == 0:
        issues.append("❌ Diplômes perdus lors de normalize_offer_for_matching()")
    elif matching_diplomes > 0:
        print(f"  ✓ Diplômes transmis correctement")
    else:
        print(f"  ⚠️  Aucun diplôme extrait (normal si non mentionné)")
    
    # Résumé
    print_section("RÉSUMÉ")
    
    if issues:
        print("\nProblèmes identifiés:")
        for issue in issues:
            print(f"  {issue}")
        print(f"\nTotal: {len(issues)} problème(s)")
    else:
        print("\n✓ Toutes les données extraites sont correctement transmises au matching!")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
