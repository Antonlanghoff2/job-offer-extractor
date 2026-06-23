# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Instrumentation de performance pour les routes Flask.

Ce module fournit un décorateur et des utilitaires de mesure pour
journaliser les durées d'exécution des routes et des traitements lourds.
Activé par la variable d'environnement TREND_RADAR_PERF_DEBUG=1.
"""

from __future__ import annotations

import functools
import logging
import os
import time
from contextlib import contextmanager
from typing import Any, Dict, Generator, Optional

logger = logging.getLogger(__name__)

_PERF_DEBUG = os.environ.get("TREND_RADAR_PERF_DEBUG", "").strip() in ("1", "true", "yes")


def is_perf_debug() -> bool:
    """Indique si le mode debug performance est actif."""
    return _PERF_DEBUG


class RouteTimer:
    """Chronomètre pour une route Flask.

    Attributes:
        route_name: Nom de la route.
        segments: Durées intermédiaires nommées.
        counters: Compteurs divers (offres, profils, etc.).
    """

    def __init__(self, route_name: str):
        self.route_name = route_name
        self._start = time.monotonic()
        self.segments: Dict[str, float] = {}
        self.counters: Dict[str, int] = {}
        self._segment_start: Optional[float] = None
        self._segment_name: Optional[str] = None

    def start_segment(self, name: str) -> None:
        """Démarre un segment chronométré."""
        if not _PERF_DEBUG:
            return
        self._end_segment()
        self._segment_name = name
        self._segment_start = time.monotonic()

    def end_segment(self, name: Optional[str] = None) -> None:
        """Termine le segment courant."""
        if not _PERF_DEBUG:
            return
        self._end_segment()

    def _end_segment(self) -> None:
        if self._segment_start is not None and self._segment_name is not None:
            elapsed = time.monotonic() - self._segment_start
            self.segments[self._segment_name] = round(elapsed, 4)
            self._segment_start = None
            self._segment_name = None

    def count(self, key: str, value: int = 1) -> None:
        """Ajoute un compteur."""
        if not _PERF_DEBUG:
            return
        self.counters[key] = self.counters.get(key, 0) + value

    def log(self) -> None:
        """Journalise les mesures."""
        if not _PERF_DEBUG:
            return
        self._end_segment()
        total = round(time.monotonic() - self._start, 4)
        parts = [f"Route {self.route_name}", f"total={total}s"]
        for seg_name, seg_dur in self.segments.items():
            parts.append(f"{seg_name}={seg_dur}s")
        for cnt_name, cnt_val in self.counters.items():
            parts.append(f"{cnt_name}={cnt_val}")
        logger.info(" | ".join(parts))


@contextmanager
def timed_segment(timer: RouteTimer, name: str) -> Generator[None, None, None]:
    """Contexte pour mesurer un segment."""
    timer.start_segment(name)
    try:
        yield
    finally:
        timer.end_segment(name)


def timed_route(route_name: str):
    """Décorateur pour mesurer automatiquement une route Flask.

    Args:
        route_name: Nom de la route pour les logs.

    Returns:
        Décorateur.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not _PERF_DEBUG:
                return func(*args, **kwargs)
            timer = RouteTimer(route_name)
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                timer.log()
        return wrapper
    return decorator


def measure_call(label: str, func, *args, **kwargs) -> Any:
    """Mesure la durée d'un appel de fonction.

    Args:
        label: Libellé pour le log.
        func: Fonction à appeler.
        *args: Arguments positionnels.
        **kwargs: Arguments nommés.

    Returns:
        Résultat de la fonction.
    """
    if not _PERF_DEBUG:
        return func(*args, **kwargs)
    start = time.monotonic()
    try:
        return func(*args, **kwargs)
    finally:
        elapsed = round(time.monotonic() - start, 4)
        logger.info("Perf: %s = %ss", label, elapsed)
