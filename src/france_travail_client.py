# Copyright Anton Langhoff

import os
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire"
API_BASE_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2"

CLIENT_ID = os.getenv("FRANCE_TRAVAIL_CLIENT_ID")
CLIENT_SECRET = os.getenv("FRANCE_TRAVAIL_CLIENT_SECRET")


def get_access_token() -> str:
    if not CLIENT_ID or not CLIENT_SECRET:
        raise RuntimeError("FRANCE_TRAVAIL_CLIENT_ID ou FRANCE_TRAVAIL_CLIENT_SECRET manquant dans .env")

    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "scope": "api_offresdemploiv2 o2dsoffre",
        },
        timeout=20,
    )

    if response.status_code != 200:
        raise RuntimeError(f"Erreur token France Travail: {response.status_code} {response.text}")

    return response.json()["access_token"]


def search_offres(mots_cles: str, range_value: str = "0-149") -> dict:
    token = get_access_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    params = {
        "motsCles": mots_cles,
        "range": range_value,
    }

    response = requests.get(
        f"{API_BASE_URL}/offres/search",
        headers=headers,
        params=params,
        timeout=30,
    )

    if response.status_code not in (200, 206):
        raise RuntimeError(f"Erreur API France Travail: {response.status_code} {response.text}")

    return response.json()