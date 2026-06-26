# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from src.db import fetch_all, fetch_one
from src.jobs.refresh_all import refresh_all
from src.profile_extraction.experience_skill_extractor import extract_skills_from_experience
from src.services.matching_service import compute_match
from src.user_portal import _assemble_profile
from src.web_app import create_app


def _csrf_from_body(body: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', body)
    if not match:
        raise AssertionError("CSRF token not found")
    return match.group(1)


class ProfileExperiencesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(__file__).resolve().parent / "_tmp_profile_experiences"
        self.tmpdir.mkdir(exist_ok=True)
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret-key",
                "DATABASE_PATH": str(self.tmpdir / "trendradar.sqlite"),
                "UPLOAD_FOLDER": str(self.tmpdir / "uploads"),
            }
        )
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        for path in sorted(self.tmpdir.glob("**/*"), reverse=True):
            if path.is_file():
                path.unlink(missing_ok=True)
            elif path.is_dir():
                try:
                    path.rmdir()
                except OSError:
                    pass
        try:
            self.tmpdir.rmdir()
        except OSError:
            pass

    def _register(self, email: str = "alice@example.com") -> None:
        body = self.client.get("/register").get_data(as_text=True)
        token = _csrf_from_body(body)
        response = self.client.post(
            "/register",
            data={"csrf_token": token, "email": email, "password": "secret123"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)

    def _profile_token(self, path: str = "/profile") -> str:
        body = self.client.get(path).get_data(as_text=True)
        return _csrf_from_body(body)

    def _api_headers(self, token: str) -> dict[str, str]:
        return {"X-CSRF-Token": token}

    def _create_manual_skill(self, name: str) -> None:
        token = self._profile_token("/profile/skills")
        response = self.client.post(
            "/profile/skills",
            data={
                "csrf_token": token,
                "name": name,
                "level": "expert",
                "years_experience": "5",
                "source": "manual",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)

    def _create_experience(self, *, title: str, description: str, company: str = "Théâtre Exemple", source: str = "manual") -> int:
        token = self._profile_token("/profile/experiences")
        response = self.client.post(
            "/api/profile/experiences",
            json={
                "job_title": title,
                "company": company,
                "description": description,
                "source": source,
                "auto_extract": True,
                "csrf_token": token,
            },
            headers=self._api_headers(token),
        )
        self.assertEqual(response.status_code, 201)
        payload = response.get_json()
        self.assertEqual(payload["status"], "ok")
        return int(payload["experience"]["id"])

    def test_profile_page_exposes_experience_block(self) -> None:
        self._register()
        body = self.client.get("/profile").get_data(as_text=True)

        self.assertIn("Expériences professionnelles", body)
        self.assertIn("Ajouter une expérience", body)

    def test_create_update_and_delete_experience_via_api(self) -> None:
        self._register()
        token = self._profile_token("/profile/experiences")
        response = self.client.post(
            "/api/profile/experiences",
            json={
                "job_title": "Ingénieur du son",
                "company": "Théâtre Exemple",
                "start_date": "2022-01",
                "end_date": "2024-06",
                "description": "Installation et exploitation d'un réseau audio Dante, mixage sur console numérique et maintenance du parc.",
                "source": "manual",
                "auto_extract": True,
                "csrf_token": token,
            },
            headers=self._api_headers(token),
        )
        self.assertEqual(response.status_code, 201)
        created = response.get_json()["experience"]
        experience_id = int(created["id"])
        self.assertEqual(created["job_title"], "Ingénieur du son")

        update = self.client.put(
            f"/api/profile/experiences/{experience_id}",
            json={
                "job_title": "Ingénieur du son senior",
                "company": "Théâtre Exemple",
                "description": "Gestion d'une équipe de cinq techniciens et planification des interventions.",
                "source": "manual",
                "csrf_token": token,
            },
            headers=self._api_headers(token),
        )
        self.assertEqual(update.status_code, 200)
        updated = update.get_json()["experience"]
        self.assertEqual(updated["job_title"], "Ingénieur du son senior")

        delete = self.client.delete(
            f"/api/profile/experiences/{experience_id}",
            json={"csrf_token": token},
            headers=self._api_headers(token),
        )
        self.assertEqual(delete.status_code, 200)
        self.assertEqual(delete.get_json()["deleted"], True)

        with self.app.app_context():
            self.assertEqual(len(fetch_all("SELECT * FROM experiences")), 0)

    def test_rejects_empty_experience_payload(self) -> None:
        self._register()
        token = self._profile_token("/profile/experiences")
        response = self.client.post(
            "/api/profile/experiences",
            json={"job_title": "", "description": "", "csrf_token": token},
            headers=self._api_headers(token),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("obligatoire", response.get_json()["error"])

    def test_experience_skills_are_confirmed_and_deduplicated_with_manual_skills(self) -> None:
        self._register()
        self._create_manual_skill("Python")
        experience_id = self._create_experience(
            title="Développeur backend Python",
            description="Développement d'API REST avec Flask, PostgreSQL, Docker et Git. Mise en place de tests automatisés.",
        )

        suggestions = extract_skills_from_experience(
            "Développeur backend Python",
            "Développement d'API REST avec Flask, PostgreSQL, Docker et Git. Mise en place de tests automatisés.",
        )
        self.assertIn("Python", {skill["name"] for skill in suggestions})

        token = self._profile_token("/profile/experiences")
        confirm = self.client.post(
            "/api/profile/skills/confirm",
            json={
                "experience_id": experience_id,
                "skills": [{"name": "Python"}, {"name": "Flask"}],
                "csrf_token": token,
            },
            headers=self._api_headers(token),
        )
        self.assertEqual(confirm.status_code, 200)

        with self.app.app_context():
            profile = _assemble_profile(1)
            python_items = [skill for skill in profile["skills"] if skill["normalized_name"] == "Python"]
            self.assertEqual(len(python_items), 1)
            self.assertCountEqual(python_items[0]["sources"], ["manual", "professional_experience"])

        delete = self.client.delete(
            f"/api/profile/experiences/{experience_id}",
            json={"csrf_token": token},
            headers=self._api_headers(token),
        )
        self.assertEqual(delete.status_code, 200)

        with self.app.app_context():
            profile = _assemble_profile(1)
            python_items = [skill for skill in profile["skills"] if skill["normalized_name"] == "Python"]
            self.assertEqual(len(python_items), 1)
            self.assertEqual(python_items[0]["sources"], ["manual"])

    def test_extracted_skills_affect_matching(self) -> None:
        self._register("bob@example.com")
        experience_id = self._create_experience(
            title="Développeur backend Python",
            description="Développement d'API REST avec Flask, PostgreSQL, Docker et Git.",
        )
        token = self._profile_token("/profile/experiences")
        confirm = self.client.post(
            "/api/profile/skills/confirm",
            json={
                "experience_id": experience_id,
                "skills": [{"name": "Python"}, {"name": "Flask"}],
                "csrf_token": token,
            },
            headers=self._api_headers(token),
        )
        self.assertEqual(confirm.status_code, 200)

        with self.app.app_context():
            profile = _assemble_profile(1)
            offer = {
                "titre": "Développeur backend",
                "competences": ["Python", "Docker"],
                "contrat": "CDI",
                "experience_requise": "3 ans",
            }
            match = compute_match(profile, offer)
            self.assertGreater(match["global_score"], 0)
            self.assertIn("Python", match["matching_skills"])

    def test_old_profile_without_experiences_remains_supported(self) -> None:
        self._register("carol@example.com")
        with self.app.app_context():
            profile = _assemble_profile(1)
            self.assertIn("professional_experiences", profile)
            self.assertEqual(profile["professional_experiences"], [])

    def test_profile_experience_page_exposes_extract_button(self) -> None:
        self._register("diane@example.com")
        token = self._profile_token("/profile/experiences")
        self.client.post(
            "/profile/experiences",
            data={
                "csrf_token": token,
                "job_title": "Ingénieur du son",
                "company": "Théâtre Exemple",
                "description": "Installation et exploitation d'un réseau audio Dante.",
                "skills": "Dante",
                "source": "manual",
            },
            follow_redirects=True,
        )
        body = self.client.get("/profile/experiences").get_data(as_text=True)
        self.assertIn("Extraire", body)
        self.assertIn("Extraction des compétences", body)


if __name__ == "__main__":
    unittest.main()
