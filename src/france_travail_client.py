# Copyright Anton Langhoff

"""France Travail API client with pagination helpers."""

from __future__ import annotations

import json
import os
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire"
API_BASE_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2"
DEFAULT_PAGE_SIZE = 150

CLIENT_ID = os.getenv("FRANCE_TRAVAIL_CLIENT_ID")
CLIENT_SECRET = os.getenv("FRANCE_TRAVAIL_CLIENT_SECRET")


def get_access_token() -> str:
    if not CLIENT_ID or not CLIENT_SECRET:
        raise RuntimeError(
            "FRANCE_TRAVAIL_CLIENT_ID ou FRANCE_TRAVAIL_CLIENT_SECRET manquant dans .env"
        )

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
        raise RuntimeError(
            f"Erreur token France Travail: {response.status_code} {response.text}"
        )

    return response.json()["access_token"]


def _build_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }


def search_offres(mots_cles: str, range_value: str = "0-149") -> dict[str, Any]:
    token = get_access_token()
    response = requests.get(
        f"{API_BASE_URL}/offres/search",
        headers=_build_headers(token),
        params={"motsCles": mots_cles, "range": range_value},
        timeout=30,
    )
    if response.status_code not in (200, 206):
        raise RuntimeError(
            f"Erreur API France Travail: {response.status_code} {response.text}"
        )
    return response.json()


def _offer_identifier(offer: dict[str, Any]) -> str:
    for key in ("id", "id_offre", "idOffre", "idOfr", "cle"):
        value = offer.get(key)
        if value not in (None, ""):
            return str(value)
    return json.dumps(offer, sort_keys=True, ensure_ascii=False)


def iter_search_offres(
    mots_cles: str,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_pages: int | None = None,
    max_results: int | None = None,
) -> list[dict[str, Any]]:
    """Fetch France Travail search results across range windows.

    The API accepts range windows such as ``0-149``. This helper keeps
    requesting consecutive windows until the API returns fewer results than the
    page size, no new offers are seen, or optional limits are reached.
    """
    token = get_access_token()
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    start = 0
    page_index = 0

    while True:
        end = start + max(page_size, 1) - 1
        response = requests.get(
            f"{API_BASE_URL}/offres/search",
            headers=_build_headers(token),
            params={"motsCles": mots_cles, "range": f"{start}-{end}"},
            timeout=30,
        )
        if response.status_code not in (200, 206):
            raise RuntimeError(
                f"Erreur API France Travail: {response.status_code} {response.text}"
            )

        payload = response.json()
        items = payload.get("resultats", []) if isinstance(payload, dict) else []
        if not isinstance(items, list) or not items:
            break

        page_new = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            identifier = _offer_identifier(item)
            if identifier in seen:
                continue
            seen.add(identifier)
            results.append(item)
            page_new += 1
            if max_results is not None and len(results) >= max_results:
                return results[:max_results]

        page_index += 1
        if len(items) < page_size or page_new == 0:
            break
        if max_pages is not None and page_index >= max_pages:
            break
        start += page_size

    return results
