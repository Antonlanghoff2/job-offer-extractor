# Copyright Anton Langhoff

"""Fetch France Travail offers and store a paginated local snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.france_travail_client import iter_search_offres

DATA_DIR = Path("data/raw")
DEFAULT_QUERY = "intelligence artificielle data python"
DEFAULT_OUTPUT = DATA_DIR / "offres_france_travail.json"
DEFAULT_PAGE_SIZE = 150


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download France Travail offers with pagination.")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="Mots-clés de recherche France Travail.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Chemin du JSON de sortie.")
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE, help="Nombre d'offres par page API.")
    parser.add_argument("--max-pages", type=int, default=None, help="Limite optionnelle du nombre de pages.")
    parser.add_argument("--max-results", type=int, default=None, help="Limite optionnelle du nombre total d'offres.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    offres = iter_search_offres(
        args.query,
        page_size=args.page_size,
        max_pages=args.max_pages,
        max_results=args.max_results,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(offres, f, ensure_ascii=False, indent=2)

    print(f"{len(offres)} offres enregistrées dans {output_path}")


if __name__ == "__main__":
    main()
