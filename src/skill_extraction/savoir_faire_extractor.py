# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Extraction des savoir-faire depuis les phrases verbales.

Niveau 2.5 du pipeline hybride. Ce module détecte les phrases construites
autour de verbes d'action et les transforme en compétences nominales
normalisées.

Exemples de transformations :

- « concevoir et gérer un projet » → « Gestion de projet »
- « analyser et structurer des données » → « Analyse de données »
- « rédiger un cahier des charges » → « Rédaction de cahier des charges »
- « déployer des modèles en production » → « Déploiement de modèles »
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_VERBE_ACTION_PATTERNS: Dict[str, List[Tuple[str, str]]] = {
    "concevoir": [
        (r"concevoi?r\s+(?:et\s+)?g[ée]rer?\s+(?:un\s+)?projet", "Gestion de projet"),
        (r"concevoi?r\s+(?:une\s+)?application", "Conception d'applications"),
        (r"concevoi?r\s+(?:des\s+)?syst[èe]mes", "Conception de systèmes"),
        (r"concevoi?r\s+(?:une\s+)?architecture", "Architecture logiciel"),
        (r"concevoi?r\s+(?:des\s+)?solutions?", "Conception de solutions"),
        (r"concevoi?r\s+(?:l'|une\s+)?ing[ée]nierie\s+de\s+formation", "Ingénierie de formation"),
    ],
    "analyser": [
        (r"analyser\s*(?:,\s*exploiter)?\s*(?:et\s+)?(?:structurer)?\s*(?:les?\s+)?donn[ée]es", "Analyse de données"),
        (r"analyser\s+(?:les?\s+)?besoins", "Analyse des besoins"),
        (r"analyser\s+(?:les?\s+)?exigences", "Analyse des exigences"),
        (r"analyser\s+(?:le\s+)?march[ée]", "Analyse de marché"),
        (r"analyser\s+(?:les?\s+)?performances", "Analyse de performance"),
        (r"analyser\s+(?:les?\s+)?risques", "Analyse de risques"),
    ],
    "d[ée]velopper": [
        (r"d[ée]velopper\s+(?:des\s+)?applications?\s+web", "Développement web"),
        (r"d[ée]velopper\s+(?:des\s+)?applications?\s+mobiles", "Développement mobile"),
        (r"d[ée]velopper\s+(?:des\s+)?logiciels", "Développement logiciel"),
        (r"d[ée]velopper\s+(?:des\s+)?algorithmes", "Conception d'algorithmes"),
        (r"d[ée]velopper\s+(?:des\s+)?mod[èe]les", "Développement de modèles"),
    ],
    "g[ée]rer": [
        (r"g[ée]rer\s+(?:un\s+)?projet", "Gestion de projet"),
        (r"g[ée]rer\s+(?:une\s+)?[ée]quipe", "Management d'équipe"),
        (r"g[ée]rer\s+(?:une\s+)?base\s+de\s+donn[ée]es", "Gestion de bases de données"),
        (r"g[ée]rer\s+(?:des\s+)?bases\s+de\s+donn[ée]es", "Gestion de bases de données"),
        (r"g[ée]rer\s+(?:des\s+)?infrastructures", "Gestion d'infrastructure"),
        (r"g[ée]rer\s+(?:des\s+)?serveurs", "Administration serveur"),
        (r"g[ée]rer\s+(?:un\s+)?budget", "Gestion budgétaire"),
    ],
    "administrer": [
        (r"administrer\s+(?:des\s+)?bases\s+de\s+donn[ée]es", "Administration de bases de données"),
        (r"administrer\s+(?:des\s+)?syst[èe]mes", "Administration système"),
        (r"administrer\s+(?:des\s+)?r[ée]seaux", "Administration réseau"),
        (r"administrer\s+(?:des\s+)?serveurs", "Administration serveur"),
    ],
    "piloter": [
        (r"piloter\s+(?:un\s+)?projet", "Pilotage de projet"),
        (r"piloter\s+(?:une\s+)?[ée]quipe", "Pilotage d'équipe"),
        (r"piloter\s+(?:des\s+)?activit[ée]s", "Pilotage d'activités"),
        (r"piloter\s+(?:la\s+)?performance", "Pilotage de la performance"),
    ],
    "maintenir": [
        (r"maintenir\s+(?:des\s+)?applications?", "Maintenance applicative"),
        (r"maintenir\s+(?:des\s+)?syst[èe]mes", "Maintenance système"),
        (r"maintenir\s+(?:des\s+)?[ée]quipements", "Maintenance équipement"),
        (r"maintenir\s+en\s+condition\s+op[ée]rationnelle", "MCO"),
    ],
    "d[ée]ployer": [
        (r"d[ée]ployer\s+(?:des\s+)?mod[èe]les", "Déploiement de modèles"),
        (r"d[ée]ployer\s+(?:des\s+)?applications?", "Déploiement d'applications"),
        (r"d[ée]ployer\s+(?:des\s+)?solutions?", "Déploiement de solutions"),
        (r"d[ée]ployer\s+(?:en\s+)?production", "Mise en production"),
    ],
    "superviser": [
        (r"superviser\s+(?:des\s+)?travaux", "Supervision de travaux"),
        (r"superviser\s+(?:une\s+)?[ée]quipe", "Supervision d'équipe"),
        (r"superviser\s+(?:des\s+)?op[ée]rations", "Supervision d'opérations"),
    ],
    "r[ée]diger": [
        (r"r[ée]diger\s+(?:un\s+)?cahier\s+des\s+charges", "Rédaction de cahier des charges"),
        (r"r[ée]diger\s+(?:des\s+)?sp[ée]cifications", "Rédaction de spécifications"),
        (r"r[ée]diger\s+(?:des\s+)?documents?\s+techniques", "Rédaction technique"),
        (r"r[ée]diger\s+(?:des\s+)?rapports?", "Rédaction de rapports"),
    ],
    "former": [
        (r"former\s+(?:des\s+)?personnes", "Formation"),
        (r"former\s+(?:aux\s+)?outils", "Formation outils"),
        (r"former\s+(?:aux\s+)?technologies", "Formation technologique"),
    ],
    "coordonner": [
        (r"coordonner\s+(?:un\s+)?projet", "Coordination de projet"),
        (r"coordonner\s+(?:des\s+)?activit[ée]s", "Coordination d'activités"),
        (r"coordonner\s+(?:une\s+)?[ée]quipe", "Coordination d'équipe"),
    ],
    "mettre_place": [
        (r"mettre\s+(?:en\s+)?place\s+(?:une\s+)?strat[ée]gie", "Définition de stratégie"),
        (r"mettre\s+(?:en\s+)?place\s+(?:des\s+)?processus", "Mise en place de processus"),
        (r"mettre\s+(?:en\s+)?place\s+(?:une\s+)?architecture", "Architecture"),
        (r"mettre\s+(?:en\s+)?place\s+(?:des\s+)?indicateurs", "Définition d'indicateurs"),
    ],
    "surveiller": [
        (r"surveiller\s+(?:les\s+)?performances", "Monitoring de performance"),
        (r"surveiller\s+(?:la\s+)?d[ée]rive\s+(?:des\s+)?mod[èe]les", "Monitoring de modèles"),
        (r"surveiller\s+(?:les\s+)?syst[èe]mes", "Monitoring système"),
    ],
    "optimiser": [
        (r"optimiser\s+(?:les\s+)?performances", "Optimisation de performance"),
        (r"optimiser\s+(?:les\s+)?processus", "Optimisation de processus"),
        (r"optimiser\s+(?:les\s+)?co[ûu]ts", "Optimisation des coûts"),
    ],
    "automatiser": [
        (r"automatiser\s+(?:les\s+)?processus", "Automatisation de processus"),
        (r"automatiser\s+(?:les\s+)?tests", "Automatisation des tests"),
        (r"automatiser\s+(?:les\s+)?d[ée]ploiements", "Automatisation des déploiements"),
    ],
    "tester": [
        (r"tester\s+(?:des\s+)?applications?", "Tests applicatifs"),
        (r"tester\s+(?:des\s+)?logiciels", "Tests logiciels"),
    ],
    "int[ée]grer": [
        (r"int[ée]grer\s+(?:des\s+)?syst[èe]mes", "Intégration de systèmes"),
        (r"int[ée]grer\s+(?:des\s+)?apis?", "Intégration d'API"),
        (r"int[ée]grer\s+(?:en\s+)?continu", "Intégration continue"),
    ],
}

_NEGATION_MARKERS = (
    "aucune connaissance de",
    "aucune expérience en",
    "pas de connaissance en",
    "pas d'expérience en",
    "non requis",
    "non requise",
    "non nécessaire",
    "pas nécessaire",
    "inutile de",
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-Œ])|(?<=\n)\s*")


def _is_negated(sentence: str, match_start: int) -> bool:
    """Vérifie si la phrase contient un marqueur de négation."""

    prefix = sentence[max(0, match_start - 50):match_start].lower()
    return any(marker in prefix for marker in _NEGATION_MARKERS)


def _extract_sentences(text: str) -> List[Tuple[str, int]]:
    """Segmente un texte en phrases avec leurs positions."""

    sentences: List[Tuple[str, int]] = []
    pos = 0
    for raw in _SENTENCE_SPLIT.split(text):
        cleaned = raw.strip()
        if cleaned and len(cleaned) >= 10:
            sentences.append((cleaned, pos))
        pos += len(raw) + 1
    return sentences


def extract_savoir_faire(text: str) -> List[Tuple[str, str, str]]:
    """Extrait les savoir-faire depuis les phrases verbales.

    Parcourt le texte à la recherche de phrases construites autour de
    verbes d'action et les transforme en compétences nominales.

    Args:
        text: Texte brut de l'offre d'emploi.

    Returns:
        Liste de tuples ``(compétence_nominale, texte_brut, phrase_source)``.

    Example:
        >>> text = "Vous serez chargé de concevoir et gérer un projet."
        >>> results = extract_savoir_faire(text)
        >>> results[0][0]
        'Gestion de projet'
    """

    if not text:
        return []

    results: List[Tuple[str, str, str]] = []
    seen: set = set()

    sentences = _extract_sentences(text)

    for sentence, _ in sentences:
        sentence_lower = sentence.lower()

        for verb_key, patterns in _VERBE_ACTION_PATTERNS.items():
            for pattern, canonical_skill in patterns:
                for match in re.finditer(pattern, sentence_lower, re.IGNORECASE):
                    if _is_negated(sentence, match.start()):
                        continue

                    matched_text = sentence[match.start():match.end()]
                    key = canonical_skill.lower()

                    if key not in seen:
                        seen.add(key)
                        results.append((canonical_skill, matched_text, sentence))

    return results


def extract_savoir_faire_as_dicts(text: str) -> List[Dict[str, str]]:
    """Extrait les savoir-faire et retourne une liste de dictionnaires.

    Args:
        text: Texte brut de l'offre.

    Returns:
        Liste de dictionnaires avec les clés ``canonical_name``,
        ``raw_text`` et ``source_sentence``.
    """

    return [
        {
            "canonical_name": canonical,
            "raw_text": raw,
            "source_sentence": sentence,
        }
        for canonical, raw, sentence in extract_savoir_faire(text)
    ]
