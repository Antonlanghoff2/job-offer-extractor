# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from src.france_travail_client import _build_search_params, search_offres


class FranceTravailClientTest(unittest.TestCase):
    @patch("src.france_travail_client.get_access_token", return_value="token")
    @patch("src.france_travail_client.requests.get")
    def test_search_without_territory_omits_empty_parameters(self, mock_get: Mock, _mock_token: Mock) -> None:
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"resultats": []}
        mock_get.return_value = response

        search_offres("python", range_value="0-149")

        params = mock_get.call_args.kwargs["params"]
        self.assertEqual(params, {"motsCles": "python", "range": "0-149"})

    @patch("src.france_travail_client.get_access_token", return_value="token")
    @patch("src.france_travail_client.requests.get")
    def test_search_by_commune_adds_distance(self, mock_get: Mock, _mock_token: Mock) -> None:
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"resultats": []}
        mock_get.return_value = response

        search_offres("data", commune="69123", distance=20, range_value="150-299")

        params = mock_get.call_args.kwargs["params"]
        self.assertEqual(params, {"motsCles": "data", "range": "150-299", "commune": "69123", "distance": 20})

    @patch("src.france_travail_client.get_access_token", return_value="token")
    @patch("src.france_travail_client.requests.get")
    def test_search_by_department(self, mock_get: Mock, _mock_token: Mock) -> None:
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"resultats": []}
        mock_get.return_value = response

        search_offres("ia", departement="75")

        params = mock_get.call_args.kwargs["params"]
        self.assertEqual(params, {"motsCles": "ia", "range": "0-149", "departement": "75"})

    @patch("src.france_travail_client.get_access_token", return_value="token")
    @patch("src.france_travail_client.requests.get")
    def test_search_by_region(self, mock_get: Mock, _mock_token: Mock) -> None:
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"resultats": []}
        mock_get.return_value = response

        search_offres("ia", region="84")

        params = mock_get.call_args.kwargs["params"]
        self.assertEqual(params, {"motsCles": "ia", "range": "0-149", "region": "84"})

    def test_build_search_params_drops_empty_values(self) -> None:
        params = _build_search_params(" python ", commune="", departement=None, region="  ", distance=None, range_value="0-149")
        self.assertEqual(params, {"motsCles": "python", "range": "0-149"})


if __name__ == "__main__":
    unittest.main()
