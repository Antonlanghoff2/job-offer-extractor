#!/usr/bin/env python3
# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Script de diagnostic pour le filtrage territorial.

Usage:
    python -m src.debug_territory_filter --territoire "Paris"
    python -m src.debug_territory_filter --territoire "75"
    python -m src.debug_territory_filter --territoire "Lyon"
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

from src.cache_reader import get_precomputed_offers, get_precomputed_trends
from src.territory_normalization import (
    extract_offer_territory_keys,
    filter_offers_by_territory,
    normalize_territory,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnostic du filtrage territorial")
    parser.add_argument("--territoire", type=str, help="Territoire à tester")
    parser.add_argument("--limit", type=int, default=5, help="Nombre d'offres à afficher")
    args = parser.parse_args()

    territory = args.territoire
    limit = args.limit

    print(f"=== Diagnostic territorial ===\n")
    print(f"Territoire demandé: {territory!r}")
    print(f"Territoire normalisé: {normalize_territory(territory)!r}\n")

    offers, error = get_precomputed_offers()
    if error:
        print(f"Erreur: {error}")
        return

    print(f"Total offres chargées: {len(offers)}\n")

    if territory:
        filtered = filter_offers_by_territory(offers, territory)
        print(f"Offres après filtrage: {len(filtered)}")
        print(f"Offres rejetées: {len(offers) - len(filtered)}\n")

        if filtered:
            print(f"=== Premières offres filtrées (limite={limit}) ===\n")
            for i, offer in enumerate(filtered[:limit], 1):
                keys = extract_offer_territory_keys(offer)
                print(f"{i}. {offer.get('intitule', 'Sans titre')}")
                print(f"   Territoire: {offer.get('territoire', 'N/A')}")
                print(f"   Ville: {offer.get('ville', 'N/A')}")
                print(f"   Clés territoriales: {sorted(keys)}")
                print()

        trends, trends_error = get_precomputed_trends(territoire=territory)
        if trends_error:
            print(f"Erreur tendances: {trends_error}")
        else:
            print(f"=== Tendances pour {territory!r} ===\n")
            print(f"Nombre d'offres (tendances): {trends.get('nombre_offres', 'N/A')}")
            competences = trends.get("competences", {})
            print(f"Top 5 compétences:")
            for i, (skill, count) in enumerate(list(competences.items())[:5], 1):
                print(f"  {i}. {skill}: {count}")
    else:
        print("Aucun territoire spécifié, affichage des tendances globales\n")
        trends, trends_error = get_precomputed_trends(territoire=None)
        if trends_error:
            print(f"Erreur tendances: {trends_error}")
        else:
            print(f"Nombre d'offres (global): {trends.get('nombre_offres', 'N/A')}")
            competences = trends.get("competences", {})
            print(f"Top 5 compétences:")
            for i, (skill, count) in enumerate(list(competences.items())[:5], 1):
                print(f"  {i}. {skill}: {count}")

    print("\n=== Territoires disponibles dans les tendances ===\n")
    from src.cache_reader import _load_json_file, TRENDS_PATH
    trends_data = _load_json_file(TRENDS_PATH)
    if trends_data:
        for key in list(trends_data.keys())[:10]:
            count = trends_data[key].get("nombre_offres", "N/A")
            print(f"  - {key}: {count} offres")
        if len(trends_data) > 10:
            print(f"  ... et {len(trends_data) - 10} autres")


if __name__ == "__main__":
    main()
