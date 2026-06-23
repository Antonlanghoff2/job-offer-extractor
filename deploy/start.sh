#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -d .venv ]; then
  echo "Error: .venv is missing. Run ./deploy/install_ubuntu.sh first." >&2
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

if [ ! -f models/segment_classifier.joblib ]; then
  echo "Error: required model missing: models/segment_classifier.joblib" >&2
  exit 1
fi

if [ ! -f data/raw/offres_france_travail.json ]; then
  echo "Error: required dataset missing: data/raw/offres_france_travail.json" >&2
  exit 1
fi

exec .venv/bin/gunicorn \
  --bind "${APP_HOST:-127.0.0.1}:${APP_PORT:-8000}" \
  --workers "${GUNICORN_WORKERS:-2}" \
  --timeout "${GUNICORN_TIMEOUT:-120}" \
  --access-logfile - \
  --error-logfile - \
  "src.web_app:create_app()"