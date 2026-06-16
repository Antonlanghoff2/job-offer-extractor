#!/usr/bin/env bash

set -e

echo "=== Job Offer Extractor - entraînement ==="

echo "1. Création du virtualenv si absent"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

echo "2. Activation du virtualenv"
source .venv/bin/activate

echo "3. Mise à jour pip"
python -m pip install --upgrade pip setuptools wheel

echo "4. Installation des dépendances"
python -m pip install -r requirements.txt

echo "5. Entraînement du modèle"
python -m src.train_classifier

echo "6. Évaluation du modèle"
python -m src.evaluate

echo "7. Test de prédiction"
python -m src.predict

echo "=== Terminé ==="
echo "Tu peux maintenant lancer :"
echo "source .venv/bin/activate"
echo "python app_cli.py"
