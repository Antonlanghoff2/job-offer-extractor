# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

from __future__ import annotations

import io
import json
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

    def _save_matching_weights(self, client, token: str, **weights: str) -> None:
        payload = {
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
        }
        payload.update(weights)
        response = client.post("/profile", data=payload, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

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
        skills_body = self.client.get("/profile/skills").get_data(as_text=True)
        self.assertIn("Python", skills_body)
        self.assertIn("expert", skills_body)
        self.assertIn("5", skills_body)

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

        profile_body = self.client.get("/profile").get_data(as_text=True)
        self.assertIn("Mes compétences et mes formations", profile_body)
        self.assertIn("Python", profile_body)
        self.assertIn("Master Informatique", profile_body)

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

        preview_body = self.client.get("/profile/cv/preview").get_data(as_text=True)
        self.assertEqual(self.client.get("/profile/cv/preview").status_code, 200)
        self.assertIn("Aperçu de mon CV", preview_body)

        with self.app.app_context():
            self.assertIsNotNone(fetch_one("SELECT * FROM user_cvs"))

    def test_cv_validation_supports_indexed_dynamic_blocks(self) -> None:
        self._register(self.client, "alice@example.com")

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
        self.assertIn("Valider les informations extraites", validate_body)
        self.assertIn("+ Ajouter une compétence", validate_body)
        self.assertIn("+ Ajouter une formation", validate_body)
        self.assertIn("+ Ajouter une expérience", validate_body)

        token = _csrf_from_body(validate_body)
        payload = MultiDict(
            [
                ("csrf_token", token),
                ("competences[0][nom]", "Python"),
                ("competences[0][categorie]", "langage"),
                ("competences[0][source]", "explicite"),
                ("competences[0][texte_source]", "Python, SQL, Flask"),
                ("competences[0][confiance]", "0.98"),
                ("formations[0][intitule]", "Master Informatique"),
                ("formations[0][etablissement]", "Université de Lyon"),
                ("formations[0][niveau]", "Master"),
                ("formations[0][annee]", "2022"),
                ("formations[0][texte_source]", "Master Informatique - Université de Lyon"),
                ("formations[0][confiance]", "0.91"),
                ("experiences_professionnelles[0][poste]", "Développeur backend"),
                ("experiences_professionnelles[0][entreprise]", "ACME"),
                ("experiences_professionnelles[0][lieu]", "Lyon"),
                ("experiences_professionnelles[0][date_debut]", "2020-01-01"),
                ("experiences_professionnelles[0][date_fin]", "2024-01-01"),
                ("experiences_professionnelles[0][description]", "Python et Flask"),
                ("experiences_professionnelles[0][competences_associees]", "Python, Flask"),
                ("experiences_professionnelles[0][texte_source]", "Développeur backend - ACME - 2020 à 2024"),
                ("experiences_professionnelles[0][confiance]", "0.89"),
            ]
        )
        response = self.client.post("/profile/cv/validate", data=payload, follow_redirects=True)
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Mon profil", body)

        with self.app.app_context():
            self.assertEqual(len(fetch_all("SELECT * FROM diplomas WHERE source = 'cv'")), 1)
            self.assertEqual(len(fetch_all("SELECT * FROM user_skills WHERE source = 'cv'")), 1)
            self.assertEqual(len(fetch_all("SELECT * FROM experiences WHERE source = 'cv'")), 1)

        profile_body = self.client.get("/profile").get_data(as_text=True)
        self.assertIn("Python", profile_body)
        self.assertIn("Master Informatique", profile_body)
        experience_body = self.client.get("/profile/experiences").get_data(as_text=True)
        self.assertIn("Développeur backend", experience_body)


    def test_dashboard_computes_matches_without_preloading_recommendations(self) -> None:
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
        ]

        with patch("src.user_portal._load_local_offers", return_value=offers):
            response = self.client.get("/dashboard-utilisateur")
            body = response.get_data(as_text=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn("Offres compatibles", body)
            self.assertIn("Voir l’offre", body)
            self.assertIn("https://example.com/off-1", body)

    def test_dashboard_uses_internal_fallback_when_offer_url_is_missing(self) -> None:
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
            response = self.client.get("/dashboard-utilisateur")
            body = response.get_data(as_text=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn("Voir l’offre", body)
            self.assertIn("/mes-offres/off-2", body)

    def test_dashboard_best_offer_displays_full_offer_details(self) -> None:
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
        ]

        with patch("src.user_portal._load_local_offers", return_value=offers):
            response = self.client.get("/dashboard-utilisateur")
            body = response.get_data(as_text=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn("Meilleure offre", body)
            self.assertIn("Développeur backend Python", body)
            self.assertIn("ACME", body)
            self.assertIn("Lyon", body)
            self.assertIn("Score", body)
            self.assertIn("https://example.com/off-1", body)

    def test_profile_page_exposes_matching_weights_and_persists_them(self) -> None:
        self._register(self.client, "alice@example.com")
        token = self._profile_token(self.client)
        response = self.client.get("/profile")
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Personnaliser les critères de matching", body)
        self.assertIn("Réinitialiser les pondérations", body)
        self.assertIn("Salaire", body)

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
                "matching_weights_competences": "5",
                "matching_weights_metier": "5",
                "matching_weights_experience": "10",
                "matching_weights_diplome": "10",
                "matching_weights_localisation": "50",
                "matching_weights_contrat": "5",
                "matching_weights_teletravail": "5",
                "matching_weights_salaire": "10",
            },
            follow_redirects=True,
        )
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["matching_weights"]["localisation"], 50.0)
            self.assertEqual(sess["matching_weights"]["competences"], 5.0)
            self.assertEqual(sess["matching_weights"]["salaire"], 10.0)

    def test_profile_lists_skill_names(self) -> None:
        self._register(self.client, "alice@example.com")
        token = self._profile_token(self.client)
        self.client.post(
            "/profile",
            data={
                "csrf_token": token,
                "first_name": "Alice",
                "last_name": "Martin",
                "city": "Lyon",
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

        body = self.client.get("/profile").get_data(as_text=True)
        self.assertIn("Python", body)
        self.assertIn("Compétences", body)

    def test_training_recommendation_page_handles_invalid_period_without_500(self) -> None:
        self._register(self.client, "alice@example.com")
        offers = [
            {
                "id": "off-1",
                "titre": "Développeur Python",
                "competences": ["Python", "Flask"],
                "metier": "Développeur Python",
                "territoire": "Lyon",
                "date_publication": "2026-06-20",
            }
        ]
        with patch("src.user_portal.load_normalized_offers", return_value=(offers, None)):
            response = self.client.get("/recommandation-formation?periode_jours=abc&territoire=Lyon")
            body = response.get_data(as_text=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn("Recommandation de formation", body)
            self.assertIn("Tous les territoires", body)

    def test_recommendations_and_dashboard_use_profile_weights_for_ranking(self) -> None:
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
                "matching_weights_competences": "100",
                "matching_weights_metier": "0",
                "matching_weights_experience": "0",
                "matching_weights_diplome": "0",
                "matching_weights_localisation": "0",
                "matching_weights_contrat": "0",
                "matching_weights_teletravail": "0",
                "matching_weights_salaire": "0",
            },
            follow_redirects=True,
        )

        offers = [
            {
                "id": "off-skill",
                "titre": "Développeur backend Python",
                "entreprise": "SkillFirst",
                "competences": ["Python", "Flask"],
                "contrat": "CDI",
                "lieux": ["Paris"],
                "source": "France Travail",
            },
            {
                "id": "off-location",
                "titre": "Développeur backend généraliste",
                "entreprise": "LocFirst",
                "competences": ["Java"],
                "contrat": "CDI",
                "lieux": ["Lyon"],
                "source": "France Travail",
            },
        ]

        with patch("src.user_portal._load_local_offers", return_value=offers):
            recommendations_body = self.client.get("/mes-offres").get_data(as_text=True)
            self.assertLess(recommendations_body.find("SkillFirst"), recommendations_body.find("LocFirst"))

            dashboard_body = self.client.get("/dashboard-utilisateur").get_data(as_text=True)
            self.assertIn("SkillFirst", dashboard_body)
            self.assertIn("Meilleure offre", dashboard_body)
            self.assertIn("Localisation:", dashboard_body)
            self.assertIn("Salaire:", dashboard_body)

    def test_profile_export_returns_json_payload(self) -> None:
        self._register(self.client, "alice@example.com")
        token = self._profile_token(self.client)
        self.client.post(
            "/profile",
            data={
                "csrf_token": token,
                "first_name": "Alice",
                "last_name": "Martin",
                "city": "Lyon",
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
        response = self.client.get("/profile/export-data")
        payload = json.loads(response.get_data(as_text=True))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["user"]["profile"]["first_name"], "Alice")
        self.assertEqual(payload["skills"][0]["name"], "Python")

    def test_delete_account_removes_user_and_personal_data(self) -> None:
        self._register(self.client, "alice@example.com")
        token = self._profile_token(self.client)
        self.client.post(
            "/profile",
            data={
                "csrf_token": token,
                "first_name": "Alice",
                "last_name": "Martin",
                "city": "Lyon",
                "desired_jobs": "Développeur backend",
            },
            follow_redirects=True,
        )

        token = self._profile_token(self.client, "/profile")
        response = self.client.post(
            "/profile/delete-account",
            data={"csrf_token": token},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Créer un compte", response.get_data(as_text=True))
        with self.app.app_context():
            self.assertIsNone(fetch_one("SELECT * FROM users WHERE email = ?", ("alice@example.com",)))
            self.assertEqual(len(fetch_all("SELECT * FROM user_profiles")), 0)
            self.assertEqual(len(fetch_all("SELECT * FROM user_skills")), 0)
            self.assertEqual(len(fetch_all("SELECT * FROM diplomas")), 0)
            self.assertEqual(len(fetch_all("SELECT * FROM experiences")), 0)

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
            self.assertIn("https://candidat.francetravail.fr/offres/recherche/detail/off-2", body)
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
