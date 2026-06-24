# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Normalisation et filtrage territorial pour TrendRadar IA.

Ce module fournit des fonctions pour normaliser les territoires,
extraire les clés territoriales des offres, et filtrer les offres
par territoire de manière robuste.
"""

from __future__ import annotations

import os
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Set


def _strip_accents(value: str) -> str:
    """Supprime les accents d'une chaîne.

    Args:
        value: Chaîne à normaliser.

    Returns:
        Chaîne sans accents.
    """
    text = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def normalize_territory(value: Optional[str]) -> Optional[str]:
    """Normalise un territoire pour comparaison.

    Supprime les espaces, accents, met en minuscules,
    et normalise les tirets et codes.

    Args:
        value: Territoire à normaliser.

    Returns:
        Territoire normalisé ou None si vide.

    Examples:
        >>> normalize_territory("Paris")
        'paris'
        >>> normalize_territory("Île-de-France")
        'ile-de-france'
        >>> normalize_territory("75")
        '75'
        >>> normalize_territory("  Lyon  ")
        'lyon'
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = _strip_accents(text)
    text = text.lower()
    text = re.sub(r"[^\w\-]", "-", text)
    text = re.sub(r"-+", "-", text)
    text = text.strip("-")
    if not text:
        return None
    return text


def extract_territory_code(value: str) -> Optional[str]:
    """Extrait un code département ou commune d'un territoire.

    Args:
        value: Territoire (ex: "75", "69 - LYON", "75001").

    Returns:
        Code extrait ou None.

    Examples:
        >>> extract_territory_code("75")
        '75'
        >>> extract_territory_code("69 - LYON 01")
        '69'
        >>> extract_territory_code("75001")
        '75001'
    """
    if not value:
        return None
    text = str(value).strip()
    match = re.match(r"^(\d{2,5})", text)
    if match:
        return match.group(1)
    return None


def extract_offer_territory_keys(offer: Dict[str, Any]) -> Set[str]:
    """Extrait toutes les clés territoriales d'une offre.

    Retourne un ensemble de clés normalisées pour le filtrage :
    - nom de commune
    - code postal
    - code département
    - territoire brut

    Args:
        offer: Dictionnaire de l'offre.

    Returns:
        Ensemble de clés territoriales normalisées.
    """
    keys: Set[str] = set()

    territoire = offer.get("territoire")
    if territoire:
        norm = normalize_territory(str(territoire))
        if norm:
            keys.add(norm)
        code = extract_territory_code(str(territoire))
        if code:
            keys.add(code)

    ville = offer.get("ville")
    if ville:
        norm = normalize_territory(str(ville))
        if norm:
            keys.add(norm)

    code_postal = offer.get("code_postal")
    if code_postal:
        keys.add(str(code_postal).strip())

    lieu_travail = offer.get("lieuTravail")
    if isinstance(lieu_travail, dict):
        for field in ("libelle", "commune", "codePostal"):
            value = lieu_travail.get(field)
            if value:
                norm = normalize_territory(str(value))
                if norm:
                    keys.add(norm)
                code = extract_territory_code(str(value))
                if code:
                    keys.add(code)

    lieux = offer.get("lieux")
    if isinstance(lieux, list):
        for lieu in lieux:
            if lieu:
                norm = normalize_territory(str(lieu))
                if norm:
                    keys.add(norm)

    return keys


def offer_matches_territory(offer: Dict[str, Any], territory: Optional[str]) -> bool:
    """Vérifie si une offre correspond à un territoire.

    Args:
        offer: Dictionnaire de l'offre.
        territory: Territoire recherché (normalisé ou brut).

    Returns:
        True si l'offre correspond au territoire.
    """
    if not territory:
        return True

    territory_norm = normalize_territory(territory)
    if not territory_norm:
        return True

    territory_code = extract_territory_code(territory)

    offer_keys = extract_offer_territory_keys(offer)

    if territory_norm in offer_keys:
        return True

    if territory_code and territory_code in offer_keys:
        return True

    for key in offer_keys:
        if territory_norm in key or key in territory_norm:
            if len(key) >= 3 and len(territory_norm) >= 3:
                return True

    return False


def filter_offers_by_territory(
    offers: Iterable[Dict[str, Any]],
    territory: Optional[str],
) -> List[Dict[str, Any]]:
    """Filtre les offres par territoire.

    Args:
        offers: Iterable d'offres.
        territory: Territoire à filtrer.

    Returns:
        Liste des offres correspondant au territoire.
    """
    if not territory:
        return list(offers)

    return [offer for offer in offers if offer_matches_territory(offer, territory)]


def find_territory_key_in_data(
    territory: str,
    available_keys: Iterable[str],
) -> Optional[str]:
    """Trouve la clé correspondante dans les données précalculées.

    Args:
        territory: Territoire recherché.
        available_keys: Clés disponibles dans les données.

    Returns:
        Clé correspondante ou None.
    """
    territory_norm = normalize_territory(territory)
    if not territory_norm:
        return None

    territory_code = extract_territory_code(territory)

    for key in available_keys:
        if key == territory:
            return key

    for key in available_keys:
        key_norm = normalize_territory(key)
        if key_norm == territory_norm:
            return key

    if territory_code:
        for key in available_keys:
            key_code = extract_territory_code(key)
            if key_code == territory_code:
                if territory_norm and territory_norm in normalize_territory(key):
                    return key

    for key in available_keys:
        key_norm = normalize_territory(key)
        if territory_norm in key_norm or key_norm in territory_norm:
            if len(key_norm) >= 3 and len(territory_norm) >= 3:
                return key

    return None


def is_territory_debug_mode() -> bool:
    """Indique si le mode debug territorial est activé.

    Returns:
        True si TREND_RADAR_TERRITORY_DEBUG=1.
    """
    return os.environ.get("TREND_RADAR_TERRITORY_DEBUG", "") == "1"
