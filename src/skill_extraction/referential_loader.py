# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Chargement robuste des référentiels JSON de compétences.

Ce module isole la résolution des chemins et la validation des fichiers
``data/referentials/*.json`` utilisés par les extracteurs de compétences.
Il évite de dépendre du répertoire courant et met les résultats en cache
par processus pour limiter les accès disque répétés pendant les tests et
en production.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REFERENTIAL_DIR = PROJECT_ROOT / "data" / "referentials"


@dataclass(frozen=True)
class ReferentialLoadResult:
    """Résultat du chargement d'un référentiel JSON.

    Le résultat encapsule le statut de chargement, le chemin résolu et
    les entrées validées. Les entrées sont figées dans une structure de
    lecture seule afin d'éviter les mutations accidentelles entre appels.

    Attributes:
        path: Chemin résolu du fichier JSON, même s'il n'existe pas.
        entries: Entrées validées et figées issues du fichier.
        status: Statut du chargement, par exemple ``ok`` ou ``error``.
        reason: Code métier lisible décrivant l'échec éventuel.
        message: Message technique détaillé, destiné aux journaux.
    """

    path: Path
    entries: Tuple[Mapping[str, Any], ...]
    status: str
    reason: Optional[str]
    message: Optional[str]

    @property
    def ok(self) -> bool:
        """Indique si le référentiel a été chargé correctement."""

        return self.status == "ok"


def _freeze_entry(entry: Dict[str, Any]) -> Mapping[str, Any]:
    """Transforme une entrée JSON en mapping de lecture seule."""

    frozen: Dict[str, Any] = {}
    for key, value in entry.items():
        if isinstance(value, list):
            frozen[key] = tuple(value)
        else:
            frozen[key] = value
    return MappingProxyType(frozen)


def _validate_entry(
    entry: Any,
    *,
    index: int,
    required_string_fields: Sequence[str],
    required_list_fields: Sequence[str],
    optional_string_fields: Sequence[str] = (),
    optional_list_fields: Sequence[str] = (),
) -> Dict[str, Any]:
    """Valide une entrée du référentiel.

    Args:
        entry: Entrée brute issue du JSON.
        index: Position de l'entrée dans le fichier.
        required_string_fields: Champs texte obligatoires.
        required_list_fields: Champs listes obligatoires.
        optional_string_fields: Champs texte acceptés mais non obligatoires.
        optional_list_fields: Champs listes acceptés mais non obligatoires.

    Returns:
        Entrée validée et normalisée sous forme de dictionnaire.

    Raises:
        ValueError: Si la structure du référentiel est invalide.
    """

    if not isinstance(entry, dict):
        raise ValueError(f"Entrée {index}: chaque élément doit être un objet JSON.")

    normalized: Dict[str, Any] = {}

    for field_name in required_string_fields:
        value = entry.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"Entrée {index}: le champ '{field_name}' doit être une chaîne non vide."
            )
        normalized[field_name] = value.strip()

    for field_name in required_list_fields:
        value = entry.get(field_name)
        if not isinstance(value, list):
            raise ValueError(
                f"Entrée {index}: le champ '{field_name}' doit être une liste JSON."
            )
        cleaned_values = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError(
                    f"Entrée {index}: le champ '{field_name}' doit contenir uniquement des chaînes non vides."
                )
            cleaned_values.append(item.strip())
        normalized[field_name] = cleaned_values

    for field_name in optional_string_fields:
        value = entry.get(field_name)
        if value is None:
            continue
        if not isinstance(value, str):
            raise ValueError(
                f"Entrée {index}: le champ optionnel '{field_name}' doit être une chaîne."
            )
        normalized[field_name] = value.strip()

    for field_name in optional_list_fields:
        value = entry.get(field_name)
        if value is None:
            normalized[field_name] = []
            continue
        if not isinstance(value, list):
            raise ValueError(
                f"Entrée {index}: le champ optionnel '{field_name}' doit être une liste JSON."
            )
        cleaned_values = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError(
                    f"Entrée {index}: le champ optionnel '{field_name}' doit contenir uniquement des chaînes non vides."
                )
            cleaned_values.append(item.strip())
        normalized[field_name] = cleaned_values

    for key, value in entry.items():
        if key not in normalized:
            normalized[key] = value

    return normalized


@lru_cache(maxsize=None)
def resolve_referential_path(filename: str) -> Path:
    """Résout le chemin d'un référentiel à partir du module courant.

    Le premier chemin trouvé en remontant l'arborescence du module est
    retenu. Cette stratégie fonctionne depuis la racine du projet, un
    worker Gunicorn, systemd ou un répertoire de travail arbitraire.

    Args:
        filename: Nom du fichier JSON à résoudre.

    Returns:
        Chemin candidat vers le fichier référentiel.

    Raises:
        None: La fonction retourne toujours un chemin candidat.
    """

    module_path = Path(__file__).resolve()
    for parent in module_path.parents:
        candidate = parent / "data" / "referentials" / filename
        if candidate.exists():
            return candidate

    return REFERENTIAL_DIR / filename


@lru_cache(maxsize=None)
def _load_referential_cached(
    path_str: str,
    referential_name: str,
    required_string_fields: Tuple[str, ...],
    required_list_fields: Tuple[str, ...],
    optional_string_fields: Tuple[str, ...],
    optional_list_fields: Tuple[str, ...],
) -> ReferentialLoadResult:
    """Charge et valide un référentiel JSON avec cache de processus."""

    path = Path(path_str)
    if not path.exists():
        message = f"Référentiel {referential_name} introuvable: {path}"
        logger.warning(message)
        return ReferentialLoadResult(
            path=path,
            entries=tuple(),
            status="error",
            reason=f"{referential_name}_missing",
            message=message,
        )

    try:
        raw_content = path.read_text(encoding="utf-8")
    except OSError as exc:
        message = f"Impossible de lire le référentiel {referential_name}: {exc}"
        logger.error(message)
        return ReferentialLoadResult(
            path=path,
            entries=tuple(),
            status="error",
            reason=f"{referential_name}_unreadable",
            message=message,
        )

    try:
        data = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        message = f"JSON invalide dans le référentiel {referential_name}: {exc}"
        logger.error(message)
        return ReferentialLoadResult(
            path=path,
            entries=tuple(),
            status="error",
            reason=f"{referential_name}_invalid_json",
            message=message,
        )

    if not isinstance(data, list):
        message = f"Le référentiel {referential_name} doit contenir une liste JSON."
        logger.error(message)
        return ReferentialLoadResult(
            path=path,
            entries=tuple(),
            status="error",
            reason=f"{referential_name}_invalid_schema",
            message=message,
        )

    try:
        normalized_entries = [
            _validate_entry(
                entry,
                index=index,
                required_string_fields=required_string_fields,
                required_list_fields=required_list_fields,
                optional_string_fields=optional_string_fields,
                optional_list_fields=optional_list_fields,
            )
            for index, entry in enumerate(data)
        ]
    except ValueError as exc:
        message = f"Schéma invalide pour le référentiel {referential_name}: {exc}"
        logger.error(message)
        return ReferentialLoadResult(
            path=path,
            entries=tuple(),
            status="error",
            reason=f"{referential_name}_invalid_schema",
            message=message,
        )

    frozen_entries = tuple(_freeze_entry(entry) for entry in normalized_entries)
    logger.debug(
        "Référentiel %s chargé: %d entrées depuis %s",
        referential_name,
        len(frozen_entries),
        path,
    )
    return ReferentialLoadResult(
        path=path,
        entries=frozen_entries,
        status="ok",
        reason=None,
        message=None,
    )


def load_referential(
    filename: str,
    *,
    referential_name: str,
    required_string_fields: Sequence[str],
    required_list_fields: Sequence[str],
    optional_string_fields: Sequence[str] = (),
    optional_list_fields: Sequence[str] = (),
    path: Optional[Path] = None,
) -> ReferentialLoadResult:
    """Charge un référentiel JSON validé et mis en cache.

    Args:
        filename: Nom du fichier référentiel à résoudre si aucun chemin
            explicite n'est fourni.
        referential_name: Nom métier utilisé pour les messages et codes
            d'erreur.
        required_string_fields: Champs texte obligatoires pour chaque
            entrée.
        required_list_fields: Champs liste obligatoires pour chaque
            entrée.
        optional_string_fields: Champs texte autorisés mais facultatifs.
        optional_list_fields: Champs liste autorisés mais facultatifs.
        path: Chemin explicite à utiliser au lieu de la résolution par
            défaut.

    Returns:
        Résultat de chargement contenant les entrées validées.

    Raises:
        ValueError: Si ``filename`` ou ``referential_name`` est vide.
    """

    if not filename.strip():
        raise ValueError("Le nom du fichier référentiel ne peut pas être vide.")
    if not referential_name.strip():
        raise ValueError("Le nom métier du référentiel ne peut pas être vide.")

    resolved_path = Path(path).expanduser().resolve() if path is not None else resolve_referential_path(filename)
    return _load_referential_cached(
        str(resolved_path),
        referential_name,
        tuple(required_string_fields),
        tuple(required_list_fields),
        tuple(optional_string_fields),
        tuple(optional_list_fields),
    )


def clear_referential_cache() -> None:
    """Vide le cache des référentiels chargés.

    Cette fonction est utile pour les tests et les opérations
    d'administration qui doivent forcer la relecture des fichiers JSON.
    """

    resolve_referential_path.cache_clear()
    _load_referential_cached.cache_clear()

