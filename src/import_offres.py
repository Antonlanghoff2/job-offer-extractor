# Copyright Anton Langhoff

import json
from pathlib import Path
from france_travail_client import search_offres

DATA_DIR = Path("data/raw")
DATA_DIR.mkdir(parents=True, exist_ok=True)


def main():
    result = search_offres("intelligence artificielle data python")

    offres = result.get("resultats", [])

    output_path = DATA_DIR / "offres_france_travail.json"

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(offres, f, ensure_ascii=False, indent=2)

    print(f"{len(offres)} offres enregistrées dans {output_path}")


if __name__ == "__main__":
    main()