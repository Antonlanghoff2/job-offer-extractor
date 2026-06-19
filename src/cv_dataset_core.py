# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Core helpers for the synthetic CV dataset generator and validator."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import json
import random
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable, Iterator

try:  # pragma: no cover - exercised indirectly when Faker is installed.
    from faker import Faker as _Faker
except ImportError:  # pragma: no cover - local fallback when Faker is unavailable.
    _Faker = None


LABELS: tuple[str, ...] = (
    "NAME",
    "EMAIL",
    "PHONE",
    "ADDRESS",
    "POSTAL_CODE",
    "CITY",
    "JOB_TITLE",
    "COMPANY",
    "DATE",
    "EXPERIENCE_DURATION",
    "DEGREE",
    "SCHOOL",
    "SKILL",
    "LANGUAGE",
    "CERTIFICATION",
    "PROJECT",
    "WEBSITE",
    "LINKEDIN",
    "GITHUB",
    "DRIVING_LICENSE",
    "SECTION_HEADER",
)

CONTACT_LABELS: tuple[str, ...] = ("EMAIL", "PHONE", "ADDRESS", "WEBSITE", "LINKEDIN", "GITHUB")

TEMPLATES: tuple[str, ...] = (
    "classic",
    "compact",
    "technical",
    "academic",
    "creative",
    "minimal",
    "noisy_pdf",
)

MONTHS_FR: tuple[str, ...] = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)

SECTION_VARIANTS: dict[str, tuple[str, ...]] = {
    "experience": (
        "EXPÉRIENCES PROFESSIONNELLES",
        "EXPÉRIENCE",
        "PARCOURS PROFESSIONNEL",
        "MISSIONS",
    ),
    "education": (
        "FORMATION",
        "DIPLÔMES",
        "ÉTUDES",
    ),
    "skills": (
        "COMPÉTENCES",
        "COMPÉTENCES TECHNIQUES",
        "TECHNOLOGIES",
        "OUTILS",
    ),
    "languages": (
        "LANGUES",
        "LANGUAGE",
    ),
    "certifications": (
        "CERTIFICATIONS",
        "CERTIFICATS",
    ),
    "projects": (
        "PROJETS",
        "RÉALISATIONS",
    ),
    "contact": (
        "COORDONNÉES",
        "CONTACT",
    ),
    "summary": (
        "PROFIL",
        "RÉSUMÉ",
        "À PROPOS",
    ),
}

EXPERIENCE_LEVEL_RANGES: dict[str, tuple[int, int]] = {
    "junior": (0, 2),
    "intermediate": (2, 5),
    "senior": (5, 10),
    "lead": (8, 15),
}

EDUCATION_LEVELS: tuple[str, ...] = (
    "Bac+2",
    "Bac+3",
    "Bac+4",
    "Bac+5",
)

LANGUAGE_LEVELS: tuple[str, ...] = ("A2", "B1", "B2", "C1", "C2")

DATE_STYLES: tuple[str, ...] = (
    "year_range",
    "numeric_range",
    "text_range",
    "since",
    "today",
    "mixed",
)

PHONE_FORMATS: tuple[str, ...] = (
    "06 12 34 56 78",
    "06.12.34.56.78",
    "+33 6 12 34 56 78",
    "0612345678",
)


@dataclass(frozen=True)
class EntitySpan:
    """Entity annotation with explicit offsets."""

    start: int
    end: int
    label: str
    text: str


@dataclass
class AnnotatedTextBuilder:
    """Build text incrementally while tracking entity offsets."""

    parts: list[str]
    entities: list[EntitySpan]
    position: int

    def __init__(self) -> None:
        self.parts = []
        self.entities = []
        self.position = 0

    def append(self, text: str) -> None:
        """Append plain text."""

        if not isinstance(text, str):
            raise TypeError("Le texte ajouté doit être une chaîne.")
        if not text:
            return
        self.parts.append(text)
        self.position += len(text)

    def append_entity(self, text: str, label: str) -> EntitySpan:
        """Append an annotated fragment and register its offsets."""

        if not text:
            raise ValueError("Une entité ne peut pas être vide.")
        if label not in LABELS:
            raise ValueError(f"Label non autorisé: {label}")

        start = self.position
        self.append(text)
        entity = EntitySpan(start=start, end=self.position, label=label, text=text)
        self.entities.append(entity)
        return entity

    def newline(self, count: int = 1) -> None:
        """Append one or more line breaks."""

        if count < 0:
            raise ValueError("Le nombre de retours à la ligne doit être positif.")
        self.append("\n" * count)

    def separator(self, text: str = " ") -> None:
        """Append a separator between fragments."""

        self.append(text)

    def build(self) -> tuple[str, list[dict[str, Any]]]:
        """Return the final text and serializable entities."""

        return "".join(self.parts), [entity.__dict__ for entity in self.entities]


class SyntheticDataProvider:
    """Synthetic French data provider with a Faker-backed implementation."""

    _FIRST_NAMES = (
        "Camille",
        "Alexandre",
        "Sophie",
        "Nicolas",
        "Élodie",
        "Hugo",
        "Inès",
        "Julien",
        "Manon",
        "Thomas",
    )
    _LAST_NAMES = (
        "Durand",
        "Lefèvre",
        "Martin",
        "Moreau",
        "Bernard",
        "Dubois",
        "Petit",
        "Roux",
        "Fontaine",
        "Girard",
    )
    _STREET_NAMES = (
        "rue des Tilleuls",
        "avenue des Arts",
        "boulevard du Port",
        "rue des Lumières",
        "allée des Cerisiers",
        "rue du Faubourg",
        "place des Métiers",
        "rue de l'Atelier",
    )
    _CITIES = (
        "Lumière-sur-Mer",
        "Montval",
        "Belle-Rive",
        "Valdoria",
        "Saint-Aubin-des-Bois",
        "Rocheclaire",
        "Noisely",
        "Auberoche",
    )
    _COMPANIES = (
        "Nova Conseil",
        "Atelier Sigma",
        "Orbite Studio",
        "Hexa Systems",
        "Mistral Numérique",
        "Ligne Claire Tech",
        "Pixel Forge",
        "Argentum Lab",
    )
    _WORDS = (
        "conception",
        "déploiement",
        "analyse",
        "robustesse",
        "qualité",
        "automatisation",
        "collaboration",
        "architecture",
        "performance",
        "synchronisation",
        "intégration",
        "maintenance",
        "innovation",
        "monitoring",
    )

    def __init__(self, seed: int) -> None:
        self.random = random.Random(seed)
        if _Faker is not None:
            self.faker = _Faker("fr_FR")
            self.faker.seed_instance(seed)
        else:  # pragma: no cover - local fallback only.
            self.faker = None

    @staticmethod
    def _slugify(text: str) -> str:
        normalized = unicodedata.normalize("NFKD", text)
        ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
        ascii_text = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text.lower()).strip("-")
        return ascii_text or "synthetic"

    def _choice(self, values: Iterable[str]) -> str:
        pool = tuple(values)
        return pool[self.random.randrange(len(pool))]

    def first_name(self) -> str:
        if self.faker is not None:
            return self.faker.first_name()
        return self._choice(self._FIRST_NAMES)

    def last_name(self) -> str:
        if self.faker is not None:
            return self.faker.last_name()
        return self._choice(self._LAST_NAMES)

    def name(self) -> str:
        if self.faker is not None:
            return self.faker.name()
        return f"{self.first_name()} {self.last_name()}"

    def street_address(self) -> str:
        if self.faker is not None:
            return self.faker.street_address()
        return f"{self.random.randint(1, 198)} {self._choice(self._STREET_NAMES)}"

    def city(self) -> str:
        if self.faker is not None:
            return self.faker.city()
        return self._choice(self._CITIES)

    def postalcode(self) -> str:
        if self.faker is not None:
            return self.faker.postcode()
        return f"{self.random.randint(10000, 98999):05d}"

    def company(self) -> str:
        if self.faker is not None:
            return self.faker.company()
        return self._choice(self._COMPANIES)

    def email(self, name: str) -> str:
        slug = self._slugify(name)
        if self.faker is not None:
            return f"{slug}.{self.random.randint(1, 999)}@example.fr"
        return f"{slug}@example.fr"

    def phone_number(self) -> str:
        if self.faker is not None:
            raw = self.faker.phone_number()
            digits = re.sub(r"\D", "", raw)
            if len(digits) >= 10:
                digits = digits[-10:]
                return f"{digits[:2]} {digits[2:4]} {digits[4:6]} {digits[6:8]} {digits[8:10]}"
        return self._choice(PHONE_FORMATS)

    def website(self, name: str) -> str:
        slug = self._slugify(name)
        return f"https://portfolio-{slug}.example.com"

    def linkedin(self, name: str) -> str:
        return f"https://www.linkedin.com/in/{self._slugify(name)}"

    def github(self, name: str) -> str:
        return f"https://github.com/{self._slugify(name)}"

    def sentence(self, min_words: int = 6, max_words: int = 12) -> str:
        count = self.random.randint(min_words, max_words)
        words = [self._choice(self._WORDS) for _ in range(count)]
        sentence = " ".join(words).capitalize()
        return sentence + "."

    def paragraph(self, min_sentences: int = 2, max_sentences: int = 4) -> str:
        count = self.random.randint(min_sentences, max_sentences)
        return " ".join(self.sentence() for _ in range(count))

    def company_suffix(self) -> str:
        return self._choice(("Consulting", "Studio", "Lab", "Group", "Partners", "Digital"))


@dataclass(frozen=True)
class Profile:
    """Career profile used to keep synthetic CVs coherent."""

    target_job: str
    alternate_titles: tuple[str, ...]
    skills: tuple[str, ...]
    degrees: tuple[str, ...]
    certifications: tuple[str, ...]
    missions: tuple[str, ...]
    projects: tuple[str, ...]
    languages: tuple[str, ...]


PROFILE_LIBRARY: dict[str, Profile] = {
    "Développeur Python": Profile(
        target_job="Développeur Python",
        alternate_titles=("Python Developer", "Ingénieur logiciel Python", "Développeur backend Python"),
        skills=("Python", "FastAPI", "Flask", "Django", "SQL", "PostgreSQL", "Git", "Docker", "REST API", "Pandas", "NumPy"),
        degrees=("Master Informatique", "Diplôme d'ingénieur en informatique", "Licence informatique"),
        certifications=("Python Institute PCEP", "AWS Cloud Practitioner", "Scrum Master"),
        missions=(
            "Concevoir et maintenir des API REST en Python",
            "Automatiser les traitements de données et les tests",
            "Industrialiser les déploiements avec Docker et Git",
        ),
        projects=("API métier", "Plateforme d'automatisation", "Portail interne"),
        languages=("Français", "Anglais"),
    ),
    "Développeur PHP Symfony": Profile(
        target_job="Développeur PHP Symfony",
        alternate_titles=("Développeur PHP", "Ingénieur backend PHP", "Développeur web Symfony"),
        skills=("PHP", "Symfony", "Doctrine", "MySQL", "JavaScript", "Twig", "Git", "Docker", "API Platform", "REST API"),
        degrees=("Master Informatique", "BTS Services informatiques aux organisations", "Licence professionnelle développement web"),
        certifications=("Symfony Certification", "AWS Cloud Practitioner", "Scrum Product Owner"),
        missions=(
            "Développer des applications web robustes en PHP",
            "Exposer des API REST pour les applications métiers",
            "Assurer la maintenance corrective et évolutive",
        ),
        projects=("Portail client", "Catalogue e-commerce", "Back-office métier"),
        languages=("Français", "Anglais"),
    ),
    "Développeur C++ Qt": Profile(
        target_job="Développeur C++ Qt",
        alternate_titles=("Ingénieur logiciel C++", "Développeur embarqué C++", "Développeur Qt"),
        skills=("C++", "Qt", "CMake", "Git", "Linux", "OpenGL", "Tests unitaires", "Architecture logicielle"),
        degrees=("Diplôme d'ingénieur en informatique", "Master systèmes embarqués", "Licence informatique"),
        certifications=("Linux Foundation Certified System Administrator", "Scrum Master"),
        missions=(
            "Développer des interfaces techniques en C++ et Qt",
            "Optimiser les performances d'applications métier",
            "Industrialiser la compilation et les tests",
        ),
        projects=("Interface de supervision", "Console de contrôle", "Outil de visualisation"),
        languages=("Français", "Anglais"),
    ),
    "Développeur full-stack": Profile(
        target_job="Développeur full-stack",
        alternate_titles=("Développeur Full Stack", "Ingénieur logiciel full-stack", "Développeur web full-stack"),
        skills=("JavaScript", "TypeScript", "React", "Vue.js", "Python", "FastAPI", "SQL", "PostgreSQL", "Docker", "Git", "REST API"),
        degrees=("Master Informatique", "Bachelor développement web", "Licence informatique"),
        certifications=("Scrum Master", "AWS Cloud Practitioner", "MongoDB Associate"),
        missions=(
            "Développer le front-end et le back-end d'applications web",
            "Concevoir des interfaces réactives et des API robustes",
            "Travailler en méthode agile avec les équipes produit",
        ),
        projects=("Plateforme SaaS", "Application métier", "Portail collaboratif"),
        languages=("Français", "Anglais", "Espagnol"),
    ),
    "Data Analyst": Profile(
        target_job="Data Analyst",
        alternate_titles=("Analyste de données", "Business Data Analyst", "Analyste reporting"),
        skills=("SQL", "Python", "Pandas", "NumPy", "Power BI", "Tableau", "PostgreSQL", "Statistiques", "ETL", "Git"),
        degrees=("Master Data Analytics", "Master statistique", "Licence économie et data"),
        certifications=("Microsoft Power BI Data Analyst", "Google Data Analytics", "Scrum Master"),
        missions=(
            "Construire des tableaux de bord et des rapports de pilotage",
            "Analyser les indicateurs métiers et industriels",
            "Automatiser les extractions et les contrôles de qualité",
        ),
        projects=("Dashboard de pilotage", "Reporting commercial", "Suivi qualité"),
        languages=("Français", "Anglais"),
    ),
    "Data Scientist": Profile(
        target_job="Data Scientist",
        alternate_titles=("Scientifique des données", "Data Science Engineer", "Scientifique data"),
        skills=("Python", "scikit-learn", "Pandas", "NumPy", "Machine Learning", "Deep Learning", "NLP", "SQL", "PyTorch", "TensorFlow"),
        degrees=("Master Data Science", "Doctorat en statistiques", "Diplôme d'ingénieur en data"),
        certifications=("TensorFlow Developer", "AWS Machine Learning Specialty", "Google Professional Data Engineer"),
        missions=(
            "Développer des modèles prédictifs et des prototypes",
            "Préparer les jeux de données et évaluer les modèles",
            "Industrialiser les expérimentations et documenter les résultats",
        ),
        projects=("Moteur de prédiction", "Classification de textes", "Détection d'anomalies"),
        languages=("Français", "Anglais"),
    ),
    "Machine Learning Engineer": Profile(
        target_job="Machine Learning Engineer",
        alternate_titles=("Ingénieur ML", "ML Engineer", "Ingénieur machine learning"),
        skills=("Python", "PyTorch", "TensorFlow", "scikit-learn", "MLOps", "Docker", "Kubernetes", "MLflow", "Git", "SQL", "REST API"),
        degrees=("Master intelligence artificielle", "Diplôme d'ingénieur en informatique", "Master data engineering"),
        certifications=("TensorFlow Developer", "Google Professional Machine Learning Engineer", "AWS Machine Learning Specialty"),
        missions=(
            "Concevoir des pipelines d'entraînement et de déploiement",
            "Mettre en production des modèles de machine learning",
            "Surveiller la dérive et automatiser le retraining",
        ),
        projects=("Pipeline MLOps", "Service de scoring", "Plateforme de déploiement"),
        languages=("Français", "Anglais"),
    ),
    "Ingénieur IA": Profile(
        target_job="Ingénieur IA",
        alternate_titles=("AI Engineer", "Ingénieur intelligence artificielle", "Ingénieur IA générative"),
        skills=("Python", "PyTorch", "TensorFlow", "NLP", "RAG", "LLM", "FastAPI", "MLOps", "Docker", "Git", "Prompt engineering"),
        degrees=("Master intelligence artificielle", "Diplôme d'ingénieur en informatique", "Master traitement du langage"),
        certifications=("Azure AI Engineer Associate", "AWS Machine Learning Specialty", "Google Professional Machine Learning Engineer"),
        missions=(
            "Concevoir des services IA et des chaînes RAG",
            "Industrialiser les modèles de langage et les évaluations",
            "Collaborer avec les équipes produit et métier pour les cas d'usage IA",
        ),
        projects=("Assistant IA", "Moteur RAG", "Outil d'évaluation LLM"),
        languages=("Français", "Anglais"),
    ),
    "Ingénieur DevOps": Profile(
        target_job="Ingénieur DevOps",
        alternate_titles=("DevOps Engineer", "Ingénieur plateforme", "Ingénieur cloud"),
        skills=("Linux", "Docker", "Kubernetes", "Git", "Terraform", "Ansible", "AWS", "Azure", "CI/CD", "Bash", "Monitoring"),
        degrees=("Diplôme d'ingénieur en informatique", "Master systèmes et réseaux", "Licence informatique"),
        certifications=("AWS Certified Solutions Architect", "CKA", "HashiCorp Terraform Associate"),
        missions=(
            "Automatiser l'infrastructure et les déploiements",
            "Mettre en place des pipelines CI/CD robustes",
            "Maintenir les environnements de production et le monitoring",
        ),
        projects=("Plateforme CI/CD", "Infrastructure as Code", "Cluster Kubernetes"),
        languages=("Français", "Anglais"),
    ),
    "Administrateur système": Profile(
        target_job="Administrateur système",
        alternate_titles=("Administrateur Linux", "Ingénieur systèmes", "Admin systèmes et réseaux"),
        skills=("Linux", "Bash", "Ansible", "VMware", "Monitoring", "Sauvegarde", "Réseaux", "Sécurité", "Git", "Stockage"),
        degrees=("BTS SIO", "Licence systèmes et réseaux", "Bac+2 informatique"),
        certifications=("Linux Foundation Certified System Administrator", "CCNA", "ITIL Foundation"),
        missions=(
            "Administrer les serveurs et les services d'infrastructure",
            "Superviser les sauvegardes, les droits et la disponibilité",
            "Automatiser les opérations récurrentes",
        ),
        projects=("Virtualisation serveurs", "Supervision système", "Plan de reprise"),
        languages=("Français", "Anglais"),
    ),
    "Chef de projet informatique": Profile(
        target_job="Chef de projet informatique",
        alternate_titles=("Project Manager IT", "Chef de projet digital", "Responsable de projet informatique"),
        skills=("Gestion de projet", "Agile", "Scrum", "Jira", "Confluence", "Planification", "Budget", "Risque", "Communication", "SQL"),
        degrees=("Master management de projet", "Diplôme d'ingénieur", "Master informatique"),
        certifications=("PMP", "Prince2", "Scrum Master"),
        missions=(
            "Piloter des projets informatiques de bout en bout",
            "Co-ordonner les équipes métier et technique",
            "Suivre les coûts, les délais et les livrables",
        ),
        projects=("Migration applicative", "Déploiement ERP", "Refonte portail métier"),
        languages=("Français", "Anglais"),
    ),
    "Consultant IA": Profile(
        target_job="Consultant IA",
        alternate_titles=("Consultant intelligence artificielle", "Conseil IA", "Consultant data & IA"),
        skills=("Python", "Machine Learning", "Deep Learning", "NLP", "RAG", "LLM", "MLOps", "Gestion de projet", "Ateliers", "SQL"),
        degrees=("Master intelligence artificielle", "Diplôme d'ingénieur", "Master data science"),
        certifications=("Azure AI Engineer Associate", "AWS Machine Learning Specialty", "Scrum Master"),
        missions=(
            "Cadrer les cas d'usage IA et accompagner les métiers",
            "Animer des ateliers de conception et de priorisation",
            "Aider à la mise en œuvre de solutions IA responsables",
        ),
        projects=("Diagnostic IA", "Atelier RAG", "Roadmap data & IA"),
        languages=("Français", "Anglais"),
    ),
    "Technicien audiovisuel": Profile(
        target_job="Technicien audiovisuel",
        alternate_titles=("Technicien AV", "Opérateur audiovisuel", "Technicien image et son"),
        skills=("Vidéo", "Sonorisation", "Éclairage scénique", "Réseaux", "FFmpeg", "MIDI", "OSC", "Câblage", "Régie", "Maintenance"),
        degrees=("BTS audiovisuel", "Bac pro systèmes numériques", "Titre professionnel audiovisuel"),
        certifications=("Habilitation électrique", "CACES", "Sécurité spectacle"),
        missions=(
            "Installer et maintenir les équipements audiovisuels",
            "Assurer les régies et les tests avant diffusion",
            "Résoudre les incidents techniques en événementiel",
        ),
        projects=("Captation multicam", "Installation de régie", "Diffusion hybride"),
        languages=("Français", "Anglais"),
    ),
    "Régisseur son": Profile(
        target_job="Régisseur son",
        alternate_titles=("Technicien son", "Ingénieur son live", "Régisseur audio"),
        skills=("Sonorisation", "OSC", "MIDI", "Dante", "Mixage", "Câblage", "Acoustique", "Régie", "Maintenance", "Réseaux"),
        degrees=("BTS audiovisuel", "Diplôme technique du spectacle", "Bac pro audiovisuel"),
        certifications=("Habilitation électrique", "Sécurité spectacle", "CACES"),
        missions=(
            "Préparer et exploiter les systèmes de diffusion son",
            "Effectuer les balances et le réglage des retours",
            "Garantir la qualité sonore en direct",
        ),
        projects=("Tournée live", "Festival musique", "Plateau TV"),
        languages=("Français", "Anglais"),
    ),
    "Régisseur lumière": Profile(
        target_job="Régisseur lumière",
        alternate_titles=("Technicien lumière", "Régisseur éclairage", "Opérateur lumière"),
        skills=("Éclairage scénique", "DMX", "ArtNet", "Console lumière", "Vidéo", "Réseaux", "Câblage", "Régie", "Maintenance", "Création lumière"),
        degrees=("BTS audiovisuel", "Diplôme technique du spectacle", "Bac pro audiovisuel"),
        certifications=("Sécurité spectacle", "Habilitation électrique", "CACES"),
        missions=(
            "Programmer et exploiter les jeux de lumière",
            "Assurer le patch et les réglages en régie",
            "Coordonner les essais avec la mise en scène",
        ),
        projects=("Spectacle vivant", "Tournée lumière", "Installation scénique"),
        languages=("Français", "Anglais"),
    ),
    "Régisseur vidéo": Profile(
        target_job="Régisseur vidéo",
        alternate_titles=("Technicien vidéo", "Opérateur vidéo", "Régisseur projection"),
        skills=("Vidéo", "FFmpeg", "OpenGL", "Réseaux", "Projection", "Mapping vidéo", "Capture", "Câblage", "Régie", "Streaming"),
        degrees=("BTS audiovisuel", "Diplôme technique du spectacle", "Licence audiovisuel"),
        certifications=("Sécurité spectacle", "Habilitation électrique", "CACES"),
        missions=(
            "Assurer la diffusion vidéo et la projection",
            "Piloter les flux et les équipements de régie",
            "Préparer les contenus vidéo et la synchronisation",
        ),
        projects=("Mapping de façade", "Diffusion événementielle", "Captation streaming"),
        languages=("Français", "Anglais"),
    ),
    "Ingénieur du son": Profile(
        target_job="Ingénieur du son",
        alternate_titles=("Ingénieur audio", "Sound Engineer", "Ingénieur sonore"),
        skills=("Sonorisation", "Acoustique", "Pro Tools", "MAO", "Mixage", "Enregistrement", "OSC", "MIDI", "Réseaux", "Maintenance"),
        degrees=("BTS audiovisuel", "Licence ingénierie du son", "Master audio"),
        certifications=("Sécurité spectacle", "Habilitation électrique", "CACES"),
        missions=(
            "Enregistrer et mixer des sources audio",
            "Préparer les sessions et les chaînes de traitement",
            "Optimiser la qualité sonore des productions",
        ),
        projects=("Enregistrement studio", "Mixage live", "Postproduction audio"),
        languages=("Français", "Anglais"),
    ),
    "Électronicien": Profile(
        target_job="Électronicien",
        alternate_titles=("Technicien électronique", "Ingénieur électronique", "Électronicien de maintenance"),
        skills=("Électronique", "Soudure", "Oscilloscope", "Microcontrôleurs", "Câblage", "PCB", "Diagnostic", "Instrumentation", "Réseaux", "Maintenance"),
        degrees=("BTS électronique", "DUT génie électrique", "Licence électronique"),
        certifications=("Habilitation électrique", "IPC-A-610", "CACES"),
        missions=(
            "Diagnostiquer les cartes et les sous-ensembles électroniques",
            "Réaliser le prototypage et la mise au point",
            "Assurer la maintenance préventive et corrective",
        ),
        projects=("Carte de contrôle", "Banc de test", "Prototype embarqué"),
        languages=("Français", "Anglais"),
    ),
    "Technicien réseau": Profile(
        target_job="Technicien réseau",
        alternate_titles=("Administrateur réseau", "Technicien infrastructure", "Technicien systèmes et réseaux"),
        skills=("Réseaux", "TCP/IP", "VLAN", "Cisco", "Linux", "Firewall", "Wi-Fi", "Fibre", "Monitoring", "Sécurité"),
        degrees=("BTS SIO", "Bac+2 réseaux", "Licence systèmes et réseaux"),
        certifications=("CCNA", "ITIL Foundation", "Linux Foundation Certified System Administrator"),
        missions=(
            "Installer et maintenir les infrastructures réseau",
            "Gérer les incidents de connectivité et de sécurité",
            "Documenter les configurations et les procédures",
        ),
        projects=("Déploiement Wi-Fi", "Migration réseau", "Supervision LAN/WAN"),
        languages=("Français", "Anglais"),
    ),
}


ROLE_ALIASES: dict[str, str] = {profile.target_job: key for key, profile in PROFILE_LIBRARY.items()}


def strip_accents(text: str) -> str:
    """Return the text without accents."""

    normalized = unicodedata.normalize("NFKD", text)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def maybe_drop_accents(text: str, rng: random.Random, probability: float) -> str:
    """Drop accents from a string with a configurable probability."""

    if probability <= 0:
        return text
    if rng.random() < probability:
        return strip_accents(text)
    return text


def random_case(text: str, rng: random.Random) -> str:
    """Apply a random casing strategy."""

    choice = rng.random()
    if choice < 0.2:
        return text.upper()
    if choice < 0.4:
        return text.lower()
    if choice < 0.6:
        return text.title()
    return text


def break_words(text: str, rng: random.Random, probability: float) -> str:
    """Insert artificial line breaks into words to mimic PDF extraction issues."""

    if probability <= 0:
        return text

    pieces: list[str] = []
    for token in re.split(r"(\s+)", text):
        if not token or token.isspace():
            pieces.append(token)
            continue
        if len(token) > 8 and rng.random() < probability:
            cut = rng.randint(3, len(token) - 3)
            pieces.append(token[:cut] + "-\n" + token[cut:])
            continue
        if len(token) > 4 and rng.random() < probability / 2:
            cut = rng.randint(2, len(token) - 2)
            pieces.append(token[:cut] + " " + token[cut:])
            continue
        pieces.append(token)
    return "".join(pieces)


def add_pdf_noise(text: str, rng: random.Random, level: int) -> str:
    """Return a noisy variant of the provided fragment."""

    if level <= 0 or not text:
        return text

    noisy = text
    accent_probability = {1: 0.05, 2: 0.15, 3: 0.3}[level]
    if rng.random() < {1: 0.15, 2: 0.3, 3: 0.45}[level]:
        noisy = random_case(noisy, rng)
    noisy = maybe_drop_accents(noisy, rng, accent_probability)
    if level >= 2:
        noisy = break_words(noisy, rng, {2: 0.08, 3: 0.22}[level])
    if level >= 3:
        if rng.random() < 0.5:
            noisy = noisy.replace(" - ", "\n- ")
        if rng.random() < 0.4:
            noisy = noisy.replace(" | ", "  |  ")
        if rng.random() < 0.35:
            noisy = noisy.replace(":", " : ")
        if rng.random() < 0.3:
            noisy = noisy.replace("\n", "\n\n")
    if level == 1 and rng.random() < 0.25:
        noisy = noisy.replace(" ", "  ", 1)
    return noisy


def _month_name(dt: date) -> str:
    return MONTHS_FR[dt.month - 1]


def format_date(dt: date, style: str) -> str:
    """Format a date using one of the supported textual styles."""

    if style == "numeric":
        return dt.strftime("%m/%Y")
    if style == "text":
        return f"{_month_name(dt)} {dt.year}"
    return str(dt.year)


def format_date_range(start: date, end: date, rng: random.Random) -> str:
    """Format a date range with a varied French notation."""

    style = rng.choice(DATE_STYLES)
    if style == "year_range":
        return f"{start.year} - {end.year}"
    if style == "numeric_range":
        return f"{start.strftime('%m/%Y')} - {end.strftime('%m/%Y')}"
    if style == "text_range":
        return f"{_month_name(start)} {start.year} à {_month_name(end)} {end.year}"
    if style == "since":
        return f"Depuis {_month_name(start)} {start.year}"
    if style == "today":
        return f"{start.year} – aujourd’hui"
    return f"{_month_name(start)} {start.year} / {_month_name(end)} {end.year}"


def format_duration(months: int, rng: random.Random) -> str:
    """Format a duration using a natural French expression."""

    years, remaining_months = divmod(months, 12)
    if years <= 0:
        return f"{max(1, remaining_months)} mois"
    if remaining_months == 0:
        return f"{years} an{'s' if years > 1 else ''}"
    if rng.random() < 0.5:
        return f"{years} an{'s' if years > 1 else ''} {remaining_months} mois"
    return f"{years} an{'s' if years > 1 else ''} d'expérience"


def build_date_entity_text(dt: date, rng: random.Random) -> str:
    """Return a textual date entity without introducing overlaps."""

    style = rng.choice(("numeric", "text", "year"))
    return format_date(dt, style)


def choose_experience_level(rng: random.Random) -> str:
    """Choose a coherent experience level."""

    return rng.choices(
        population=["junior", "intermediate", "senior", "lead"],
        weights=[0.2, 0.35, 0.3, 0.15],
        k=1,
    )[0]


def choose_title(profile: Profile, rng: random.Random) -> str:
    """Choose a job title from the profile."""

    pool = (profile.target_job,) + profile.alternate_titles
    return rng.choice(pool)


def choose_skills(profile: Profile, rng: random.Random, count: int) -> list[str]:
    """Choose a coherent set of skills without duplicates."""

    candidates = list(profile.skills)
    rng.shuffle(candidates)
    return candidates[: min(count, len(candidates))]


def choose_languages(profile: Profile, rng: random.Random) -> list[str]:
    """Choose one to three languages."""

    pool = list(dict.fromkeys(profile.languages + ("Français", "Anglais")))
    rng.shuffle(pool)
    return pool[: rng.randint(1, min(3, len(pool)))]


def choose_degrees(profile: Profile, rng: random.Random, count: int) -> list[str]:
    """Choose education entries."""

    candidates = list(profile.degrees)
    rng.shuffle(candidates)
    return candidates[: min(count, len(candidates))]


def choose_certs(profile: Profile, rng: random.Random, count: int) -> list[str]:
    """Choose certifications."""

    candidates = list(profile.certifications)
    rng.shuffle(candidates)
    return candidates[: min(count, len(candidates))]


def choose_projects(profile: Profile, rng: random.Random, count: int) -> list[str]:
    """Choose project names."""

    candidates = list(profile.projects)
    rng.shuffle(candidates)
    return candidates[: min(count, len(candidates))]


def choose_missions(profile: Profile, rng: random.Random, count: int) -> list[str]:
    """Choose mission descriptions."""

    candidates = list(profile.missions)
    rng.shuffle(candidates)
    return candidates[: min(count, len(candidates))]


def build_summary(profile: Profile, rng: random.Random, target_job: str, level: str) -> str:
    """Build a short professional summary."""

    mission = rng.choice(profile.missions)
    if level == "junior":
        opener = "Jeune profil motivé"
    elif level == "intermediate":
        opener = "Professionnel polyvalent"
    elif level == "senior":
        opener = "Profil confirmé"
    else:
        opener = "Référent technique"
    return f"{opener} {target_job.lower()} avec un focus sur {mission.lower()}."


def build_experiences(
    builder: AnnotatedTextBuilder,
    profile: Profile,
    rng: random.Random,
    fake: SyntheticDataProvider,
    target_job: str,
    level: str,
    noise_level: int,
) -> None:
    """Append an experience section."""

    section_title = rng.choice(SECTION_VARIANTS["experience"])
    append_header(builder, section_title, rng, noise_level)

    years_min, years_max = EXPERIENCE_LEVEL_RANGES[level]
    total_years = rng.randint(max(1, years_min + 1), max(years_min + 1, years_max))
    experience_count = rng.randint(1, 4 if level != "junior" else 2)
    remaining_months = max(12, total_years * 12)
    end_date = date(2026, rng.randint(1, 12), rng.randint(1, 28))

    for index in range(experience_count):
        if index > 0:
            builder.newline()

        duration_months = max(6, remaining_months // max(1, experience_count - index) + rng.randint(-6, 6))
        duration_months = max(6, min(duration_months, remaining_months))
        start_date = end_date - timedelta(days=duration_months * 30)
        title = choose_title(profile, rng)
        company = fake.company()
        if index == 0:
            title = target_job if rng.random() < 0.7 else title

        date_text = format_date_range(start_date, end_date, rng)
        duration_text = format_duration(duration_months, rng)

        builder.append_entity(add_pdf_noise(date_text, rng, noise_level), "DATE")
        builder.append("  |  ")
        builder.append_entity(add_pdf_noise(duration_text, rng, noise_level), "EXPERIENCE_DURATION")
        builder.newline()
        builder.append_entity(add_pdf_noise(title, rng, noise_level), "JOB_TITLE")
        builder.newline()
        builder.append_entity(add_pdf_noise(company, rng, noise_level), "COMPANY")
        builder.newline()

        missions = choose_missions(profile, rng, rng.randint(1, 3))
        for mission in missions:
            bullet = rng.choice(("•", "-", "–", "▪"))
            line = f"{bullet} {mission}"
            builder.append(add_pdf_noise(line, rng, noise_level))
            builder.newline()

        skill_sample = choose_skills(profile, rng, rng.randint(3, min(6, len(profile.skills))))
        skill_line = "Technologies: " + ", ".join(skill_sample)
        builder.append(add_pdf_noise(skill_line, rng, noise_level))
        builder.newline()

        end_date = start_date - timedelta(days=rng.randint(90, 360))
        remaining_months = max(6, remaining_months - duration_months)


def build_education(
    builder: AnnotatedTextBuilder,
    profile: Profile,
    rng: random.Random,
    fake: SyntheticDataProvider,
    noise_level: int,
) -> None:
    """Append an education section."""

    builder.newline()
    append_header(builder, rng.choice(SECTION_VARIANTS["education"]), rng, noise_level)

    degrees = choose_degrees(profile, rng, rng.randint(1, 3))
    for degree in degrees:
        if rng.random() < 0.4:
            builder.append_entity(add_pdf_noise(f"202{rng.randint(0, 4)} - 202{rng.randint(4, 6)}", rng, noise_level), "DATE")
            builder.newline()
        builder.append_entity(add_pdf_noise(degree, rng, noise_level), "DEGREE")
        builder.newline()
        school = f"{fake.city()} Institut {fake.company_suffix()}"
        builder.append_entity(add_pdf_noise(school, rng, noise_level), "SCHOOL")
        builder.newline()
        if rng.random() < 0.6:
            builder.append(add_pdf_noise(f"Spécialité: {rng.choice(profile.skills[: min(5, len(profile.skills))])}", rng, noise_level))
            builder.newline()
        builder.newline()


def build_skills(
    builder: AnnotatedTextBuilder,
    profile: Profile,
    rng: random.Random,
    noise_level: int,
) -> None:
    """Append a skills section."""

    builder.newline()
    append_header(builder, rng.choice(SECTION_VARIANTS["skills"]), rng, noise_level)
    skills = choose_skills(profile, rng, rng.randint(6, min(10, len(profile.skills))))
    separator = rng.choice((" | ", " • ", " / ", ", "))
    skill_line = separator.join(skills)
    position = 0
    for index, skill in enumerate(skills):
        if index > 0:
            builder.append(separator)
        builder.append_entity(add_pdf_noise(skill, rng, noise_level), "SKILL")
        position += 1
    if not skills:
        builder.append(add_pdf_noise("Aucune compétence renseignée", rng, noise_level))
    builder.newline()


def build_languages(
    builder: AnnotatedTextBuilder,
    profile: Profile,
    rng: random.Random,
    noise_level: int,
) -> None:
    """Append a languages section."""

    if rng.random() < 0.35:
        return
    builder.newline()
    append_header(builder, rng.choice(SECTION_VARIANTS["languages"]), rng, noise_level)
    languages = choose_languages(profile, rng)
    for language in languages:
        proficiency = rng.choice(LANGUAGE_LEVELS)
        builder.append_entity(add_pdf_noise(language, rng, noise_level), "LANGUAGE")
        builder.append(add_pdf_noise(f" : {proficiency}", rng, noise_level))
        builder.newline()


def build_certifications(
    builder: AnnotatedTextBuilder,
    profile: Profile,
    rng: random.Random,
    noise_level: int,
) -> None:
    """Append a certifications section."""

    if rng.random() < 0.3:
        return
    builder.newline()
    append_header(builder, rng.choice(SECTION_VARIANTS["certifications"]), rng, noise_level)
    certs = choose_certs(profile, rng, rng.randint(1, 3))
    for cert in certs:
        builder.append_entity(add_pdf_noise(cert, rng, noise_level), "CERTIFICATION")
        builder.newline()


def build_projects(
    builder: AnnotatedTextBuilder,
    profile: Profile,
    rng: random.Random,
    noise_level: int,
) -> None:
    """Append a projects section."""

    if rng.random() < 0.25:
        return
    builder.newline()
    append_header(builder, rng.choice(SECTION_VARIANTS["projects"]), rng, noise_level)
    projects = choose_projects(profile, rng, rng.randint(1, 3))
    for project in projects:
        builder.append_entity(add_pdf_noise(project, rng, noise_level), "PROJECT")
        builder.append(add_pdf_noise(f" - {rng.choice(profile.missions).lower()}", rng, noise_level))
        builder.newline()


def build_contact_section(
    builder: AnnotatedTextBuilder,
    fake: SyntheticDataProvider,
    name: str,
    rng: random.Random,
    noise_level: int,
) -> dict[str, str]:
    """Build the contact block and return generated values."""

    email = fake.email(name)
    phone = fake.phone_number()
    address = fake.street_address()
    postal_code = fake.postalcode()
    city = fake.city()
    website = fake.website(name)
    linkedin = fake.linkedin(name)
    github = fake.github(name)

    append_header(builder, rng.choice(SECTION_VARIANTS["contact"]), rng, noise_level)
    builder.append_entity(add_pdf_noise(address, rng, noise_level), "ADDRESS")
    builder.newline()
    builder.append_entity(add_pdf_noise(postal_code, rng, noise_level), "POSTAL_CODE")
    builder.append(" ")
    builder.append_entity(add_pdf_noise(city, rng, noise_level), "CITY")
    builder.newline()
    builder.append_entity(add_pdf_noise(email, rng, noise_level), "EMAIL")
    builder.newline()
    builder.append_entity(add_pdf_noise(phone, rng, noise_level), "PHONE")
    builder.newline()
    builder.append_entity(add_pdf_noise(website, rng, noise_level), "WEBSITE")
    builder.newline()
    builder.append_entity(add_pdf_noise(linkedin, rng, noise_level), "LINKEDIN")
    builder.newline()
    builder.append_entity(add_pdf_noise(github, rng, noise_level), "GITHUB")
    builder.newline()
    builder.append_entity(add_pdf_noise("Permis B", rng, noise_level), "DRIVING_LICENSE")
    builder.newline()

    return {
        "email": email,
        "phone": phone,
        "address": address,
        "postal_code": postal_code,
        "city": city,
        "website": website,
        "linkedin": linkedin,
        "github": github,
    }


def append_header(builder: AnnotatedTextBuilder, title: str, rng: random.Random, noise_level: int) -> None:
    """Append a section header as an annotated fragment."""

    builder.append_entity(add_pdf_noise(title, rng, noise_level), "SECTION_HEADER")
    builder.newline()


def section_order_for_template(template: str) -> list[str]:
    """Return the base section order for a template."""

    if template == "academic":
        return ["education", "experience", "skills", "certifications", "languages", "projects"]
    if template == "technical":
        return ["experience", "skills", "projects", "certifications", "languages", "education"]
    if template == "compact":
        return ["contact", "experience", "skills", "education", "languages"]
    if template == "creative":
        return ["summary", "contact", "projects", "experience", "skills", "certifications", "education", "languages"]
    if template == "minimal":
        return ["contact", "experience", "education", "skills"]
    if template == "noisy_pdf":
        return ["contact", "experience", "skills", "education", "projects", "certifications", "languages"]
    return ["summary", "contact", "experience", "education", "skills", "projects", "certifications", "languages"]


def shuffled_templates(seed: int, count: int) -> list[str]:
    """Return a deterministic template sequence that covers every template."""

    rng = random.Random(seed)
    order: list[str] = []
    template_pool = list(TEMPLATES)
    while len(order) < count:
        batch = template_pool[:]
        rng.shuffle(batch)
        order.extend(batch)
    return order[:count]


def select_profile(seed: int, rng: random.Random) -> tuple[str, Profile]:
    """Select a profile deterministically from the library."""

    keys = list(PROFILE_LIBRARY)
    rng.shuffle(keys)
    index = seed % len(keys)
    key = keys[index]
    return key, PROFILE_LIBRARY[key]


def build_cv_record(
    index: int,
    seed: int,
    template: str,
    noise_level: int,
) -> dict[str, Any]:
    """Generate a single synthetic CV record."""

    record_seed = seed * 1009 + index * 37
    rng = random.Random(record_seed)
    fake = SyntheticDataProvider(record_seed)
    profile_key, profile = select_profile(record_seed, rng)
    level = choose_experience_level(rng)
    target_job = choose_title(profile, rng)
    candidate_name = fake.name()

    builder = AnnotatedTextBuilder()
    builder.append_entity(add_pdf_noise(candidate_name, rng, noise_level), "NAME")
    builder.newline()
    builder.append_entity(add_pdf_noise(target_job, rng, noise_level), "JOB_TITLE")
    builder.newline()
    summary = build_summary(profile, rng, target_job, level)
    if template in {"classic", "academic", "creative", "technical", "noisy_pdf"} and rng.random() < 0.95:
        append_header(builder, rng.choice(SECTION_VARIANTS["summary"]), rng, noise_level)
        builder.append(add_pdf_noise(summary, rng, noise_level))
        builder.newline()

    build_contact_section(builder, fake, candidate_name, rng, noise_level)

    order = section_order_for_template(template)
    for section in order:
        if section == "contact":
            continue
        if section == "summary":
            continue
        if section == "experience":
            build_experiences(builder, profile, rng, fake, target_job, level, noise_level if template == "noisy_pdf" else min(noise_level, 2))
        elif section == "education":
            build_education(builder, profile, rng, fake, noise_level if template == "noisy_pdf" else min(noise_level, 2))
        elif section == "skills":
            build_skills(builder, profile, rng, noise_level if template == "noisy_pdf" else min(noise_level, 2))
        elif section == "languages":
            build_languages(builder, profile, rng, noise_level if template == "noisy_pdf" else min(noise_level, 2))
        elif section == "certifications":
            build_certifications(builder, profile, rng, noise_level if template == "noisy_pdf" else min(noise_level, 2))
        elif section == "projects":
            build_projects(builder, profile, rng, noise_level if template == "noisy_pdf" else min(noise_level, 2))

    text, entities = builder.build()
    return build_record_from_text(text, entities, index, template, profile_key, target_job, level)


def build_record_from_text(
    text: str,
    entities: list[dict[str, Any]],
    index: int,
    template: str,
    profile_key: str,
    target_job: str,
    experience_level: str,
) -> dict[str, Any]:
    """Assemble a serializable record."""

    return {
        "id": f"cv_{index + 1:06d}",
        "text": text,
        "entities": entities,
        "metadata": {
            "synthetic": True,
            "template": template,
            "target_job": target_job,
            "experience_level": experience_level,
            "language": "fr",
            "profile_key": profile_key,
        },
    }


def build_dataset(count: int, seed: int, noise_level: int) -> list[dict[str, Any]]:
    """Build a full synthetic dataset in memory."""

    templates = shuffled_templates(seed, count)
    return [build_cv_record(index, seed, templates[index], noise_level) for index in range(count)]


def split_records(
    records: list[dict[str, Any]],
    seed: int,
    train_ratio: float,
    validation_ratio: float,
    test_ratio: float,
) -> dict[str, list[dict[str, Any]]]:
    """Split records by CV, not by entity."""

    total = len(records)
    indices = list(range(total))
    random.Random(seed).shuffle(indices)

    train_count = int(total * train_ratio)
    validation_count = int(total * validation_ratio)
    assigned = train_count + validation_count
    test_count = total - assigned

    split_indices = {
        "train": indices[:train_count],
        "validation": indices[train_count : train_count + validation_count],
        "test": indices[train_count + validation_count : train_count + validation_count + test_count],
    }
    return {
        split_name: [records[index] for index in split_indices[split_name]]
        for split_name in ("train", "validation", "test")
    }


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """Yield JSON objects from a JSONL file."""

    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            yield json.loads(line)


def write_jsonl(records: Iterable[dict[str, Any]], path: Path) -> None:
    """Write JSONL records with UTF-8 and ensure_ascii=False."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False))
            handle.write("\n")


TOKEN_PATTERN = re.compile(r"\S+")


def tokenize_with_spans(text: str) -> list[tuple[str, int, int]]:
    """Tokenize a string using a simple whitespace strategy."""

    return [(match.group(0), match.start(), match.end()) for match in TOKEN_PATTERN.finditer(text)]


def entities_to_spacy_entities(entities: list[dict[str, Any]]) -> list[list[int | str]]:
    """Convert entities to spaCy-compatible offsets."""

    return [[entity["start"], entity["end"], entity["label"]] for entity in entities]


def convert_record_to_spacy(record: dict[str, Any]) -> dict[str, Any]:
    """Convert a record to spaCy JSONL format."""

    return {
        "text": record["text"],
        "entities": entities_to_spacy_entities(record["entities"]),
    }


def build_hf_tags(tokens: list[tuple[str, int, int]], entities: list[dict[str, Any]]) -> list[str]:
    """Build BIO tags from token spans and entity offsets."""

    tags = ["O"] * len(tokens)
    sorted_entities = sorted(entities, key=lambda entity: (entity["start"], entity["end"]))
    for entity in sorted_entities:
        start = entity["start"]
        end = entity["end"]
        label = entity["label"]
        token_indexes = [index for index, (_, token_start, token_end) in enumerate(tokens) if token_start < end and token_end > start]
        if not token_indexes:
            continue
        tags[token_indexes[0]] = f"B-{label}"
        for index in token_indexes[1:]:
            tags[index] = f"I-{label}"
    return tags


def convert_record_to_huggingface(record: dict[str, Any]) -> dict[str, Any]:
    """Convert a record to a simple token/BIO format."""

    tokens_with_spans = tokenize_with_spans(record["text"])
    tokens = [token for token, _, _ in tokens_with_spans]
    ner_tags = build_hf_tags(tokens_with_spans, record["entities"])
    return {
        "id": record["id"],
        "tokens": tokens,
        "ner_tags": ner_tags,
    }


def export_records(records: list[dict[str, Any]], path: Path, output_format: str) -> None:
    """Export records to the requested JSONL format."""

    if output_format == "jsonl":
        write_jsonl(records, path)
        return
    if output_format == "spacy":
        write_jsonl((convert_record_to_spacy(record) for record in records), path)
        return
    if output_format == "huggingface":
        write_jsonl((convert_record_to_huggingface(record) for record in records), path)
        return
    raise ValueError(f"Format de sortie non pris en charge: {output_format}")


@dataclass
class ValidationReport:
    """Validation summary for a dataset."""

    analyzed: int
    valid: int
    invalid: int
    total_entities: int
    label_counts: dict[str, int]
    template_counts: dict[str, int]
    average_entities: float
    errors: list[str]
    cv_with_name_and_contact: int

    @property
    def has_errors(self) -> bool:
        """Return whether validation failed."""

        return self.invalid > 0 or bool(self.errors)


def validate_record(
    record: dict[str, Any],
    known_ids: set[str],
    allowed_labels: set[str],
) -> tuple[bool, list[str], int, bool]:
    """Validate a single record and return its status."""

    errors: list[str] = []
    record_id = record.get("id")
    text = record.get("text")
    entities = record.get("entities")

    if not isinstance(record_id, str) or not record_id:
        errors.append("Identifiant manquant ou invalide.")
    elif record_id in known_ids:
        errors.append(f"Identifiant dupliqué: {record_id}")
    else:
        known_ids.add(record_id)

    if not isinstance(text, str) or not text:
        errors.append("Texte manquant ou vide.")
        text = ""

    if not isinstance(entities, list):
        errors.append("La liste entities est absente ou invalide.")
        entities = []

    parsed_entities: list[tuple[int, int, str, str]] = []
    seen_exact: set[tuple[int, int, str, str]] = set()

    for entity in entities:
        if not isinstance(entity, dict):
            errors.append("Une entité n'est pas un objet JSON valide.")
            continue
        start = entity.get("start")
        end = entity.get("end")
        label = entity.get("label")
        entity_text = entity.get("text")

        if not isinstance(start, int) or not isinstance(end, int):
            errors.append("Les offsets start/end doivent être des entiers.")
            continue
        if start < 0:
            errors.append("Un offset start est négatif.")
        if end > len(text):
            errors.append("Un offset end dépasse la longueur du texte.")
        if start >= end:
            errors.append("Un offset est vide ou inversé.")
        if not isinstance(label, str) or label not in allowed_labels:
            errors.append(f"Label interdit ou manquant: {label}")
        if not isinstance(entity_text, str) or not entity_text:
            errors.append("Une entité est vide.")
        elif 0 <= start < end <= len(text) and text[start:end] != entity_text:
            errors.append(
                f"Correspondance texte/offets invalide pour {label}: '{text[start:end]}' != '{entity_text}'"
            )

        current = (start, end, str(label), str(entity_text))
        if current in seen_exact:
            errors.append(f"Doublon exact d'entité: {current}")
        seen_exact.add(current)
        parsed_entities.append((start, end, str(label), str(entity_text)))

    parsed_entities.sort(key=lambda item: (item[0], item[1]))
    previous_end = -1
    for start, end, label, entity_text in parsed_entities:
        if start < previous_end:
            errors.append("Chevauchement entre entités.")
            break
        previous_end = end

    has_name = any(label == "NAME" for _, _, label, _ in parsed_entities)
    has_contact = any(label in CONTACT_LABELS for _, _, label, _ in parsed_entities)
    is_valid = not errors
    return is_valid, errors, len(parsed_entities), has_name and has_contact


def validate_dataset(records: list[dict[str, Any]], allowed_labels: set[str] | None = None) -> ValidationReport:
    """Validate an entire dataset."""

    if allowed_labels is None:
        allowed_labels = set(LABELS)

    known_ids: set[str] = set()
    errors: list[str] = []
    label_counts: dict[str, int] = {}
    template_counts: dict[str, int] = {}
    total_entities = 0
    valid = 0
    invalid = 0
    name_and_contact_count = 0

    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            invalid += 1
            errors.append(f"CV #{index}: l'entrée n'est pas un objet JSON.")
            continue

        template = record.get("metadata", {}).get("template") if isinstance(record.get("metadata"), dict) else None
        if isinstance(template, str):
            template_counts[template] = template_counts.get(template, 0) + 1

        is_valid, record_errors, entity_count, has_name_and_contact = validate_record(record, known_ids, allowed_labels)
        total_entities += entity_count
        if has_name_and_contact:
            name_and_contact_count += 1
        for entity in record.get("entities", []) if isinstance(record.get("entities"), list) else []:
            if isinstance(entity, dict):
                label = entity.get("label")
                if isinstance(label, str) and label in allowed_labels:
                    label_counts[label] = label_counts.get(label, 0) + 1
        if is_valid:
            valid += 1
        else:
            invalid += 1
            errors.extend([f"CV #{index}: {message}" for message in record_errors])

    analyzed = len(records)
    average_entities = total_entities / analyzed if analyzed else 0.0
    if analyzed > 0 and name_and_contact_count <= analyzed / 2:
        errors.append(
            "Moins de la moitié des CV contiennent à la fois un NAME et un moyen de contact."
        )

    return ValidationReport(
        analyzed=analyzed,
        valid=valid,
        invalid=invalid,
        total_entities=total_entities,
        label_counts=dict(sorted(label_counts.items())),
        template_counts=dict(sorted(template_counts.items())),
        average_entities=average_entities,
        errors=errors,
        cv_with_name_and_contact=name_and_contact_count,
    )


def print_validation_report(report: ValidationReport) -> None:
    """Print a human-readable validation report in French."""

    print(f"CV analysés: {report.analyzed}")
    print(f"CV valides: {report.valid}")
    print(f"CV invalides: {report.invalid}")
    print(f"Nombre total d'entités: {report.total_entities}")
    print("Répartition par label:")
    if report.label_counts:
        for label, count in report.label_counts.items():
            print(f"- {label}: {count}")
    else:
        print("- Aucune entité")
    print("Répartition par template:")
    if report.template_counts:
        for template, count in report.template_counts.items():
            print(f"- {template}: {count}")
    else:
        print("- Aucun template")
    print(f"Nombre moyen d'entités par CV: {report.average_entities:.2f}")
    print("Erreurs rencontrées:")
    if report.errors:
        for error in report.errors:
            print(f"- {error}")
    else:
        print("- Aucune")

