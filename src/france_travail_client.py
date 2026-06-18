# Copyright Anton Langhoff

"""France Travail API client with pagination and multi-query collection helpers."""

from __future__ import annotations

import json
import os
from collections import Counter
from typing import Any, Iterable

import requests
try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv(*args, **kwargs):
        return False

load_dotenv()

TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire"
API_BASE_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2"
DEFAULT_PAGE_SIZE = 150
MAX_RANGE_START = 3000

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


def _clean_param_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return str(value)


def _build_search_params(
    mots_cles: str,
    *,
    commune: str | None = None,
    departement: str | None = None,
    region: str | None = None,
    distance: int | None = None,
    range_value: str = "0-149",
) -> dict[str, Any]:
    params: dict[str, Any] = {}
    cleaned_mots = _clean_param_value(mots_cles)
    cleaned_range = _clean_param_value(range_value)
    if cleaned_mots:
        params["motsCles"] = cleaned_mots
    if cleaned_range:
        params["range"] = cleaned_range
    cleaned_commune = _clean_param_value(commune)
    cleaned_departement = _clean_param_value(departement)
    cleaned_region = _clean_param_value(region)
    if cleaned_commune:
        params["commune"] = cleaned_commune
    if cleaned_departement:
        params["departement"] = cleaned_departement
    if cleaned_region:
        params["region"] = cleaned_region
    if distance is not None:
        params["distance"] = distance
    return params


def _request_offres_page(
    token: str,
    mots_cles: str,
    range_value: str,
    *,
    commune: str | None = None,
    departement: str | None = None,
    region: str | None = None,
    distance: int | None = None,
) -> dict[str, Any]:
    response = requests.get(
        f"{API_BASE_URL}/offres/search",
        headers=_build_headers(token),
        params=_build_search_params(
            mots_cles,
            commune=commune,
            departement=departement,
            region=region,
            distance=distance,
            range_value=range_value,
        ),
        timeout=30,
    )

    # France Travail renvoie 204 quand il n'y a aucun résultat.
    # Ce n'est pas une erreur pour notre collecteur.
    if response.status_code == 204:
        return {"resultats": []}

    if response.status_code not in (200, 206):
        raise RuntimeError(
            "Erreur API France Travail "
            f"(motsCles='{mots_cles}', range='{range_value}'): "
            f"{response.status_code} {response.text}"
        )

    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(
            f"Réponse API inattendue pour motsCles='{mots_cles}' et range='{range_value}'"
        )
    return payload


def search_offres(
    mots_cles: str,
    *,
    commune: str | None = None,
    departement: str | None = None,
    region: str | None = None,
    distance: int | None = None,
    range_value: str = "0-149",
) -> dict[str, Any]:
    token = get_access_token()
    return _request_offres_page(
        token,
        mots_cles,
        range_value,
        commune=commune,
        departement=departement,
        region=region,
        distance=distance,
    )


def _offer_identifier(offer: dict[str, Any]) -> str:
    for key in ("id", "id_offre", "idOffre", "idOfr", "cle"):
        value = offer.get(key)
        if value not in (None, ""):
            return str(value)
    return json.dumps(offer, sort_keys=True, ensure_ascii=False)


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).strip().lower()


def _iter_location_texts(offer: dict[str, Any]) -> Iterable[str]:
    lieu = offer.get("lieuTravail")
    if isinstance(lieu, dict):
        for key in ("libelle", "commune", "codePostal"):
            value = lieu.get(key)
            if value:
                yield str(value)
    for key in ("territoire", "localisation", "location", "city", "ville"):
        value = offer.get(key)
        if value:
            yield str(value)


def _territory_matches_offer(offer: dict[str, Any], territoire: str) -> bool:
    target = _normalize_text(territoire)
    if not target:
        return False
    location_blob = _normalize_text(" ".join(_iter_location_texts(offer)))
    if not location_blob:
        return False
    return target in location_blob or location_blob in target


def _dedupe_offers(offers: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for offer in offers:
        identifier = _offer_identifier(offer)
        if identifier in seen:
            continue
        seen.add(identifier)
        deduped.append(offer)
    return deduped


def iter_search_offres(
    mots_cles: str,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_pages: int | None = None,
    max_results: int | None = None,
    *,
    commune: str | None = None,
    departement: str | None = None,
    region: str | None = None,
    distance: int | None = None,
) -> list[dict[str, Any]]:
    """Fetch France Travail search results across range windows."""
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    start = 0
    page_index = 0
    effective_page_size = min(max(page_size, 1), DEFAULT_PAGE_SIZE)

    while start <= MAX_RANGE_START:
        end = start + effective_page_size - 1
        payload = search_offres(
            mots_cles,
            commune=commune,
            departement=departement,
            region=region,
            distance=distance,
            range_value=f"{start}-{end}",
        )
        items = payload.get("resultats", [])
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
        if len(items) < effective_page_size or page_new == 0:
            break
        if max_pages is not None and page_index >= max_pages:
            break
        start += effective_page_size

    return results


def search_all_offres(
    queries: list[str],
    page_size: int = DEFAULT_PAGE_SIZE,
    max_pages: int | None = None,
    max_results: int | None = None,
    territoires: list[str] | None = None,
) -> dict[str, Any]:
    """Collect France Travail offers across multiple queries and optional territories.

    The function paginates every query with 150-result windows, merges the
    pages, filters by territory when requested, and deduplicates by France
    Travail identifier.
    """
    if not queries:
        raise ValueError("Au moins une requête doit être fournie.")

    normalized_territories = [t.strip() for t in territoires or [] if t and t.strip()]
    all_matches: list[dict[str, Any]] = []
    by_query: dict[str, int] = {}
    by_territory: Counter[str] = Counter()
    per_query_details: list[dict[str, Any]] = []

    for query in queries:
        query_results = iter_search_offres(
            query,
            page_size=page_size,
            max_pages=max_pages,
            max_results=max_results,
        )
        by_query[query] = len(query_results)
        retained = 0
        if normalized_territories:
            for offer in query_results:
                if any(_territory_matches_offer(offer, territory) for territory in normalized_territories):
                    all_matches.append(offer)
                    retained += 1
                    for territory in normalized_territories:
                        if _territory_matches_offer(offer, territory):
                            by_territory[territory] += 1
        else:
            all_matches.extend(query_results)
            retained = len(query_results)
        per_query_details.append({
            "query": query,
            "retrieved": len(query_results),
            "retained": retained,
        })

    total_before_dedup = len(all_matches)
    deduped = _dedupe_offers(all_matches)
    total_after_dedup = len(deduped)

    return {
        "offers": deduped,
        "queries": queries,
        "territoires": normalized_territories,
        "by_query": by_query,
        "by_territory": dict(by_territory),
        "per_query_details": per_query_details,
        "total_before_dedup": total_before_dedup,
        "total_after_dedup": total_after_dedup,
    }
