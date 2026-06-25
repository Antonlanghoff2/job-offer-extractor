# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Tests multi-métiers pour valider le système générique.

Ces tests couvrent au moins 10 métiers différents pour vérifier que
le système fonctionne pour tous les secteurs, pas seulement l'IA/Data.
"""

from __future__ import annotations

import unittest
from typing import Any, Dict

from src.domain_classifier import classify_offer_domain
from src.domain_config import get_all_queries, get_enabled_domains


class DomainConfigTest(unittest.TestCase):
    """Tests pour la configuration multi-métiers."""

    def test_load_domains(self) -> None:
        """Vérifie que les domaines sont chargés."""
        domains = get_enabled_domains()
        self.assertGreater(len(domains), 0)

    def test_multiple_domains(self) -> None:
        """Vérifie qu'il y a au moins 10 domaines."""
        domains = get_enabled_domains()
        self.assertGreaterEqual(len(domains), 10)

    def test_queries_not_empty(self) -> None:
        """Vérifie que les requêtes sont générées."""
        queries = get_all_queries()
        self.assertGreater(len(queries), 0)

    def test_domain_structure(self) -> None:
        """Vérifie la structure des domaines."""
        domains = get_enabled_domains()
        for domain in domains:
            self.assertIn("id", domain)
            self.assertIn("name", domain)
            self.assertIn("queries", domain)


class DomainClassifierTest(unittest.TestCase):
    """Tests pour la classification domaine/métier."""

    def test_classify_developpeur_python(self) -> None:
        """Test classification développeur Python."""
        offer = {
            "intitule": "Développeur Python",
            "description": "Nous recherchons un développeur Python expérimenté.",
            "codeROME": "M1805",
        }
        result = classify_offer_domain(offer)
        self.assertIn(result["domain_id"], ["informatique", "data-ia"])
        self.assertGreater(result["confidence"], 0.5)

    def test_classify_infirmier(self) -> None:
        """Test classification infirmier."""
        offer = {
            "intitule": "Infirmier",
            "description": "Nous recherchons un infirmier pour soins aux patients.",
        }
        result = classify_offer_domain(offer)
        self.assertEqual(result["domain_id"], "sante")
        self.assertGreater(result["confidence"], 0.5)

    def test_classify_electricien(self) -> None:
        """Test classification électricien."""
        offer = {
            "intitule": "Électricien bâtiment",
            "description": "Électricien pour travaux de câblage et installation.",
        }
        result = classify_offer_domain(offer)
        self.assertEqual(result["domain_id"], "batiment")
        self.assertGreater(result["confidence"], 0.5)

    def test_classify_preparateur_commandes(self) -> None:
        """Test classification préparateur de commandes."""
        offer = {
            "intitule": "Préparateur de commandes",
            "description": "Préparation de commandes en entrepôt.",
        }
        result = classify_offer_domain(offer)
        self.assertEqual(result["domain_id"], "transport-logistique")
        self.assertGreater(result["confidence"], 0.5)

    def test_classify_vendeur(self) -> None:
        """Test classification vendeur."""
        offer = {
            "intitule": "Vendeur en magasin",
            "description": "Vendeur pour conseil client et tenue de caisse.",
        }
        result = classify_offer_domain(offer)
        self.assertEqual(result["domain_id"], "commerce")
        self.assertGreater(result["confidence"], 0.5)

    def test_classify_cuisinier(self) -> None:
        """Test classification cuisinier."""
        offer = {
            "intitule": "Cuisinier",
            "description": "Cuisinier pour préparation de repas en restaurant.",
        }
        result = classify_offer_domain(offer)
        self.assertEqual(result["domain_id"], "hotellerie-restauration")
        self.assertGreater(result["confidence"], 0.5)

    def test_classify_technicien_maintenance(self) -> None:
        """Test classification technicien de maintenance."""
        offer = {
            "intitule": "Technicien de maintenance industrielle",
            "description": "Maintenance préventive et corrective de machines.",
        }
        result = classify_offer_domain(offer)
        self.assertIn(result["domain_id"], ["maintenance", "industrie"])
        self.assertGreater(result["confidence"], 0.5)

    def test_classify_assistant_administratif(self) -> None:
        """Test classification assistant administratif."""
        offer = {
            "intitule": "Assistant administratif",
            "description": "Gestion administrative et comptable.",
        }
        result = classify_offer_domain(offer)
        self.assertEqual(result["domain_id"], "administration")
        self.assertGreater(result["confidence"], 0.5)

    def test_classify_regisseur_son(self) -> None:
        """Test classification régisseur son."""
        offer = {
            "intitule": "Régisseur son",
            "description": "Régie son et mixage audio pour événements.",
        }
        result = classify_offer_domain(offer)
        self.assertEqual(result["domain_id"], "audiovisuel-spectacle")
        self.assertGreater(result["confidence"], 0.5)

    def test_classify_conducteur_travaux(self) -> None:
        """Test classification conducteur de travaux."""
        offer = {
            "intitule": "Conducteur de travaux",
            "description": "Conducteur de travaux pour chantier BTP.",
        }
        result = classify_offer_domain(offer)
        self.assertEqual(result["domain_id"], "batiment")
        self.assertGreater(result["confidence"], 0.5)


class MultiDomainOfferTest(unittest.TestCase):
    """Tests pour valider la diversité des offres."""

    def test_10_different_jobs(self) -> None:
        """Test que 10 métiers différents sont classifiés correctement."""
        offers = [
            {"intitule": "Développeur Python", "description": "Python Django"},
            {"intitule": "Infirmier", "description": "Soins aux patients"},
            {"intitule": "Électricien", "description": "Câblage électrique"},
            {"intitule": "Préparateur de commandes", "description": "Préparation commandes"},
            {"intitule": "Vendeur", "description": "Techniques de vente"},
            {"intitule": "Cuisinier", "description": "Préparation de repas"},
            {"intitule": "Technicien de maintenance", "description": "Maintenance machines"},
            {"intitule": "Assistant administratif", "description": "Gestion administrative"},
            {"intitule": "Régisseur son", "description": "Régie son mixage"},
            {"intitule": "Conducteur de travaux", "description": "Chantier BTP"},
        ]

        domains_found = set()
        for offer in offers:
            result = classify_offer_domain(offer)
            domains_found.add(result["domain_id"])

        self.assertGreaterEqual(len(domains_found), 8)


if __name__ == "__main__":
    unittest.main()
