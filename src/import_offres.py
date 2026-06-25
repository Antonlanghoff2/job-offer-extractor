# Copyright Anton Langhoff

"""Fetch France Travail offers and store a paginated local snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

from src.france_travail_client import search_all_offres
from src.domain_config import get_all_queries, get_enabled_domains

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "raw"
DEFAULT_OUTPUT = DATA_DIR / "offres_france_travail.json"
DEFAULT_PAGE_SIZE = 150
REQUETES = [
    "intelligence artificielle",
    "machine learning",
    "deep learning",
    "data scientist",
    "data engineer",
    "data analyst",
    "developpeur IA",
    "ingenieur IA",
    "consultant IA",
    "machine learning engineer",
    "python",
    "llm",
    "rag",
    "langchain",
    "pytorch",
    "tensorflow",
    "nlp",
    "mlops",
]
TERRITOIRES = [
    "Paris",
    "Lyon",
    "Lille",
    "Toulouse",
    "Marseille",
    "Bordeaux",
    "Nantes",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download France Travail offers with pagination.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Chemin du JSON de sortie.")
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE, help="Nombre d'offres par page API.")
    parser.add_argument("--max-pages", type=int, default=None, help="Limite optionnelle du nombre de pages.")
    parser.add_argument("--max-results", type=int, default=None, help="Limite optionnelle du nombre total d'offres par requête.")
    parser.add_argument("--territory-mode", action="store_true", help="Active la collecte filtrée sur les territoires prédéfinis.")
    parser.add_argument("--territories", nargs="*", default=None, help="Territoires personnalisés. Remplace la liste prédéfinie si fourni.")
    parser.add_argument("--multi-domain", action="store_true", help="Active la collecte multi-métiers depuis config/job_domains.json.")
    return parser


def _print_query_stats(details: Iterable[dict]) -> None:
    for detail in details:
        print(f"- {detail['query']}: {detail['retrieved']} offres récupérées")


def main() -> None:
    args = build_parser().parse_args()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    territories = None
    if args.territories:
        territories = args.territories
    elif args.territory_mode:
        territories = TERRITOIRES

    if args.multi_domain:
        queries = get_all_queries()
        print(f"Collecte multi-métiers activée: {len(queries)} requêtes depuis {len(get_enabled_domains())} domaines")
    else:
        queries = REQUETES
        print(f"Collecte IA/Data: {len(queries)} requêtes")

    result = search_all_offres(
        queries,
        page_size=args.page_size,
        max_pages=args.max_pages,
        max_results=args.max_results,
        territoires=territories,
    )

    offres = result["offers"]

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(offres, f, ensure_ascii=False, indent=2)

    print("Offres récupérées par requête:")
    _print_query_stats(result["per_query_details"])
    if result["territoires"]:
        print("Offres retenues par territoire:")
        for territoire in result["territoires"]:
            print(f"- {territoire}: {result['by_territory'].get(territoire, 0)} offres")
    print(f"Total avant déduplication: {result['total_before_dedup']}")
    print(f"Total après déduplication: {result['total_after_dedup']}")
    print(f"{len(offres)} offres enregistrées dans {output_path}")


if __name__ == "__main__":
    main()
