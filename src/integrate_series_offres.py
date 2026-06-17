# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Integrate France Travail aggregated offer series for model 2 context."""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = (
    PROJECT_ROOT
    / "data_external"
    / "france_travail_series"
    / "series_offres_diffusees_T42025.xlsx"
)
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
CONTRAT_OUTPUT = PROCESSED_DIR / "contrat_long.csv"
METIER_OUTPUT = PROCESSED_DIR / "metier_context_t3_2025.csv"


def clean_column_name(value: object) -> str:
    """Return a simple snake_case column name."""
    text = str(value).strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("'", "_")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "colonne"


def clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize all dataframe column names."""
    result = df.copy()
    result.columns = [clean_column_name(col) for col in result.columns]
    return result


def find_sheet(sheet_names: list[str], expected_name: str) -> str:
    """Find a sheet by normalized name."""
    expected = clean_column_name(expected_name)
    for name in sheet_names:
        if clean_column_name(name) == expected:
            return name
    raise ValueError(
        f"Feuille '{expected_name}' introuvable. Feuilles disponibles: "
        f"{', '.join(sheet_names)}"
    )


def build_contrat_long(excel_file: pd.ExcelFile, sheet_name: str) -> pd.DataFrame:
    """Build a long contract-type monthly series."""
    df = clean_columns(pd.read_excel(excel_file, sheet_name=sheet_name))
    required = ["annee", "trimestre", "mois"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(
            "Colonnes manquantes dans la feuille Contrat: "
            + ", ".join(missing)
        )

    value_columns = [col for col in df.columns if col not in required]
    if not value_columns:
        raise ValueError("Aucune colonne de type de contrat trouvee.")

    long_df = df.melt(
        id_vars=required,
        value_vars=value_columns,
        var_name="type_contrat",
        value_name="nombre_offres",
    )
    long_df = long_df.dropna(subset=["nombre_offres"])
    long_df["nombre_offres"] = pd.to_numeric(
        long_df["nombre_offres"],
        errors="coerce",
    )
    long_df = long_df.dropna(subset=["nombre_offres"])
    return long_df


def build_metier_context(excel_file: pd.ExcelFile, sheet_name: str) -> pd.DataFrame:
    """Build the T3 2025 market context by job domain."""
    df = clean_columns(pd.read_excel(excel_file, sheet_name=sheet_name))
    df = df.loc[:, ~df.columns.str.startswith("unnamed")]
    df = df.dropna(how="all")

    required = [
        "grand_domaine",
        "domaine",
        "offres_au_t3_2025",
        "part_des_offres",
        "evolution_sur_un_an",
        "part_des_offres_durables",
    ]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(
            "Colonnes manquantes dans la feuille Metier: "
            + ", ".join(missing)
        )

    current_grand_domain: str | None = None
    grand_domains: list[str | None] = []
    domains: list[str | None] = []

    for row in df.itertuples(index=False):
        grand = getattr(row, "grand_domaine")
        domain = getattr(row, "domaine")
        grand_text = str(grand).strip() if pd.notna(grand) else ""
        domain_text = str(domain).strip() if pd.notna(domain) else ""

        if grand_text and grand_text.lower() != "dont" and not domain_text:
            current_grand_domain = grand_text

        grand_domains.append(current_grand_domain or grand_text or None)
        domains.append(domain_text or grand_text or None)

    result = df.copy()
    result["grand_domaine"] = grand_domains
    result["domaine"] = domains
    result = result.dropna(subset=["domaine", "offres_au_t3_2025"])

    numeric_columns = [
        "offres_au_t3_2025",
        "part_des_offres",
        "evolution_sur_un_an",
        "part_des_offres_durables",
        "difference_de_la_part_d_offres_durables_sur_un_an",
    ]
    for column in numeric_columns:
        if column in result.columns:
            result[column] = pd.to_numeric(result[column], errors="coerce")

    return result


def run() -> None:
    """Read the Excel workbook and export processed CSV files."""
    if not SOURCE_PATH.exists():
        print(
            "Erreur: fichier source absent: "
            f"{SOURCE_PATH.relative_to(PROJECT_ROOT)}",
            file=sys.stderr,
        )
        print(
            "Placez le fichier Excel dans "
            "data_external/france_travail_series/ avant de relancer.",
            file=sys.stderr,
        )
        sys.exit(1)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    excel_file = pd.ExcelFile(SOURCE_PATH, engine="openpyxl")
    print("Feuilles detectees:", ", ".join(excel_file.sheet_names))

    contrat_sheet = find_sheet(excel_file.sheet_names, "Contrat")
    metier_sheet = find_sheet(excel_file.sheet_names, "Metier")

    contrat_long = build_contrat_long(excel_file, contrat_sheet)
    metier_context = build_metier_context(excel_file, metier_sheet)

    contrat_long.to_csv(CONTRAT_OUTPUT, index=False)
    metier_context.to_csv(METIER_OUTPUT, index=False)

    print(
        f"CSV genere: {CONTRAT_OUTPUT.relative_to(PROJECT_ROOT)} "
        f"{contrat_long.shape}"
    )
    print(
        f"CSV genere: {METIER_OUTPUT.relative_to(PROJECT_ROOT)} "
        f"{metier_context.shape}"
    )


if __name__ == "__main__":
    run()
