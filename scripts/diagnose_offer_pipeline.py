#!/usr/bin/env python3
# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Diagnostic script to trace one offer through the extraction pipeline.

Usage:
    python scripts/diagnose_offer_pipeline.py [offer_id]

If no offer_id is provided, uses the first offer from the raw data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.predict import extract_job_offer
from src.offer_normalization import normalize_france_travail_offer
from src.services.offer_normalization import normalize_offer_for_matching


def load_raw_offers():
    """Load raw offers from JSON."""
    raw_path = PROJECT_ROOT / "data" / "raw" / "offres_france_travail.json"
    if not raw_path.exists():
        print(f"ERROR: File not found: {raw_path}")
        sys.exit(1)
    
    with raw_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def find_offer(offers, offer_id=None):
    """Find an offer by ID or return the first one."""
    if offer_id:
        for offer in offers:
            if str(offer.get("id")) == str(offer_id):
                return offer
        print(f"ERROR: Offer {offer_id} not found")
        sys.exit(1)
    return offers[0] if offers else None


def print_section(title):
    """Print a section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def main():
    offer_id = sys.argv[1] if len(sys.argv) > 1 else None
    
    print_section("LOADING RAW OFFERS")
    offers = load_raw_offers()
    print(f"Loaded {len(offers)} offers")
    
    offer = find_offer(offers, offer_id)
    if not offer:
        print("ERROR: No offers available")
        sys.exit(1)
    
    print(f"\nSelected offer ID: {offer.get('id')}")
    print(f"Title: {offer.get('intitule', 'N/A')}")
    
    # Step 1: Raw JSON
    print_section("STEP 1: RAW OFFER JSON (first 2000 chars)")
    raw_json = json.dumps(offer, ensure_ascii=False, indent=2)
    print(raw_json[:2000])
    if len(raw_json) > 2000:
        print(f"\n... (truncated, {len(raw_json)} total chars)")
    
    # Step 2: Text transmitted to extract_job_offer()
    print_section("STEP 2: TEXT TRANSMITTED TO extract_job_offer()")
    description = offer.get("description", "")
    print(f"Description length: {len(description)} chars")
    print(f"\nFirst 1000 chars:\n{description[:1000]}")
    if len(description) > 1000:
        print(f"\n... (truncated, {len(description)} total chars)")
    
    # Step 3: Result of extract_job_offer()
    print_section("STEP 3: RESULT OF extract_job_offer()")
    extraction_result = extract_job_offer(description, debug=True)
    print(json.dumps(extraction_result, ensure_ascii=False, indent=2))
    
    # Step 4: Normalized offer (what the web app uses)
    print_section("STEP 4: NORMALIZED OFFER (web app)")
    normalized = normalize_france_travail_offer(offer)
    print(json.dumps(normalized, ensure_ascii=False, indent=2))
    
    # Step 5: Offer for matching (what the matching service receives)
    print_section("STEP 5: OFFER FOR MATCHING (matching service)")
    offer_for_matching = normalize_offer_for_matching(normalized)
    print(json.dumps(offer_for_matching, ensure_ascii=False, indent=2))
    
    # Step 6: Analysis - what's missing?
    print_section("STEP 6: ANALYSIS - WHAT'S MISSING?")
    
    issues = []
    
    # Check skills
    skills_extracted = extraction_result.get("competences_requises_noms", [])
    skills_in_normalized = normalized.get("competences", [])
    skills_in_matching = offer_for_matching.get("competences", [])
    
    print(f"\nCompétences:")
    print(f"  - extract_job_offer(): {len(skills_extracted)} skills")
    print(f"  - normalized offer: {len(skills_in_normalized)} skills")
    print(f"  - offer for matching: {len(skills_in_matching)} skills")
    
    if not skills_in_matching:
        issues.append("❌ Compétences: ABSENT in offer for matching")
    elif len(skills_in_matching) < len(skills_extracted):
        issues.append(f"⚠️  Compétences: Only {len(skills_in_matching)}/{len(skills_extracted)} transferred")
    else:
        print(f"  ✓ Compétences OK")
    
    # Check salary
    salary_extracted = extraction_result.get("salaires", [])
    salary_min = offer_for_matching.get("salaire_min")
    salary_max = offer_for_matching.get("salaire_max")
    
    print(f"\nSalaire:")
    print(f"  - extract_job_offer(): {len(salary_extracted)} mentions")
    print(f"  - offer for matching: min={salary_min}, max={salary_max}")
    
    if salary_min is None and salary_max is None:
        issues.append("❌ Salaire: ABSENT in offer for matching")
    else:
        print(f"  ✓ Salaire OK")
    
    # Check remote/teletravail
    remote_extracted = extraction_result.get("distanciel")
    remote_in_matching = offer_for_matching.get("teletravail")
    
    print(f"\nTélétravail:")
    print(f"  - extract_job_offer(): {remote_extracted}")
    print(f"  - offer for matching: {remote_in_matching}")
    
    if remote_in_matching is None:
        issues.append("❌ Télétravail: ABSENT in offer for matching")
    else:
        print(f"  ✓ Télétravail OK")
    
    # Check diplomas
    diplomas_in_matching = offer_for_matching.get("diplomes_requis", [])
    
    print(f"\nDiplômes:")
    print(f"  - extract_job_offer(): NOT IMPLEMENTED")
    print(f"  - offer for matching: {len(diplomas_in_matching)} diplomas")
    
    if not diplomas_in_matching:
        issues.append("❌ Diplômes: ABSENT (extraction not implemented)")
    else:
        print(f"  ✓ Diplômes OK")
    
    # Check experience
    experience_in_matching = offer_for_matching.get("experience_requise")
    
    print(f"\nExpérience:")
    print(f"  - offer for matching: {experience_in_matching}")
    
    if experience_in_matching is None:
        issues.append("❌ Expérience: ABSENT in offer for matching")
    else:
        print(f"  ✓ Expérience OK")
    
    # Summary
    print_section("SUMMARY")
    if issues:
        print("\nIssues found:")
        for issue in issues:
            print(f"  {issue}")
        print(f"\nTotal issues: {len(issues)}")
    else:
        print("\n✓ All fields present!")
    
    print("\nRoot cause:")
    print("  extract_job_offer() is NOT called during offer normalization.")
    print("  It's only called from CLI (app_cli.py), not from web app.")
    print("\nSolution:")
    print("  1. Add diploma extraction to extract_job_offer()")
    print("  2. Create a reindexing script to process all offers")
    print("  3. Save extracted data to offer JSON")
    print("  4. Update normalization to use extracted data")


if __name__ == "__main__":
    main()
