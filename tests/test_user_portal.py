# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

from __future__ import annotations

import io
import re
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from werkzeug.datastructures import MultiDict

from src.db import fetch_all, fetch_one
from src.web_app import create_app


def _csrf_from_body(body: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', body)
    if not match:
        raise AssertionError("CSRF token not found in response body")
    return match.group(1)


def _make_docx_bytes() -> bytes:
    xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>Compétences</w:t></w:r></w:p>
    <w:p><w:r><w:t>Python</w:t></w:r></w:p>
    <w:p><w:r><w:t>Diplômes</w:t></w:r></w:p>
    <w:p><w:r><w:t>Mastère spécialisé</w:t></w:r></w:p>
    <w:p><w:r><w:t>Expériences</w:t></w:r></w:p>
    <w:p><w:r><w:t>Développeur backend</w:t></w:r></w:p>
  </w:body>
</w:document>'''
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml", xml)
    return buf.getvalue()


def _make_pdf_bytes() -> bytes:
    return (
        b"%PDF-1.4\n1 0 obj\n<<>>\nstream\n"
        b"(Python) Tj\n(Diplome Bac+5) Tj\n(Developpeur backend) Tj\n"
        b"endstream\n%%EOF"
    )


class UserPortalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret-key",
                "DATABASE_PATH": str(root / "trendradar.sqlite"),
                "UPLOAD_FOLDER": str(root / "uploads"),
            }
        )
        self.client = self.app.test_client()
        self.client2 = self.app.test_client()

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _register(self, client, email: str, password: str = "secret123") -> None:
        body = client.get("/register").get_data(as_text=True)
        token = _csrf_from_body(body)
        response = client.post(
            "/register",
            data={"csrf_token": token, "email": email, "password": password},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)

    def _profile_token(self, client, path: str = "/profile") -> str:
        body = client.get(path).get_data(as_text=True)
        return _csrf_from_body(body)

    def test_login_page_uses_shared_navigation(self) -> None:
        response = self.client.get("/login")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Recherche d'offres", body)
        self.assertIn("Tendances par territoire", body)
        self.assertIn("Mon compte", body)
        self.assertIn("Mon profil", body)
        self.assertIn("Déconnexion", body)

    def test_register_and_access_protection(self) -> None:
        response = self.client.get("/profile")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

        self._register(self.client, "alice@example.com")
        response = self.client.get("/profile")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Mon profil", response.get_data(as_text=True))

    def test_profile_skill_diploma_and_experience_crud(self) -> None:
        self._register(self.client, "alice@example.com")

        token = self._profile_token(self.client)
        self.client.post(
            "/profile",
            data={
                "csrf_token": token,
                "first_name": "Alice",
                "last_name": "Martin",
                "city": "Lyon",
                "postal_code": "69000",
                "department": "69",
                "search_radius_km": "20",
                "contract_preference": "CDI",
                "remote_preference": "hybride",
                "minimum_salary": "45000",
                "availability": "Immédiate",
                "summary": "Développeuse Python",
                "desired_jobs": "Développeur backend\nData engineer",
            },
            follow_redirects=True,
        )

        token = self._profile_token(self.client, "/profile/skills")
        self.client.post(
            "/profile/skills",
            data={
                "csrf_token": token,
                "name": "Python",
                "level": "expert",
                "years_experience": "5",
                "source": "manual",
            },
            follow_redirects=True,
        )

        token = self._profile_token(self.client, "/profile/diplomas")
        self.client.post(
            "/profile/diplomas",
            data={
                "csrf_token": token,
                "title": "Master Informatique",
                "level": "Bac+5",
                "institution": "Université de Lyon",
                "speciality": "IA",
                "graduation_year": "2022",
                "description": "Diplôme obtenu",
                "source": "manual",
            },
            follow_redirects=True,
        )

        token = self._profile_token(self.client, "/profile/experiences")
        self.client.post(
            "/profile/experiences",
            data={
                "csrf_token": token,
                "job_title": "Développeur backend",
                "company": "ACME",
                "city": "Lyon",
                "start_date": "2020-01-01",
                "end_date": "2024-01-01",
                "description": "Python et Flask",
                "skills": "Python, Flask",
                "source": "manual",
            },
            follow_redirects=True,
        )

        with self.app.app_context():
            profile = fetch_one("SELECT * FROM user_profiles WHERE first_name = ?", ("Alice",))
            self.assertIsNotNone(profile)
            self.assertEqual(profile["contract_preference"], "CDI")
            self.assertEqual(len(fetch_all("SELECT * FROM user_skills")), 1)
            self.assertEqual(len(fetch_all("SELECT * FROM diplomas")), 1)
            self.assertEqual(len(fetch_all("SELECT * FROM experiences")), 1)

    def test_isolation_between_two_users(self) -> None:
        self._register(self.client, "alice@example.com")
        token = self._profile_token(self.client, "/profile/skills")
        self.client.post(
            "/profile/skills",
            data={
                "csrf_token": token,
                "name": "Python",
                "level": "expert",
                "years_experience": "5",
                "source": "manual",
            },
            follow_redirects=True,
        )
        self.client.get("/logout")

        self._register(self.client2, "bob@example.com")
        body = self.client2.get("/profile/skills").get_data(as_text=True)
        self.assertIn("Aucune compétence enregistrée", body)
        self.assertNotIn("Python", body)

    def test_cv_upload_docx_pdf_and_rejection(self) -> None:
        self._register(self.client, "alice@example.com")

        token = self._profile_token(self.client, "/profile/cv")
        response = self.client.post(
            "/profile/cv",
            data={
                "csrf_token": token,
                "cv_file": (io.BytesIO(_make_docx_bytes()), "cv.docx"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Valider les informations extraites", response.get_data(as_text=True))

        token = self._profile_token(self.client, "/profile/cv")
        response = self.client.post(
            "/profile/cv",
            data={
                "csrf_token": token,
                "cv_file": (io.BytesIO(b"not-allowed"), "cv.txt"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertIn("Format de fichier interdit", response.get_data(as_text=True))

        token = self._profile_token(self.client, "/profile/cv")
        self.client.post(
            "/profile/cv",
            data={
                "csrf_token": token,
                "cv_file": (io.BytesIO(_make_pdf_bytes()), "cv.pdf"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        validate_body = self.client.get("/profile/cv/validate").get_data(as_text=True)
        token = _csrf_from_body(validate_body)
        payload = MultiDict(
            [
                ("csrf_token", token),
                ("skill_name", "Python"),
                ("skill_level", "expert"),
                ("skill_years", "4"),
                ("diploma_title", "Bac+5"),
                ("diploma_level", "Bac+5"),
                ("diploma_school", "Université"),
                ("diploma_year", "2020"),
                ("experience_job", "Développeur backend"),
                ("experience_company", "ACME"),
                ("experience_start", "2020-01-01"),
                ("experience_end", "2024-01-01"),
                ("experience_desc", "Backend Python"),
            ]
        )
        response = self.client.post("/profile/cv/validate", data=payload, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Mon profil", response.get_data(as_text=True))

        with self.app.app_context():
            self.assertIsNotNone(fetch_one("SELECT * FROM user_cvs"))

    def test_recommendations_and_dashboard_use_original_url(self) -> None:
        self._register(self.client, "alice@example.com")
        token = self._profile_token(self.client)
        self.client.post(
            "/profile",
            data={
                "csrf_token": token,
                "first_name": "Alice",
                "last_name": "Martin",
                "city": "Lyon",
                "postal_code": "69000",
                "department": "69",
                "search_radius_km": "20",
                "contract_preference": "CDI",
                "remote_preference": "indifferent",
                "minimum_salary": "45000",
                "availability": "Immédiate",
                "summary": "Développeuse Python",
                "desired_jobs": "Développeur backend",
            },
            follow_redirects=True,
        )
        token = self._profile_token(self.client, "/profile/skills")
        self.client.post(
            "/profile/skills",
            data={
                "csrf_token": token,
                "name": "Python",
                "level": "expert",
                "years_experience": "5",
                "source": "manual",
            },
            follow_redirects=True,
        )

        offers = [
            {
                "id": "off-1",
                "titre": "Développeur backend Python",
                "entreprise": "ACME",
                "competences": ["Python", "Flask", "Docker"],
                "diplomes_requis": ["Master Informatique"],
                "contrat": "CDI",
                "teletravail": "hybride",
                "lieux": ["Lyon"],
                "experience_requise": "3 ans",
                "url_originale": "https://example.com/off-1",
                "source": "France Travail",
            },
            {
                "id": "off-2",
                "titre": "Data Analyst",
                "entreprise": "Beta",
                "competences": ["SQL"],
                "contrat": "CDD",
                "lieux": ["Paris"],
                "source": "France Travail",
            },
        ]

        with patch("src.user_portal._load_local_offers", return_value=offers):
            response = self.client.get("/mes-offres")
            body = response.get_data(as_text=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn("Voir l’offre", body)
            self.assertIn("https://example.com/off-1", body)
            self.assertIn("Lien indisponible", body)
            self.assertIn("Sous-scores", body)
            self.assertIn("France Travail", body)

            response = self.client.get("/dashboard-utilisateur")
            body = response.get_data(as_text=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn("Compétences à développer", body)
            self.assertIn("Offres compatibles", body)
            self.assertIn("Répartition des contrats", body)
            self.assertIn("Répartition géographique", body)
            self.assertIn("Compétences les plus demandées", body)

        with self.app.app_context():
            self.assertGreaterEqual(len(fetch_all("SELECT * FROM job_matches")), 1)


if __name__ == "__main__":
    unittest.main()
