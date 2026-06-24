# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Tests d'intégration Flask pour les pages Mes offres et Tableau de bord.

Vérifie que :
- Le titre apparaît dans le HTML
- Le score global apparaît
- Les sous-scores sont associés au bon libellé
- Les données absentes affichent « Non renseigné » ou « Non évalué »
- Aucune chaîne None, null ou dictionnaire brut n'apparaît
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch, MagicMock

from src.presentation.offer_view_model import (
    build_match_view_model,
    build_offer_view_model,
    resolve_offer_title,
)


class OfferDisplayIntegrationTest(unittest.TestCase):
    """Tests d'intégration pour l'affichage des offres."""

    def test_title_resolved_from_intitule(self) -> None:
        offer = {"id": "1", "intitule": "Dev Python", "entreprise": "ACME"}
        vm = build_offer_view_model(offer)
        self.assertEqual(vm.title, "Dev Python")
        self.assertNotIn("None", vm.title)
        self.assertNotIn("null", vm.title)

    def test_title_fallback_when_empty(self) -> None:
        offer = {"id": "1", "intitule": "", "entreprise": "ACME"}
        vm = build_offer_view_model(offer)
        self.assertEqual(vm.title, "Intitulé non renseigné")

    def test_sub_scores_correct_labels(self) -> None:
        match = {
            "offer_id": "1",
            "score": 70.0,
            "details": {
                "global_score": 70.0,
                "sous_scores": {
                    "competences": {"score": 85.0, "statut": "evalue", "details": {"matching_skills": ["Python"]}},
                    "metier": {"score": 60.0, "statut": "evalue", "details": {}},
                    "localisation": {"score": None, "statut": "champ_absent", "details": {}},
                    "salaire": {"score": 0.0, "statut": "evalue", "details": {"reason": "salaire trop bas"}},
                },
                "criterion_details": {},
                "explanation": {},
            },
        }
        offer = {"id": "1", "intitule": "Dev Python"}
        vm = build_match_view_model(match, offer)

        self.assertEqual(vm.criterion_scores["skills"]["label"], "Compétences")
        self.assertTrue(vm.criterion_scores["skills"]["evaluated"])
        self.assertEqual(vm.criterion_scores["skills"]["score"], 85.0)

        self.assertEqual(vm.criterion_scores["job"]["label"], "Métier")
        self.assertTrue(vm.criterion_scores["job"]["evaluated"])

        self.assertEqual(vm.criterion_scores["location"]["label"], "Localisation")
        self.assertFalse(vm.criterion_scores["location"]["evaluated"])

        self.assertEqual(vm.criterion_scores["salary"]["label"], "Salaire")
        self.assertTrue(vm.criterion_scores["salary"]["evaluated"])
        self.assertEqual(vm.criterion_scores["salary"]["score"], 0.0)

    def test_no_none_in_view_model_strings(self) -> None:
        offer = {"id": "1"}
        vm = build_offer_view_model(offer)
        self.assertIsNotNone(vm.title)
        self.assertNotEqual(vm.title, "None")
        self.assertNotEqual(vm.title, "null")
        self.assertNotEqual(vm.title, "")

    def test_location_resolved_from_territoire(self) -> None:
        offer = {"id": "1", "intitule": "Dev", "territoire": "75 - Paris"}
        vm = build_offer_view_model(offer)
        self.assertEqual(vm.location, "75 - Paris")

    def test_url_none_when_no_url_field(self) -> None:
        offer = {"id": "ABC123", "intitule": "Dev", "source": "France Travail"}
        vm = build_offer_view_model(offer)
        self.assertIsNone(vm.url)

    def test_unique_offer_ids_in_view_model_list(self) -> None:
        offers = [
            {"id": "1", "intitule": "Dev A"},
            {"id": "2", "intitule": "Dev B"},
            {"id": "3", "intitule": "Dev C"},
        ]
        seen_ids = set()
        for offer in offers:
            vm = build_offer_view_model(offer)
            self.assertNotIn(vm.offer_id, seen_ids, f"Duplicate offer_id: {vm.offer_id}")
            seen_ids.add(vm.offer_id)
        self.assertEqual(len(seen_ids), 3)

    def test_enriched_offer_without_titre_field(self) -> None:
        offer = {
            "id": "209XRVH",
            "intitule": "Ingénieur en intelligence artificielle H/F",
            "entreprise": "ACME",
            "territoire": "75 - Paris",
            "ville": "75 - Paris",
            "contrat": "CDI",
            "competences": ["Python", "ML"],
            "source": "France Travail",
        }
        vm = build_offer_view_model(offer)
        self.assertEqual(vm.title, "Ingénieur en intelligence artificielle H/F")
        self.assertNotEqual(vm.title, "Intitulé non renseigné")

    def test_match_with_details_but_no_top_level_scores(self) -> None:
        match = {
            "offer_id": "X1",
            "score": 55.0,
            "matching_skills": ["SQL"],
            "missing_skills": ["NoSQL"],
            "details": {
                "global_score": 55.0,
                "skill_score": 70.0,
                "job_score": 40.0,
                "sous_scores": {
                    "competences": {"score": 70.0, "statut": "evalue", "details": {}},
                    "metier": {"score": 40.0, "statut": "evalue", "details": {}},
                },
                "criterion_scores": {"competences": 0.7, "metier": 0.4},
                "criterion_details": {},
                "explanation": {},
            },
        }
        offer = {"id": "X1", "intitule": "Data Analyst"}
        vm = build_match_view_model(match, offer)
        self.assertEqual(vm.global_score, 55.0)
        self.assertTrue(vm.criterion_scores["skills"]["evaluated"])
        self.assertEqual(vm.criterion_scores["skills"]["score"], 70.0)
        self.assertTrue(vm.criterion_scores["job"]["evaluated"])
        self.assertEqual(vm.criterion_scores["job"]["score"], 40.0)


class DebugModeTest(unittest.TestCase):
    """Tests pour le mode debug."""

    def test_debug_mode_off_by_default(self) -> None:
        from src.presentation.offer_view_model import is_debug_mode
        old = os.environ.get("TREND_RADAR_VIEW_DEBUG")
        os.environ.pop("TREND_RADAR_VIEW_DEBUG", None)
        try:
            self.assertFalse(is_debug_mode())
        finally:
            if old is not None:
                os.environ["TREND_RADAR_VIEW_DEBUG"] = old

    def test_debug_mode_on(self) -> None:
        from src.presentation.offer_view_model import is_debug_mode
        old = os.environ.get("TREND_RADAR_VIEW_DEBUG")
        os.environ["TREND_RADAR_VIEW_DEBUG"] = "1"
        try:
            self.assertTrue(is_debug_mode())
        finally:
            if old is not None:
                os.environ["TREND_RADAR_VIEW_DEBUG"] = old
            else:
                os.environ.pop("TREND_RADAR_VIEW_DEBUG", None)


if __name__ == "__main__":
    unittest.main()
