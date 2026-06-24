# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""ViewModel centralisé pour l'affichage des offres.

Ce module fournit une structure unique ``OfferViewModel`` utilisée par
toutes les pages affichant des offres (Mes offres, Tableau de bord,
détail d'offre). Il garantit que les champs sont toujours présents,
que le titre est résolu avec un ordre de priorité explicite, et que
les sous-scores sont normalisés vers un schéma canonique.

Le module gère également la compatibilité avec les anciens formats
de données (offres normalisées, matchings précalculés, cache).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

CACHE_SCHEMA_VERSION = 2

_CANONICAL_CRITERION_KEYS = (
    "skills",
    "job",
    "experience",
    "diploma",
    "location",
    "contract",
    "remote",
    "salary",
)

_LEGACY_TO_CANONICAL = {
    "competences": "skills",
    "metier": "job",
    "experience": "experience",
    "diplome": "diploma",
    "localisation": "location",
    "contrat": "contract",
    "teletravail": "remote",
    "distanciel": "remote",
    "salaire": "salary",
}

_CRITERION_LABELS = {
    "skills": "Compétences",
    "job": "Métier",
    "experience": "Expérience",
    "diploma": "Diplôme",
    "location": "Localisation",
    "contract": "Contrat",
    "remote": "Télétravail",
    "salary": "Salaire",
}

_TITLE_FALLBACK_KEYS = (
    "title",
    "titre",
    "intitule_poste",
    "intitule",
    "libelle",
    "metier",
    "job_title",
    "offer_title",
)

_INVALID_TITLE_VALUES = {"", "null", "none", "n/a", "-"}


def _is_blank_title(value: object) -> bool:
    """Vérifie si une valeur de titre est vide ou invalide.

    Args:
        value: Valeur à tester.

    Returns:
        True si la valeur est None, vide, ou un marqueur invalide.
    """
    if value is None:
        return True
    text = str(value).strip()
    if not text:
        return True
    if text.lower() in _INVALID_TITLE_VALUES:
        return True
    return False


def resolve_offer_title(offer: Dict[str, Any]) -> str:
    """Résout le titre d'une offre avec un ordre de priorité explicite.

    L'ordre de priorité est :
    1. title
    2. intitule_poste
    3. intitule
    4. libelle
    5. metier
    6. job_title
    7. offer_title
    8. Données brutes France Travail (romeLibelle, appellationlibelle)
    9. Fallback « Intitulé non renseigné »

    Args:
        offer: Dictionnaire représentant l'offre (normalisée ou brute).

    Returns:
        Titre résolu, jamais vide.
    """
    if not isinstance(offer, dict):
        return "Intitulé non renseigné"

    for key in _TITLE_FALLBACK_KEYS:
        value = offer.get(key)
        if not _is_blank_title(value):
            return str(value).strip()

    rome = offer.get("romeLibelle")
    if not _is_blank_title(rome):
        return str(rome).strip()

    appellation = offer.get("appellationlibelle")
    if not _is_blank_title(appellation):
        return str(appellation).strip()

    lieu_travail = offer.get("lieuTravail")
    if isinstance(lieu_travail, dict):
        libelle = lieu_travail.get("libelle")
        if not _is_blank_title(libelle):
            candidate = str(libelle).strip()
            if candidate.lower() not in _INVALID_TITLE_VALUES:
                return candidate

    return "Intitulé non renseigné"


def resolve_offer_location(offer: Dict[str, Any]) -> str:
    """Résout la localisation d'une offre.

    Args:
        offer: Dictionnaire représentant l'offre.

    Returns:
        Localisation résolue ou « Lieu non renseigné ».
    """
    if not isinstance(offer, dict):
        return "Lieu non renseigné"

    lieux = offer.get("lieux")
    if isinstance(lieux, list) and lieux:
        parts = [str(item).strip() for item in lieux if str(item).strip()]
        if parts:
            return ", ".join(parts)
    if isinstance(lieux, str) and lieux.strip():
        return lieux.strip()

    for key in ("ville", "territoire", "localisation", "location", "lieu"):
        value = offer.get(key)
        if value and str(value).strip():
            return str(value).strip()

    lieu_travail = offer.get("lieuTravail")
    if isinstance(lieu_travail, dict):
        for key in ("libelle", "commune", "codePostal"):
            value = lieu_travail.get(key)
            if value and str(value).strip():
                return str(value).strip()

    code_postal = offer.get("code_postal")
    if code_postal and str(code_postal).strip():
        return str(code_postal).strip()

    return "Lieu non renseigné"


def resolve_offer_url(offer: Dict[str, Any], offer_identifier: Optional[str] = None) -> Optional[str]:
    """Résout l'URL d'une offre.

    Args:
        offer: Dictionnaire représentant l'offre.
        offer_identifier: Identifiant de l'offre en secours.

    Returns:
        URL ou None.
    """
    if not isinstance(offer, dict):
        return None

    for key in ("url_originale", "urlOrigine", "url", "origineOffre"):
        value = offer.get(key)
        if isinstance(value, dict):
            value = value.get("urlOrigine") or value.get("url")
        if value and str(value).strip():
            return str(value).strip()

    origine = offer.get("origineOffre")
    if isinstance(origine, dict):
        url = origine.get("urlOrigine") or origine.get("url")
        if url and str(url).strip():
            return str(url).strip()

    return None


def _normalize_criterion_key(key: str) -> str:
    """Convertit une clé de critère ancienne ou canonique en clé canonique.

    Args:
        key: Clé de critère (ancienne ou canonique).

    Returns:
        Clé canonique.
    """
    if key in _CANONICAL_CRITERION_KEYS:
        return key
    return _LEGACY_TO_CANONICAL.get(key, key)


def _empty_criterion(label: str) -> Dict[str, Any]:
    """Retourne un dictionnaire de critère non évalué.

    Args:
        label: Libellé du critère.

    Returns:
        Dictionnaire de critère avec score=None et evaluated=False.
    """
    return {
        "label": label,
        "score": None,
        "evaluated": False,
        "reason": "champ_absent",
        "matched_values": [],
        "missing_values": [],
    }


def normalize_criterion_scores(
    match_result: Optional[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Normalise les sous-scores vers le schéma canonique.

    Gère les anciens formats :
    - ``sous_scores`` (build_scoring_result)
    - ``criterion_scores`` (0-1 scale)
    - ``explanation.subscores`` (0-100 scale)
    - ``{key}_score`` fields (skill_score, job_score...)

    Args:
        match_result: Résultat de matching complet.

    Returns:
        Dictionnaire {clé_canonique: {label, score, evaluated, reason, ...}}.
    """
    result: Dict[str, Dict[str, Any]] = {}
    for key in _CANONICAL_CRITERION_KEYS:
        result[key] = _empty_criterion(_CRITERION_LABELS.get(key, key))

    if not match_result or not isinstance(match_result, dict):
        return result

    sous_scores_raw = match_result.get("sous_scores") or {}
    criterion_scores_raw = match_result.get("criterion_scores") or {}
    criterion_details = match_result.get("criterion_details") or {}
    explanation = match_result.get("explanation") or {}
    explanation_subscores = explanation.get("subscores") or {}

    for legacy_key, data in sous_scores_raw.items():
        canonical = _normalize_criterion_key(legacy_key)
        if canonical not in _CANONICAL_CRITERION_KEYS:
            continue
        if not isinstance(data, dict):
            continue

        score_value = data.get("score")
        statut = data.get("statut", "")
        details = data.get("details") or {}

        if statut == "champ_absent" or score_value is None:
            result[canonical] = {
                "label": _CRITERION_LABELS.get(canonical, canonical),
                "score": None,
                "evaluated": False,
                "reason": details.get("reason") or "champ_absent",
                "matched_values": details.get("matching_skills") or details.get("matching_diplomas") or details.get("matched_tokens") or [],
                "missing_values": details.get("missing_skills") or details.get("missing_diplomas") or [],
            }
        else:
            try:
                score_float = float(score_value)
            except (TypeError, ValueError):
                score_float = None
            result[canonical] = {
                "label": _CRITERION_LABELS.get(canonical, canonical),
                "score": score_float,
                "evaluated": True,
                "reason": details.get("reason") or "",
                "matched_values": details.get("matching_skills") or details.get("matching_diplomas") or details.get("matched_tokens") or [],
                "missing_values": details.get("missing_skills") or details.get("missing_diplomas") or [],
            }

    for legacy_key, score_value in criterion_scores_raw.items():
        canonical = _normalize_criterion_key(legacy_key)
        if canonical not in _CANONICAL_CRITERION_KEYS:
            continue
        if result[canonical]["evaluated"]:
            continue
        details = criterion_details.get(legacy_key) or criterion_details.get(canonical) or {}
        if score_value is None:
            result[canonical] = {
                "label": _CRITERION_LABELS.get(canonical, canonical),
                "score": None,
                "evaluated": False,
                "reason": details.get("reason") or "champ_absent",
                "matched_values": [],
                "missing_values": [],
            }
        else:
            try:
                score_100 = float(score_value) * 100.0
            except (TypeError, ValueError):
                score_100 = None
            if score_100 is not None:
                score_100 = round(max(0.0, min(100.0, score_100)), 2)
            result[canonical] = {
                "label": _CRITERION_LABELS.get(canonical, canonical),
                "score": score_100,
                "evaluated": True,
                "reason": details.get("reason") or "",
                "matched_values": [],
                "missing_values": [],
            }

    for legacy_key, score_value in explanation_subscores.items():
        canonical = _normalize_criterion_key(legacy_key)
        if canonical not in _CANONICAL_CRITERION_KEYS:
            continue
        if result[canonical]["evaluated"]:
            continue
        details = criterion_details.get(legacy_key) or {}
        if score_value is None:
            result[canonical] = {
                "label": _CRITERION_LABELS.get(canonical, canonical),
                "score": None,
                "evaluated": False,
                "reason": "champ_absent",
                "matched_values": [],
                "missing_values": [],
            }
        else:
            try:
                score_float = float(score_value)
            except (TypeError, ValueError):
                score_float = None
            result[canonical] = {
                "label": _CRITERION_LABELS.get(canonical, canonical),
                "score": score_float,
                "evaluated": True,
                "reason": details.get("reason") or "",
                "matched_values": [],
                "missing_values": [],
            }

    _score_field_map = {
        "skills": "skill_score",
        "job": "job_score",
        "experience": "experience_score",
        "diploma": "diploma_score",
        "location": "location_score",
        "contract": "contract_score",
        "remote": "remote_score",
        "salary": "salary_score",
    }
    for canonical, field_name in _score_field_map.items():
        if result[canonical]["evaluated"]:
            continue
        raw_value = match_result.get(field_name)
        if raw_value is None:
            continue
        try:
            score_float = float(raw_value)
        except (TypeError, ValueError):
            continue
        details = criterion_details.get(canonical) or {}
        result[canonical] = {
            "label": _CRITERION_LABELS.get(canonical, canonical),
            "score": round(score_float, 2),
            "evaluated": True,
            "reason": details.get("reason") or "",
            "matched_values": [],
            "missing_values": [],
        }

    return result


@dataclass
class OfferViewModel:
    """Représentation canonique d'une offre pour l'affichage.

    Cette structure est utilisée par toutes les pages affichant des offres.
    Elle garantit que les champs sont toujours présents et typés.

    Attributes:
        offer_id: Identifiant unique de l'offre.
        title: Titre résolu de l'offre (jamais vide).
        company: Nom de l'entreprise ou None.
        location: Localisation résolue.
        contract: Type de contrat ou None.
        salary_text: Texte du salaire ou None.
        remote_text: Texte du télétravail ou None.
        url: URL de l'offre ou None.
        source: Source de l'offre.
        global_score: Score global de matching (0-100) ou None.
        criterion_scores: Sous-scores normalisés par critère canonique.
        matched_skills: Compétences en commun.
        missing_skills: Compétences manquantes.
        updated_at: Date de dernière mise à jour ou None.
    """

    offer_id: str
    title: str
    company: Optional[str] = None
    location: Optional[str] = None
    contract: Optional[str] = None
    salary_text: Optional[str] = None
    remote_text: Optional[str] = None
    url: Optional[str] = None
    source: Optional[str] = None
    global_score: Optional[float] = None
    criterion_scores: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    matched_skills: List[str] = field(default_factory=list)
    missing_skills: List[str] = field(default_factory=list)
    updated_at: Optional[str] = None


def _resolve_salary_text(offer: Dict[str, Any]) -> Optional[str]:
    """Construit un texte lisible pour le salaire.

    Args:
        offer: Dictionnaire de l'offre.

    Returns:
        Texte du salaire ou None.
    """
    salary_min = offer.get("salaire_min")
    salary_max = offer.get("salaire_max")
    try:
        min_val = int(salary_min) if salary_min not in (None, "") else None
    except (TypeError, ValueError):
        min_val = None
    try:
        max_val = int(salary_max) if salary_max not in (None, "") else None
    except (TypeError, ValueError):
        max_val = None

    if min_val and max_val and min_val != max_val:
        return f"{min_val:,} – {max_val:,} €".replace(",", " ")
    if min_val:
        return f"À partir de {min_val:,} €".replace(",", " ")
    if max_val:
        return f"Jusqu'à {max_val:,} €".replace(",", " ")

    salaire_text = offer.get("salaire")
    if isinstance(salaire_text, str) and salaire_text.strip():
        return salaire_text.strip()
    if isinstance(salaire_text, dict):
        libelle = salaire_text.get("libelle")
        if libelle and str(libelle).strip():
            return str(libelle).strip()
    return None


def _resolve_remote_text(offer: Dict[str, Any]) -> Optional[str]:
    """Résout le texte du télétravail.

    Args:
        offer: Dictionnaire de l'offre.

    Returns:
        Texte du télétravail ou None.
    """
    teletravail = offer.get("teletravail")
    if not teletravail:
        return None
    text = str(teletravail).strip().lower()
    mapping = {
        "teletravail": "Télétravail complet",
        "hybride": "Télétravail hybride",
        "presentiel": "Présentiel",
    }
    return mapping.get(text, str(teletravail).strip())


def build_offer_view_model(
    offer: Dict[str, Any],
    match_result: Optional[Dict[str, Any]] = None,
    offer_identifier: Optional[str] = None,
) -> OfferViewModel:
    """Construit un OfferViewModel depuis une offre et un résultat de matching.

    Cette fonction est le point d'entrée unique pour transformer les données
    brutes en ViewModel prêt pour l'affichage.

    Args:
        offer: Dictionnaire de l'offre (normalisée, enrichie ou brute).
        match_result: Résultat de matching optionnel.
        offer_identifier: Identifiant de l'offre en secours.

    Returns:
        OfferViewModel prêt pour l'affichage.
    """
    if not isinstance(offer, dict):
        offer = {}

    oid = offer_identifier or str(offer.get("id") or offer.get("id_offre") or offer.get("source_identifier") or "")
    title = resolve_offer_title(offer)
    company = offer.get("entreprise") or offer.get("company") or offer.get("employer")
    if isinstance(company, dict):
        company = company.get("nom") or company.get("name") or None
    company_text = str(company).strip() if company else None
    if not company_text:
        company_text = None

    location = resolve_offer_location(offer)
    contract = offer.get("contrat") or offer.get("contract")
    contract_text = str(contract).strip() if contract else None
    salary_text = _resolve_salary_text(offer)
    remote_text = _resolve_remote_text(offer)
    url = resolve_offer_url(offer, oid)
    source = offer.get("source") or "France Travail"

    global_score = None
    criterion_scores: Dict[str, Dict[str, Any]] = {}
    matched_skills: List[str] = []
    missing_skills: List[str] = []

    if match_result and isinstance(match_result, dict):
        gs = match_result.get("global_score") or match_result.get("score_global")
        if gs is not None:
            try:
                global_score = round(float(gs), 2)
            except (TypeError, ValueError):
                global_score = None

        criterion_scores = normalize_criterion_scores(match_result)

        matched_skills = match_result.get("matching_skills") or match_result.get("competences_communes") or []
        missing_skills = match_result.get("missing_skills") or match_result.get("competences_manquantes") or []

        explanation = match_result.get("explanation") or {}
        if not matched_skills:
            matched_skills = explanation.get("matching_skills") or []
        if not missing_skills:
            missing_skills = explanation.get("missing_skills") or []

    return OfferViewModel(
        offer_id=oid,
        title=title,
        company=company_text,
        location=location if location != "Lieu non renseigné" else None,
        contract=contract_text,
        salary_text=salary_text,
        remote_text=remote_text,
        url=url,
        source=str(source) if source else None,
        global_score=global_score,
        criterion_scores=criterion_scores,
        matched_skills=list(matched_skills),
        missing_skills=list(missing_skills),
    )


def build_match_view_model(
    match: Dict[str, Any],
    offer: Optional[Dict[str, Any]] = None,
    offer_identifier: Optional[str] = None,
) -> OfferViewModel:
    """Construit un OfferViewModel depuis un match et son offre associée.

    Args:
        match: Résultat de matching (précalculé ou en direct).
        offer: Offre associée (optionnelle, extraite du match si absente).
        offer_identifier: Identifiant de l'offre en secours.

    Returns:
        OfferViewModel prêt pour l'affichage.
    """
    if not isinstance(match, dict):
        match = {}
    if offer is None:
        offer = match.get("offer") or {}
    if not isinstance(offer, dict):
        offer = {}

    oid = offer_identifier or str(match.get("offer_identifier") or match.get("offer_id") or offer.get("id") or offer.get("id_offre") or "")

    match_for_scores = dict(match)
    details = match.get("details") or {}
    if details and not match_for_scores.get("sous_scores"):
        for key in ("sous_scores", "criterion_scores", "criterion_details", "explanation"):
            if key in details and key not in match_for_scores:
                match_for_scores[key] = details[key]
    if details.get("global_score") and not match_for_scores.get("global_score"):
        match_for_scores["global_score"] = details["global_score"]
    if details.get("score_global") and not match_for_scores.get("global_score"):
        match_for_scores["global_score"] = details["score_global"]
    for field_name in ("skill_score", "job_score", "experience_score", "diploma_score",
                       "location_score", "contract_score", "remote_score", "salary_score"):
        if field_name in details and field_name not in match_for_scores:
            match_for_scores[field_name] = details[field_name]
    if details.get("matching_skills") and not match_for_scores.get("matching_skills"):
        match_for_scores["matching_skills"] = details["matching_skills"]
    if details.get("missing_skills") and not match_for_scores.get("missing_skills"):
        match_for_scores["missing_skills"] = details["missing_skills"]

    vm = build_offer_view_model(offer, match_for_scores, offer_identifier=oid)
    return vm


def is_debug_mode() -> bool:
    """Indique si le mode debug d'affichage est activé.

    Returns:
        True si la variable d'environnement TREND_RADAR_VIEW_DEBUG est à 1.
    """
    return os.environ.get("TREND_RADAR_VIEW_DEBUG", "") == "1"


def debug_offer_payload(
    raw_offer: Optional[Dict[str, Any]] = None,
    normalized_offer: Optional[Dict[str, Any]] = None,
    match_result: Optional[Dict[str, Any]] = None,
    view_model: Optional[OfferViewModel] = None,
) -> Dict[str, Any]:
    """Construit un payload de debug pour une offre.

    Args:
        raw_offer: Offre brute.
        normalized_offer: Offre normalisée.
        match_result: Résultat de matching.
        view_model: ViewModel final.

    Returns:
        Dictionnaire de debug.
    """
    payload: Dict[str, Any] = {}
    if raw_offer is not None:
        payload["raw_offer"] = raw_offer
    if normalized_offer is not None:
        payload["normalized_offer"] = normalized_offer
    if match_result is not None:
        safe_match = {}
        for key, value in match_result.items():
            if key == "offer" and isinstance(value, dict):
                safe_match[key] = {k: v for k, v in value.items() if k != "description"}
            else:
                safe_match[key] = value
        payload["match_result"] = safe_match
    if view_model is not None:
        from dataclasses import asdict
        payload["view_model"] = asdict(view_model)
    return payload
