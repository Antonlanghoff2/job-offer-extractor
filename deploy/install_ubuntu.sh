#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 is required but was not found." >&2
  exit 1
fi

if [ ! -f requirements.txt ]; then
  echo "Error: requirements.txt is missing." >&2
  exit 1
fi

python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

mkdir -p data/raw data/processed data_external models

if [ ! -f models/segment_classifier.joblib ]; then
  echo "Error: required model missing: models/segment_classifier.joblib" >&2
  echo "Train it first with: python -m src.train_classifier" >&2
  exit 1
fi

if [ ! -f data/raw/offres_france_travail.json ]; then
  echo "Error: required dataset missing: data/raw/offres_france_travail.json" >&2
  echo "Generate it first with: python -m src.import_offres --output data/raw/offres_france_travail.json" >&2
  exit 1
fi

if [ ! -f .env ] && [ -f .env.example ]; then
  cp .env.example .env
  echo "Created .env from .env.example. Fill in the France Travail credentials if needed."
fi

if [ ! -f data/processed/metier_context_t3_2025.csv ]; then
  echo "Warning: data/processed/metier_context_t3_2025.csv is missing; the market context section will be empty." >&2
fi

if [ ! -f data/processed/tendances.json ]; then
  echo "Warning: data/processed/tendances.json is missing; trend snapshots will be computed on demand." >&2
fi

echo "Installation complete."
echo "Launch with: ./deploy/start.sh"
