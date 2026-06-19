# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""Synthetic CV dataset generator for local NER training.

The generator emits fully synthetic French CVs with exact character-level
annotations. It supports JSONL, spaCy-style JSONL, and a simple BIO export.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from faker import Faker

ALLOWED_LABELS = [
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
]

CONTACT_LABELS = {"EMAIL", "PHONE", "WEBSITE", "LINKEDIN", "GITHUB"}
DEFAULT_OUTPUT = Path("data/cv/synthetic_cv_dataset.jsonl")
TEMPLATE_NAMES = ("classic", "compact", "technical", "academic", "creative", "minimal", "noisy_pdf")
LANGUAGES = ("Français", "Anglais", "Espagnol", "Allemand", "Italien")
DRIVING_LICENSES = ("Permis B", "Permis B + véhicule", "Permis A/B", "Permis C")
SECTION_TITLES = {
    "identity": ["COORDONNÉES", "Coordonnées", "Profil", "Résumé"],
    "experience": [
        "EXPÉRIENCES PROFESSIONNELLES",
        "EXPÉRIENCE",
        "PARCOURS PROFESSIONNEL",
        "MISSIONS",
    ],
    "education": ["FORMATION", "DIPLÔMES", "ÉTUDES"],
    "skills": ["COMPÉTENCES", "COMPÉTENCES TECHNIQUES", "TECHNOLOGIES", "OUTILS"],
    "languages": ["LANGUES"],
    "certifications": ["CERTIFICATIONS"],
    "projects": ["PROJETS"],
    "links": ["LIENS", "PROFILS EN LIGNE"],
    "misc": ["INFORMATIONS COMPLÉMENTAIRES"],
}


def _ascii_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()


def _slugify(value: str) -> str:
    key = _ascii_key(value)
    key = re.sub(r"[^a-z0-9]+", ".", key)
    return re.sub(r"\.+", ".", key).strip(".")


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _title_case(value: str) -> str:
    return " ".join(part[:1].upper() + part[1:].lower() if part else part for part in value.split())


@dataclass(frozen=True)
class EntitySpan:
    start: int
    end: int
    label: str
    text: str

    def as_dict(self) -> dict[str, Any]:
        return {"start": self.start, "end": self.end, "label": self.label, "text": self.text}


@dataclass
class AnnotatedTextBuilder:
    """Incrementally build a text with exact entity offsets."""

    parts: list[str] = field(default_factory=list)
    entities: list[EntitySpan] = field(default_factory=list)
    _length: int = 0

    @property
    def length(self) -> int:
        return self._length

    def append(self, text: str) -> None:
        if not text:
            return
        self.parts.append(text)
        self._length += len(text)

    def append_entity(self, text: str, label: str) -> EntitySpan:
        if not text:
            raise ValueError("Impossible d'annoter un texte vide.")
        if label not in ALLOWED_LABELS:
            raise ValueError(f"Label interdit: {label}")
        start = self._length
        self.append(text)
        entity = EntitySpan(start=start, end=self._length, label=label, text=text)
        self.entities.append(entity)
        return entity

    def newline(self, count: int = 1) -> None:
        self.append("\n" * max(count, 0))

    def space(self, count: int = 1) -> None:
        self.append(" " * max(count, 0))

    def build(self) -> tuple[str, list[dict[str, Any]]]:
        return "".join(self.parts), [entity.as_dict() for entity in self.entities]


@dataclass(frozen=True)
class JobProfileSpec:
    name: str
    aliases: tuple[str, ...]
    skills: tuple[str, ...]
    degrees: tuple[str, ...]
    certifications: tuple[str, ...]
    missions: tuple[str, ...]
    projects: tuple[str, ...]
    colors: tuple[str, ...] = ("bleu", "vert", "orange")
    level_weights: tuple[tuple[str, int], ...] = (("junior", 2), ("intermediate", 3), ("senior", 5))


@dataclass(frozen=True)
class TemplateSpec:
    name: str
    section_orders: tuple[tuple[str, ...], ...]
    minimum_noise: int = 0
    compact: bool = False
    allow_missing_sections: tuple[str, ...] = ()


JOB_PROFILES: dict[str, JobProfileSpec] = {
    "Développeur Python": JobProfileSpec(
        name="Développeur Python",
        aliases=("Développeur Python", "Python Developer", "Software Engineer Python", "Ingénieur Python"),
        skills=("Python", "Flask", "FastAPI", "Django", "Pandas", "NumPy", "SQL", "PostgreSQL", "PyTorch", "scikit-learn", "Git", "Docker"),
        degrees=("Master Informatique", "Diplôme d'ingénieur informatique", "BUT Informatique"),
        certifications=("PCAP", "AWS Certified Cloud Practitioner", "TensorFlow Developer Certificate"),
        missions=(
            "Concevoir des API REST et industrialiser des traitements de données.",
            "Maintenir des services Python testés et déployés en conteneurs.",
            "Mettre en place des pipelines de données et des scripts d'automatisation.",
        ),
        projects=(
            "Moteur de recommandation de formations",
            "API d'extraction documentaire",
            "Pipeline de scoring d'offres",
        ),
    ),
    "Développeur PHP Symfony": JobProfileSpec(
        name="Développeur PHP Symfony",
        aliases=("Développeur PHP Symfony", "PHP Symfony Developer", "Développeur back-end PHP"),
        skills=("PHP", "Symfony", "Doctrine", "MySQL", "Twig", "REST API", "Git", "Docker", "JavaScript", "Bootstrap"),
        degrees=("BUT Informatique", "Licence professionnelle développement web", "Master développement logiciel"),
        certifications=("Symfony Certification", "Zend Certified PHP Engineer", "Scrum Master"),
        missions=(
            "Développer des applications web métier et maintenir les intégrations API.",
            "Optimiser les performances de consultation et les modèles de données.",
            "Mettre en place des tests fonctionnels et de la CI/CD.",
        ),
        projects=("Portail métier Symfony", "Back-office e-commerce", "API de synchronisation",),
    ),
    "Développeur C++ Qt": JobProfileSpec(
        name="Développeur C++ Qt",
        aliases=("Développeur C++ Qt", "C++ Qt Developer", "Ingénieur logiciel C++"),
        skills=("C++", "Qt", "CMake", "Git", "Linux", "OpenGL", "Multithreading", "UDP", "TCP/IP", "Architecture logicielle"),
        degrees=("Diplôme d'ingénieur logiciel", "Master systèmes embarqués", "Licence informatique"),
        certifications=("C++ Institute CPP", "Qt Certification", "Linux Foundation Certified Associate"),
        missions=("Développer des logiciels embarqués ou desktop en C++.", "Concevoir des interfaces Qt performantes.", "Industrialiser la compilation et les tests."),
        projects=("Console de supervision Qt", "Outil de visualisation 3D", "Application de contrôle embarqué"),
    ),
    "Développeur full-stack": JobProfileSpec(
        name="Développeur full-stack",
        aliases=("Développeur full-stack", "Full Stack Developer", "Développeur web full-stack"),
        skills=("JavaScript", "TypeScript", "React", "Vue.js", "Node.js", "FastAPI", "Flask", "REST API", "Docker", "Git", "SQL"),
        degrees=("Master informatique", "BUT Informatique", "Licence web et mobile"),
        certifications=("AWS Certified Cloud Practitioner", "Scrum Master", "Azure Fundamentals"),
        missions=("Développer des interfaces web et des services back-end.", "Sécuriser les échanges et les déploiements.", "Travailler sur des produits web de bout en bout."),
        projects=("Plateforme SaaS de réservation", "Tableau de bord analytique", "Application collaborative temps réel"),
    ),
    "Data Analyst": JobProfileSpec(
        name="Data Analyst",
        aliases=("Data Analyst", "Analyste données", "Business Analyst Data"),
        skills=("SQL", "PostgreSQL", "Pandas", "NumPy", "Excel", "Power BI", "Tableau", "Python", "Statistiques", "DataViz"),
        degrees=("Master data", "Licence statistiques", "BUT informatique décisionnelle"),
        certifications=("Microsoft Power BI Data Analyst", "Google Data Analytics", "AWS Certified Cloud Practitioner"),
        missions=("Analyser des indicateurs métier et automatiser des reportings.", "Structurer des tableaux de bord décisionnels.", "Fiabiliser la qualité et la lisibilité des données."),
        projects=("Dashboard de pilotage", "Segmentation client", "Suivi des performances commerciales"),
    ),
    "Data Scientist": JobProfileSpec(
        name="Data Scientist",
        aliases=("Data Scientist", "Scientifique des données", "Machine Learning Scientist"),
        skills=("Python", "scikit-learn", "Pandas", "NumPy", "SQL", "Machine Learning", "Statistiques", "Jupyter", "Matplotlib", "XGBoost"),
        degrees=("Master data science", "Diplôme d'ingénieur informatique", "Doctorat en mathématiques appliquées"),
        certifications=("TensorFlow Developer Certificate", "AWS Machine Learning Specialty", "Google Professional Machine Learning Engineer"),
        missions=("Concevoir des modèles prédictifs et évaluer leur robustesse.", "Préparer les données et communiquer les résultats.", "Industrialiser des expérimentations reproductibles."),
        projects=("Score de churn", "Prévision de demande", "Détection d'anomalies"),
    ),
    "Machine Learning Engineer": JobProfileSpec(
        name="Machine Learning Engineer",
        aliases=("Machine Learning Engineer", "ML Engineer", "Ingénieur machine learning"),
        skills=("Python", "PyTorch", "TensorFlow", "MLOps", "Docker", "Kubernetes", "MLflow", "scikit-learn", "CI/CD", "API REST"),
        degrees=("Diplôme d'ingénieur", "Master intelligence artificielle", "Master informatique"),
        certifications=("AWS Machine Learning Specialty", "Google Professional ML Engineer", "TensorFlow Developer Certificate"),
        missions=("Déployer des modèles de machine learning en production.", "Automatiser l'entraînement et la surveillance des modèles.", "Mettre en place des pipelines MLOps robustes."),
        projects=("Plateforme MLOps", "Service de scoring temps réel", "Chaîne d'entraînement distribuée"),
    ),
    "Ingénieur IA": JobProfileSpec(
        name="Ingénieur IA",
        aliases=("Ingénieur IA", "AI Engineer", "Ingénieur intelligence artificielle"),
        skills=("Python", "PyTorch", "Transformers", "NLP", "RAG", "LLM", "Vector search", "FastAPI", "Docker", "Git"),
        degrees=("Master intelligence artificielle", "Diplôme d'ingénieur", "Doctorat en IA"),
        certifications=("Hugging Face Course", "AWS Machine Learning Specialty", "Azure AI Engineer Associate"),
        missions=("Créer des solutions IA pour des usages métier précis.", "Structurer des systèmes de récupération et génération augmentée.", "Évaluer et sécuriser les modèles génératifs."),
        projects=("Assistant documentaire RAG", "Classifieur d'intentions", "Prototype de copilote métier"),
    ),
    "Ingénieur DevOps": JobProfileSpec(
        name="Ingénieur DevOps",
        aliases=("Ingénieur DevOps", "DevOps Engineer", "Cloud Engineer"),
        skills=("Linux", "Docker", "Kubernetes", "Terraform", "Ansible", "AWS", "Azure", "Git", "CI/CD", "Observabilité"),
        degrees=("Diplôme d'ingénieur informatique", "Master systèmes distribués", "Licence réseaux et systèmes"),
        certifications=("CKA", "AWS Solutions Architect Associate", "HashiCorp Terraform Associate"),
        missions=("Automatiser les déploiements et renforcer l'infrastructure.", "Gérer les environnements cloud et la supervision.", "Améliorer la fiabilité des services en production."),
        projects=("Plateforme CI/CD", "Infrastructure as Code", "Cluster Kubernetes multi-environnements"),
    ),
    "Administrateur système": JobProfileSpec(
        name="Administrateur système",
        aliases=("Administrateur système", "Admin Sys", "System Administrator"),
        skills=("Linux", "Bash", "Samba", "Active Directory", "VMware", "Sauvegarde", "Supervision", "Réseaux", "Git", "Ansible"),
        degrees=("BTS SIO", "DUT réseaux et télécoms", "Licence systèmes et réseaux"),
        certifications=("Linux Foundation Certified Associate", "Microsoft Windows Server", "Cisco CCNA"),
        missions=("Administrer les serveurs, comptes et sauvegardes.", "Résoudre les incidents de production et documenter les procédures.", "Maintenir les politiques de sécurité et les mises à jour."),
        projects=("Migration serveurs", "Plan de sauvegarde", "Plateforme de supervision"),
    ),
    "Chef de projet informatique": JobProfileSpec(
        name="Chef de projet informatique",
        aliases=("Chef de projet informatique", "Project Manager IT", "Chef de projet"),
        skills=("Gestion de projet", "Agile", "Scrum", "Jira", "Rédaction de spécifications", "Budget", "Planning", "Communication", "Recette", "Conduite du changement"),
        degrees=("Master management de projet", "Diplôme d'ingénieur", "Master informatique"),
        certifications=("PMP", "PSM I", "Prince2 Foundation"),
        missions=("Piloter des projets informatiques de bout en bout.", "Animer les ateliers et coordonner les parties prenantes.", "Sécuriser les délais, le budget et la qualité."),
        projects=("Refonte ERP", "Déploiement d'une plateforme métier", "Programme de migration applicative"),
    ),
    "Consultant IA": JobProfileSpec(
        name="Consultant IA",
        aliases=("Consultant IA", "AI Consultant", "Consultant intelligence artificielle"),
        skills=("Python", "LLM", "RAG", "NLP", "Ateliers métiers", "Data governance", "FastAPI", "Azure", "AWS", "Gestion de projet"),
        degrees=("Master intelligence artificielle", "Diplôme d'ingénieur", "Master data science"),
        certifications=("Azure AI Engineer Associate", "AWS Machine Learning Specialty", "Hugging Face Course"),
        missions=("Accompagner les équipes dans les usages IA.", "Cadrer des cas d'usage et construire des prototypes.", "Mesurer la valeur métier et les risques associés."),
        projects=("Audit de maturité IA", "Prototype assistant métier", "Roadmap IA responsable"),
    ),
    "Technicien audiovisuel": JobProfileSpec(
        name="Technicien audiovisuel",
        aliases=("Technicien audiovisuel", "Audiovisual Technician", "Technicien vidéo"),
        skills=("Vidéo", "Audio", "FFmpeg", "OBS", "VMix", "Routage signal", "Éclairage", "MIDI", "OSC", "Réseaux"),
        degrees=("BTS audiovisuel", "Bac pro audiovisuel", "CAP métiers de l'image"),
        certifications=("SRT", "NDI", "Habilitation électrique"),
        missions=("Installer et exploiter des dispositifs audiovisuels.", "Gérer le câblage, la diffusion et l'enregistrement.", "Assurer les réglages et le support technique."),
        projects=("Captation live multicam", "Régie de conférence", "Diffusion hybride d'événements"),
    ),
    "Régisseur son": JobProfileSpec(
        name="Régisseur son",
        aliases=("Régisseur son", "Sound Engineer", "Technicien son"),
        skills=("Sonorisation", "MIDI", "OSC", "Console numérique", "Dante", "Microphonie", "Mixage", "Acoustique", "Réseaux", "Maintenance"),
        degrees=("BTS audiovisuel", "Diplôme de technicien du spectacle", "Formation sonorisation"),
        certifications=("Dante Level 2", "Habilitation électrique", "SMAART"),
        missions=("Préparer et exploiter les systèmes son.", "Régler les retours et la diffusion façade.", "Garantir la qualité audio sur site."),
        projects=("Festival itinérant", "Tournée live", "Captation multi-sources"),
    ),
    "Régisseur lumière": JobProfileSpec(
        name="Régisseur lumière",
        aliases=("Régisseur lumière", "Lighting Engineer", "Technicien lumière"),
        skills=("Éclairage scénique", "DMX", "ArtNet", "MA3", "GrandMA", "LED", "Réseaux", "Programmation", "Maintenance", "Sécurité"),
        degrees=("BTS audiovisuel", "Diplôme de technicien lumière", "Formation éclairage scénique"),
        certifications=("Habilitation électrique", "DMX", "ArtNet"),
        missions=("Concevoir et piloter les plans lumière.", "Programmer les automates et gérer les réseaux.", "Préparer les implantations et le matériel."),
        projects=("Spectacle vivant", "Tournée lumière", "Installation immersive"),
    ),
    "Régisseur vidéo": JobProfileSpec(
        name="Régisseur vidéo",
        aliases=("Régisseur vidéo", "Video Engineer", "Technicien vidéo"),
        skills=("Vidéo", "Projection", "NDI", "SDI", "Resolume", "OBS", "FFmpeg", "Mapping", "Réseaux", "Playback"),
        degrees=("BTS audiovisuel", "Formation vidéo", "Bac pro audiovisuel"),
        certifications=("NDI", "SRT", "Habilitation électrique"),
        missions=("Préparer les flux vidéo et les projections.", "Assurer la lecture des contenus et les transitions.", "Garantir la stabilité du dispositif de diffusion."),
        projects=("Mapping événementiel", "Régie streaming", "Scénographie vidéo"),
    ),
    "Ingénieur du son": JobProfileSpec(
        name="Ingénieur du son",
        aliases=("Ingénieur du son", "Sound Engineer", "Ingénieur audio"),
        skills=("Acoustique", "Enregistrement", "Mixage", "Mastering", "Pro Tools", "Ableton Live", "Compression", "Égalisation", "Dante", "Routage"),
        degrees=("BTS audiovisuel", "Formation ingénierie audio", "Diplôme du spectacle"),
        certifications=("Pro Tools", "Dante Level 2", "SMAART"),
        missions=("Capturer, éditer et mixer les sources audio.", "Optimiser les chaînes de traitement et les niveaux.", "Préparer des sessions d'enregistrement et de post-production."),
        projects=("Album studio", "Podcast multicam", "Live session"),
    ),
    "Électronicien": JobProfileSpec(
        name="Électronicien",
        aliases=("Électronicien", "Electronics Technician", "Technicien électronique"),
        skills=("Électronique", "PCB", "Microcontrôleurs", "Soudure", "Mesure", "Câblage", "Diagnostic", "Arduino", "RF", "Réseaux"),
        degrees=("BTS électronique", "DUT génie électrique", "Licence électronique"),
        certifications=("IPC", "Habilitation électrique", "LabVIEW"),
        missions=("Diagnostiquer et réparer des systèmes électroniques.", "Concevoir et prototyper des cartes et des câblages.", "Valider les mesures et la conformité technique."),
        projects=("Prototype IoT", "Carte de contrôle", "Banc de test automatisé"),
    ),
    "Technicien réseau": JobProfileSpec(
        name="Technicien réseau",
        aliases=("Technicien réseau", "Network Technician", "Administrateur réseau junior"),
        skills=("Réseaux", "TCP/IP", "VLAN", "Switching", "Routing", "Wireshark", "VPN", "Linux", "Cisco", "Sécurité réseau"),
        degrees=("BTS SIO", "DUT réseaux et télécoms", "Licence administration réseau"),
        certifications=("Cisco CCNA", "CompTIA Network+", "Mikrotik"),
        missions=("Installer et dépanner les équipements réseau.", "Superviser les flux et les interconnexions.", "Renforcer la sécurité et la disponibilité."),
        projects=("Renouvellement LAN", "Supervision réseau", "VPN intersites"),
    ),
}


TEMPLATE_SPECS: dict[str, TemplateSpec] = {
    "classic": TemplateSpec(
        name="classic",
        section_orders=(
            ("identity", "experience", "education", "skills", "languages", "certifications", "projects", "links", "misc"),
            ("identity", "skills", "experience", "education", "projects", "languages", "links"),
        ),
        minimum_noise=0,
    ),
    "compact": TemplateSpec(
        name="compact",
        section_orders=(
            ("identity", "skills", "experience", "education", "languages", "links"),
            ("identity", "experience", "skills", "education", "misc"),
        ),
        compact=True,
    ),
    "technical": TemplateSpec(
        name="technical",
        section_orders=(
            ("identity", "skills", "projects", "experience", "certifications", "education", "links"),
            ("identity", "skills", "experience", "projects", "education", "links"),
        ),
    ),
    "academic": TemplateSpec(
        name="academic",
        section_orders=(
            ("identity", "education", "projects", "experience", "skills", "languages", "certifications"),
            ("identity", "education", "experience", "skills", "projects", "links"),
        ),
    ),
    "creative": TemplateSpec(
        name="creative",
        section_orders=(
            ("identity", "projects", "skills", "experience", "links", "certifications", "education"),
            ("identity", "skills", "projects", "experience", "misc", "links"),
        ),
        allow_missing_sections=("certifications", "languages"),
    ),
    "minimal": TemplateSpec(
        name="minimal",
        section_orders=(
            ("identity", "skills", "experience", "education", "links"),
            ("identity", "experience", "skills", "education"),
        ),
        allow_missing_sections=("languages", "certifications", "projects", "links", "misc"),
    ),
    "noisy_pdf": TemplateSpec(
        name="noisy_pdf",
        section_orders=(
            ("identity", "experience", "skills", "education", "projects", "languages", "certifications", "links", "misc"),
            ("identity", "skills", "experience", "education", "links", "projects", "misc"),
        ),
        minimum_noise=2,
    ),
}


def _choose_weighted(rng: random.Random, weighted: tuple[tuple[str, int], ...]) -> str:
    pool: list[str] = []
    for value, weight in weighted:
        pool.extend([value] * max(int(weight), 1))
    return rng.choice(pool)


def _pick(seq: Iterable[str], rng: random.Random) -> str:
    items = list(seq)
    return rng.choice(items)


def _synthetic_city(fake: Faker, rng: random.Random) -> str:
    suffixes = ("-sur-Mer", "-les-Bains", "-les-Vignes", "-sur-Loire", "-en-Val")
    return f"{_title_case(fake.word())}{rng.choice(suffixes)}"


def _synthetic_company(fake: Faker, rng: random.Random, profile: JobProfileSpec) -> str:
    prefixes = ("Nova", "Astra", "Orion", "Luma", "Nexa", "Mosaic", "Helio", "Pixel", "Vector", "Saphir")
    suffixes = ("Studio", "Lab", "Group", "Systems", "Works", "Collective", "Factory", "Digital")
    return f"{rng.choice(prefixes)} {_title_case(fake.word())} {rng.choice(suffixes)}"


def _synthetic_school(fake: Faker, rng: random.Random, profile: JobProfileSpec) -> str:
    prefixes = ("Institut", "École", "Campus", "Académie", "Centre")
    suffixes = ("du Numérique", "Technologique", "Créatif", "Scientifique", "Professionnel")
    return f"{rng.choice(prefixes)} {_title_case(fake.word())} {rng.choice(suffixes)}"


def _format_phone(rng: random.Random) -> str:
    digits = [rng.choice("0123456789") for _ in range(10)]
    styles = (
        "{0}{1} {2}{3} {4}{5} {6}{7} {8}{9}",
        "{0}{1}.{2}{3}.{4}{5}.{6}{7}.{8}{9}",
        "+33 {0} {1}{2} {3}{4} {5}{6} {7}{8} {9}",
        "{0}{1}{2}{3}{4}{5}{6}{7}{8}{9}",
    )
    style = rng.choice(styles)
    if style.startswith("+33"):
        digits[0] = rng.choice("67")
    elif digits[0] == "0":
        digits[0] = rng.choice("67")
    return style.format(*digits)


def _format_postal_code(rng: random.Random) -> str:
    return f"{rng.randint(10000, 98999):05d}"


def _format_date_year(year: int, rng: random.Random) -> str:
    month = rng.choice(
        [
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
        ]
    )
    return f"{month} {year}"


def _experience_duration(years: float) -> str:
    total_months = max(int(round(years * 12)), 1)
    years_part, months_part = divmod(total_months, 12)
    if years_part and months_part:
        return f"{years_part} ans {months_part} mois"
    if years_part:
        return f"{years_part} ans"
    return f"{months_part} mois"


def _year_span(level: str, rng: random.Random) -> tuple[int, int]:
    if level == "junior":
        return 0, 2
    if level == "senior":
        return 7, 14
    return 3, 6


def _date_span_text(start_year: int, end_year: int, rng: random.Random, current: bool = False) -> str:
    formats = (
        "{0} - {1}",
        "01/{0} - 06/{1}",
        "{2} {0} à {3} {1}",
        "{4} {0} / {5} {1}",
        "{0} aujourdhui" if current else "{0} - {1}",
    )
    start_month_name = _format_date_year(start_year, rng)
    end_month_name = "aujourd'hui" if current else _format_date_year(end_year, rng)
    fmt = rng.choice(formats)
    if fmt == "{0} aujourdhui":
        return f"{start_year} aujourd'hui"
    return fmt.format(
        f"{start_year}",
        f"{end_year}",
        start_month_name.split()[0],
        end_month_name.split()[0] if not current else "aujourd'hui",
        start_month_name,
        end_month_name,
    )


def _noisify_plain_text(text: str, level: int, rng: random.Random, *, allow_newline: bool = True) -> str:
    if level <= 0 or not text:
        return text
    result = text
    if level >= 1 and len(result) > 3:
        if rng.random() < 0.45:
            result = result.replace(" | ", "  |  ")
        if rng.random() < 0.35:
            result = result.replace(" - ", "  -  ")
        if rng.random() < 0.35:
            result = result.replace(" : ", "  :  ")
    if level >= 2:
        result = result.replace("é", "e").replace("è", "e").replace("ê", "e") if rng.random() < 0.4 else result
        if allow_newline and len(result) > 16 and rng.random() < 0.6:
            idx = result.find(" ", max(6, len(result) // 2))
            if idx == -1:
                idx = len(result) // 2
            result = result[:idx] + "\n" + result[idx + 1 :] if idx < len(result) - 1 else result
    if level >= 3:
        if allow_newline and len(result) > 18:
            idx = result.find(" ", max(4, len(result) // 3))
            if idx != -1:
                result = result[:idx] + "-\n" + result[idx + 1 :]
        if allow_newline and "  " not in result:
            result = result.replace(" ", "  ", 1)
    return result


def _section_header_text(section: str, rng: random.Random, template: TemplateSpec, noise_level: int) -> str:
    title = _pick(SECTION_TITLES[section], rng)
    if template.name == "noisy_pdf":
        title = rng.choice((title, _strip_accents(title), title.lower(), title.upper()))
    elif rng.random() < 0.4:
        title = rng.choice((title, title.lower(), title.title(), title.upper()))
    return _noisify_plain_text(title, noise_level, rng, allow_newline=False)


def _add_heading(builder: AnnotatedTextBuilder, section: str, rng: random.Random, template: TemplateSpec, noise_level: int) -> None:
    builder.append_entity(_section_header_text(section, rng, template, noise_level), "SECTION_HEADER")
    builder.newline()


def _render_identity(
    builder: AnnotatedTextBuilder,
    rng: random.Random,
    fake: Faker,
    profile: JobProfileSpec,
    target_job: str,
    experience_level: str,
    noise_level: int,
    template: TemplateSpec,
) -> dict[str, str]:
    first = fake.first_name()
    last = fake.last_name()
    name = f"{first} {last}"
    email = f"{_slugify(name)}@example.test"
    phone = _format_phone(rng)
    postal_code = _format_postal_code(rng)
    city = _synthetic_city(fake, rng)
    street = f"{rng.randint(1, 180)} rue {_title_case(fake.word())} {_title_case(fake.word())}"
    address = f"{street}, {postal_code} {city}"
    website = f"https://{_slugify(name)}.example.test"
    linkedin = f"https://www.linkedin.com/in/{_slugify(name)}"
    github = f"https://github.com/{_slugify(name)}"
    driving_license = rng.choice(DRIVING_LICENSES)

    name_text = _noisify_plain_text(name, noise_level, rng, allow_newline=False)
    job_text = _noisify_plain_text(target_job, noise_level, rng, allow_newline=False)
    address_text = _noisify_plain_text(address, noise_level, rng, allow_newline=False)
    city_text = _noisify_plain_text(city, noise_level, rng, allow_newline=False)
    website_text = website
    linkedin_text = linkedin
    github_text = github

    builder.append_entity(name_text, "NAME")
    builder.newline()
    builder.append_entity(job_text, "JOB_TITLE")
    builder.newline()
    builder.append_entity(address_text, "ADDRESS")
    builder.newline()
    builder.append_entity(postal_code, "POSTAL_CODE")
    builder.space()
    builder.append_entity(city_text, "CITY")
    builder.newline()
    builder.append_entity(email, "EMAIL")
    builder.space()
    builder.append_entity(phone, "PHONE")
    builder.newline()
    builder.append_entity(website_text, "WEBSITE")
    builder.newline()
    builder.append_entity(linkedin_text, "LINKEDIN")
    builder.newline()
    builder.append_entity(github_text, "GITHUB")
    builder.newline()
    builder.append_entity(driving_license, "DRIVING_LICENSE")
    builder.newline()
    if experience_level:
        builder.append(_noisify_plain_text(f"Niveau: {experience_level}", noise_level, rng, allow_newline=False))
        builder.newline()
    return {
        "name": name,
        "email": email,
        "phone": phone,
        "address": address,
        "postal_code": postal_code,
        "city": city,
        "website": website_text,
        "linkedin": linkedin_text,
        "github": github_text,
        "driving_license": driving_license,
    }


def _render_experience_section(
    builder: AnnotatedTextBuilder,
    rng: random.Random,
    fake: Faker,
    profile: JobProfileSpec,
    target_job: str,
    experience_level: str,
    noise_level: int,
    template: TemplateSpec,
) -> None:
    _add_heading(builder, "experience", rng, template, noise_level)
    min_years, max_years = _year_span(experience_level, rng)
    count = rng.randint(1, 4 if experience_level != "junior" else 2)
    current_year = 2025
    years_cursor = current_year - max_years - 1
    for index in range(count):
        duration_years = rng.uniform(max(min_years, 0.5 if experience_level == "junior" else 1.0), max_years)
        duration_years = round(duration_years, 1)
        span_years = max(int(round(duration_years)), 1)
        start_year = max(years_cursor + index * 2, current_year - span_years - rng.randint(0, 2))
        end_year = current_year if index == 0 and rng.random() < 0.25 else min(start_year + span_years, current_year)
        current = end_year == current_year
        job_title = target_job if index == 0 else rng.choice(profile.aliases)
        company = _synthetic_company(fake=fake, rng=rng, profile=profile)
        date_text = _date_span_text(start_year, end_year, rng, current=current)
        duration_text = _experience_duration(duration_years)
        mission = _pick(profile.missions, rng)
        if template.compact or rng.random() < 0.35:
            parts = [
                _noisify_plain_text(date_text, noise_level, rng, allow_newline=False),
                _noisify_plain_text(job_title, noise_level, rng, allow_newline=False),
                _noisify_plain_text(company, noise_level, rng, allow_newline=False),
                _noisify_plain_text(duration_text, noise_level, rng, allow_newline=False),
            ]
            separator_choices = (" | ", " - ", " / ", "   ")
            sep = rng.choice(separator_choices)
            for i, part in enumerate(parts):
                if i == 0:
                    builder.append_entity(part, "DATE")
                elif i == 1:
                    builder.append(sep)
                    builder.append_entity(part, "JOB_TITLE")
                elif i == 2:
                    builder.append(sep)
                    builder.append_entity(part, "COMPANY")
                else:
                    builder.append(sep)
                    builder.append_entity(part, "EXPERIENCE_DURATION")
            builder.newline()
            builder.append(_noisify_plain_text(mission, noise_level, rng))
            builder.newline()
        else:
            builder.append_entity(_noisify_plain_text(date_text, noise_level, rng, allow_newline=False), "DATE")
            builder.space()
            builder.append("-")
            builder.space()
            builder.append_entity(_noisify_plain_text(job_title, noise_level, rng, allow_newline=False), "JOB_TITLE")
            builder.space()
            builder.append("@")
            builder.space()
            builder.append_entity(_noisify_plain_text(company, noise_level, rng, allow_newline=False), "COMPANY")
            builder.newline()
            builder.append_entity(_noisify_plain_text(duration_text, noise_level, rng, allow_newline=False), "EXPERIENCE_DURATION")
            builder.space()
            builder.append(_noisify_plain_text(mission, noise_level, rng))
            builder.newline()


def _render_education_section(
    builder: AnnotatedTextBuilder,
    rng: random.Random,
    fake: Faker,
    profile: JobProfileSpec,
    experience_level: str,
    noise_level: int,
    template: TemplateSpec,
) -> None:
    if template.name == "minimal" and rng.random() < 0.15:
        return
    _add_heading(builder, "education", rng, template, noise_level)
    count = rng.randint(1, 3 if experience_level != "junior" else 2)
    current_year = 2025
    for _ in range(count):
        degree = _pick(profile.degrees, rng)
        school = _synthetic_school(fake, rng, profile)
        year = rng.randint(2010, current_year)
        if rng.random() < 0.35:
            year_text = _format_date_year(year, rng)
        else:
            year_text = str(year)
        builder.append_entity(_noisify_plain_text(degree, noise_level, rng, allow_newline=False), "DEGREE")
        builder.space()
        builder.append("-")
        builder.space()
        builder.append_entity(_noisify_plain_text(school, noise_level, rng, allow_newline=False), "SCHOOL")
        builder.space()
        builder.append("(")
        builder.append_entity(year_text, "DATE")
        builder.append(")")
        builder.newline()


def _render_skills_section(
    builder: AnnotatedTextBuilder,
    rng: random.Random,
    profile: JobProfileSpec,
    experience_level: str,
    noise_level: int,
    template: TemplateSpec,
) -> None:
    if template.name == "minimal" and rng.random() < 0.2:
        return
    _add_heading(builder, "skills", rng, template, noise_level)
    base_count = 8 if experience_level == "junior" else 12 if experience_level == "intermediate" else 15
    skills = list(profile.skills)
    while len(skills) < base_count:
        filler = _pick(profile.skills, rng)
        if filler not in skills:
            skills.append(filler)
    rng.shuffle(skills)
    selected = skills[: rng.randint(max(6, base_count - 2), min(len(skills), base_count + 4))]
    line_count = 1 if template.compact else rng.randint(1, 3)
    chunk_size = max(1, math.ceil(len(selected) / line_count))
    for index in range(0, len(selected), chunk_size):
        chunk = selected[index : index + chunk_size]
        bullet = rng.choice(("- ", "* ", "· "))
        builder.append(bullet)
        for pos, skill in enumerate(chunk):
            if pos:
                builder.append(rng.choice((", ", " / ", " | ", " ; ")))
            builder.append_entity(_noisify_plain_text(skill, noise_level, rng, allow_newline=False), "SKILL")
        builder.newline()


def _render_languages_section(
    builder: AnnotatedTextBuilder,
    rng: random.Random,
    experience_level: str,
    noise_level: int,
    template: TemplateSpec,
) -> None:
    if template.name == "minimal" and rng.random() < 0.4:
        return
    _add_heading(builder, "languages", rng, template, noise_level)
    languages = list(LANGUAGES)
    rng.shuffle(languages)
    count = rng.randint(2, 4 if experience_level != "junior" else 3)
    for language in languages[:count]:
        level = rng.choice(("A2", "B1", "B2", "C1", "C2", "courant", "professionnel"))
        builder.append_entity(_noisify_plain_text(language, noise_level, rng, allow_newline=False), "LANGUAGE")
        builder.append(rng.choice((" : ", " - ", " / ")))
        builder.append(_noisify_plain_text(level, noise_level, rng, allow_newline=False))
        builder.newline()


def _render_certifications_section(
    builder: AnnotatedTextBuilder,
    rng: random.Random,
    profile: JobProfileSpec,
    noise_level: int,
    template: TemplateSpec,
) -> None:
    if template.name in {"minimal", "compact"} and rng.random() < 0.35:
        return
    _add_heading(builder, "certifications", rng, template, noise_level)
    count = rng.randint(1, min(3, len(profile.certifications)))
    for cert in rng.sample(list(profile.certifications), count):
        year = rng.randint(2018, 2025)
        builder.append_entity(_noisify_plain_text(cert, noise_level, rng, allow_newline=False), "CERTIFICATION")
        builder.append(" - ")
        builder.append_entity(str(year), "DATE")
        builder.newline()


def _render_projects_section(
    builder: AnnotatedTextBuilder,
    rng: random.Random,
    profile: JobProfileSpec,
    noise_level: int,
    template: TemplateSpec,
) -> None:
    if template.name == "minimal" and rng.random() < 0.5:
        return
    _add_heading(builder, "projects", rng, template, noise_level)
    count = rng.randint(1, min(3, len(profile.projects)))
    for project in rng.sample(list(profile.projects), count):
        year = rng.randint(2019, 2025)
        description = _pick(profile.missions, rng)
        builder.append_entity(_noisify_plain_text(project, noise_level, rng, allow_newline=False), "PROJECT")
        builder.append(" (")
        builder.append_entity(str(year), "DATE")
        builder.append(") : ")
        builder.append(_noisify_plain_text(description, noise_level, rng))
        builder.newline()


def _render_links_section(
    builder: AnnotatedTextBuilder,
    rng: random.Random,
    person: dict[str, str],
    noise_level: int,
    template: TemplateSpec,
) -> None:
    if template.name == "minimal" and rng.random() < 0.6:
        return
    _add_heading(builder, "links", rng, template, noise_level)
    builder.append("Portfolio ")
    builder.append_entity(person["website"], "WEBSITE")
    builder.newline()
    builder.append("LinkedIn ")
    builder.append_entity(person["linkedin"], "LINKEDIN")
    builder.newline()
    builder.append("GitHub ")
    builder.append_entity(person["github"], "GITHUB")
    builder.newline()


def _render_misc_section(builder: AnnotatedTextBuilder, rng: random.Random, noise_level: int, template: TemplateSpec, profile: JobProfileSpec) -> None:
    if template.name == "minimal" and rng.random() < 0.7:
        return
    _add_heading(builder, "misc", rng, template, noise_level)
    sentence = rng.choice(
        [
            "Disponible pour des missions en présentiel, hybride ou télétravail.",
            "Apte à travailler sur des environnements exigeants et multi-projets.",
            "Sens du collectif, documentation soignée et curiosité technique.",
        ]
    )
    builder.append(_noisify_plain_text(sentence, noise_level, rng))
    builder.newline()


def _render_cv_body(
    builder: AnnotatedTextBuilder,
    rng: random.Random,
    fake: Faker,
    profile: JobProfileSpec,
    template: TemplateSpec,
    target_job: str,
    experience_level: str,
    noise_level: int,
) -> None:
    person = _render_identity(builder, rng, fake, profile, target_job, experience_level, noise_level, template)
    order = list(rng.choice(template.section_orders))
    for section in order:
        if section == "identity":
            continue
        if section == "experience":
            _render_experience_section(builder, rng, fake, profile, target_job, experience_level, noise_level, template)
        elif section == "education":
            _render_education_section(builder, rng, fake, profile, experience_level, noise_level, template)
        elif section == "skills":
            _render_skills_section(builder, rng, profile, experience_level, noise_level, template)
        elif section == "languages":
            _render_languages_section(builder, rng, experience_level, noise_level, template)
        elif section == "certifications":
            _render_certifications_section(builder, rng, profile, noise_level, template)
        elif section == "projects":
            _render_projects_section(builder, rng, profile, noise_level, template)
        elif section == "links":
            _render_links_section(builder, rng, person, noise_level, template)
        elif section == "misc":
            _render_misc_section(builder, rng, noise_level, template, profile)
        builder.newline()


def _ensure_minimum_contact_coverage(records: list[dict[str, Any]]) -> None:
    name_count = sum(1 for record in records if any(entity["label"] == "NAME" for entity in record["entities"]))
    contact_count = sum(
        1
        for record in records
        if any(entity["label"] in CONTACT_LABELS for entity in record["entities"])
    )
    if records and (name_count < math.ceil(len(records) / 2) or contact_count < math.ceil(len(records) / 2)):
        raise RuntimeError("La génération n'a pas atteint la couverture minimale de nom/contact.")


def _validate_record_entity_alignment(text: str, entities: list[dict[str, Any]]) -> None:
    previous_end = 0
    seen: set[tuple[int, int, str, str]] = set()
    for entity in entities:
        start = int(entity["start"])
        end = int(entity["end"])
        label = str(entity["label"])
        value = str(entity["text"])
        if start < previous_end:
            raise ValueError("Chevauchement d'entités détecté.")
        if text[start:end] != value:
            raise ValueError("Offsets invalides pour une entité.")
        key = (start, end, label, value)
        if key in seen:
            raise ValueError("Doublon exact d'entité détecté.")
        seen.add(key)
        previous_end = end


class SyntheticCVGenerator:
    """Generate deterministic synthetic CV records."""

    def __init__(self, seed: int = 42, noise_level: int = 0) -> None:
        self.seed = seed
        self.noise_level = noise_level
        self.rng = random.Random(seed)
        self.fake = Faker("fr_FR")
        self.fake.seed_instance(seed)
        self._template_cycle = list(TEMPLATE_SPECS.keys())
        self.rng.shuffle(self._template_cycle)

    def _template_for_index(self, index: int) -> str:
        return self._template_cycle[(index - 1) % len(self._template_cycle)]

    def _select_profile(self) -> JobProfileSpec:
        return JOB_PROFILES[self.rng.choice(list(JOB_PROFILES.keys()))]

    def generate_record(self, index: int, template_name: str | None = None) -> dict[str, Any]:
        profile = self._select_profile()
        template = TEMPLATE_SPECS[template_name or self._template_for_index(index)]
        experience_level = _choose_weighted(self.rng, profile.level_weights)
        target_job = self.rng.choice(profile.aliases)
        noise_level = max(self.noise_level, template.minimum_noise)
        builder = AnnotatedTextBuilder()
        _render_cv_body(
            builder=builder,
            rng=self.rng,
            fake=self.fake,
            profile=profile,
            template=template,
            target_job=target_job,
            experience_level=experience_level,
            noise_level=noise_level,
        )
        text, entities = builder.build()
        _validate_record_entity_alignment(text, entities)
        metadata = {
            "synthetic": True,
            "template": template.name,
            "target_job": target_job,
            "experience_level": experience_level,
            "language": "fr",
        }
        return {"id": f"cv_{index:06d}", "text": text, "entities": entities, "metadata": metadata}

    def generate_records(self, count: int) -> list[dict[str, Any]]:
        records = [self.generate_record(index) for index in range(1, count + 1)]
        _ensure_minimum_contact_coverage(records)
        return records


def generate_dataset(count: int = 1000, seed: int = 42, noise_level: int = 0) -> list[dict[str, Any]]:
    return SyntheticCVGenerator(seed=seed, noise_level=noise_level).generate_records(count)


def _write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False))
            handle.write("\n")


def _tokenize_with_spans(text: str) -> list[tuple[str, int, int]]:
    return [(match.group(0), match.start(), match.end()) for match in re.finditer(r"\S+", text)]


def _bio_tags(text: str, entities: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    tokens = _tokenize_with_spans(text)
    tags = ["O"] * len(tokens)
    spans = [
        (int(entity["start"]), int(entity["end"]), str(entity["label"]))
        for entity in sorted(entities, key=lambda item: (int(item["start"]), int(item["end"])))
    ]
    for token_index, (_, start, end) in enumerate(tokens):
        for entity_start, entity_end, label in spans:
            if start >= entity_start and end <= entity_end:
                prefix = "B-" if start == entity_start else "I-"
                tags[token_index] = f"{prefix}{label}"
                break
    return [token for token, _, _ in tokens], tags


def convert_to_spacy_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for record in records:
        converted.append(
            {
                "text": record["text"],
                "entities": [[entity["start"], entity["end"], entity["label"]] for entity in record["entities"]],
            }
        )
    return converted


def convert_to_huggingface_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for record in records:
        tokens, tags = _bio_tags(record["text"], record["entities"])
        converted.append({"id": record["id"], "tokens": tokens, "ner_tags": tags})
    return converted


def _split_records(records: list[dict[str, Any]], train_ratio: float, validation_ratio: float, test_ratio: float, seed: int) -> dict[str, list[dict[str, Any]]]:
    total = train_ratio + validation_ratio + test_ratio
    if not math.isclose(total, 1.0, rel_tol=1e-9, abs_tol=1e-9):
        raise ValueError("La somme des ratios de split doit valoir 1.0.")
    rng = random.Random(seed)
    shuffled = list(records)
    rng.shuffle(shuffled)
    count = len(shuffled)
    train_count = int(round(count * train_ratio))
    validation_count = int(round(count * validation_ratio))
    if train_count + validation_count > count:
        validation_count = max(0, count - train_count)
    test_count = count - train_count - validation_count
    train = shuffled[:train_count]
    validation = shuffled[train_count : train_count + validation_count]
    test = shuffled[train_count + validation_count : train_count + validation_count + test_count]
    return {"train": train, "validation": validation, "test": test}


def split_records(
    records: list[dict[str, Any]],
    train_ratio: float,
    validation_ratio: float,
    test_ratio: float,
    seed: int,
) -> dict[str, list[dict[str, Any]]]:
    """Split records by CV boundary with a reproducible shuffle."""

    return _split_records(records, train_ratio, validation_ratio, test_ratio, seed)


def write_dataset(
    records: list[dict[str, Any]],
    output: str | Path,
    output_format: str = "jsonl",
) -> Path:
    path = Path(output)
    if output_format == "jsonl":
        _write_jsonl(path, records)
    elif output_format == "spacy":
        _write_jsonl(path, convert_to_spacy_records(records))
    elif output_format == "huggingface":
        _write_jsonl(path, convert_to_huggingface_records(records))
    else:
        raise ValueError(f"Format de sortie inconnu: {output_format}")
    return path


def convert_jsonl_to_spacy(input_path: str | Path, output_path: str | Path) -> Path:
    records = load_dataset_jsonl(input_path)
    return write_dataset(records, output_path, output_format="spacy")


def convert_jsonl_to_huggingface(input_path: str | Path, output_path: str | Path) -> Path:
    records = load_dataset_jsonl(input_path)
    return write_dataset(records, output_path, output_format="huggingface")


def load_dataset_jsonl(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def build_output_paths(base_output: str | Path) -> dict[str, Path]:
    path = Path(base_output)
    parent = path.parent
    return {
        "train": parent / "train.jsonl",
        "validation": parent / "validation.jsonl",
        "test": parent / "test.jsonl",
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Générateur de CV synthétiques annotés.")
    parser.add_argument("--count", type=int, default=1000, help="Nombre de CV à générer.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Fichier JSONL de sortie ou base de répertoire pour les exports partagés.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Graine aléatoire reproductible.")
    parser.add_argument("--format", choices=("jsonl", "spacy", "huggingface"), default="jsonl", help="Format de sortie.")
    parser.add_argument("--noise-level", type=int, choices=(0, 1, 2, 3), default=0, help="Niveau de bruit des CV.")
    parser.add_argument("--split", action="store_true", help="Découper le dataset en train/validation/test.")
    parser.add_argument("--train-ratio", type=float, default=0.8, help="Proportion du train split.")
    parser.add_argument("--validation-ratio", type=float, default=0.1, help="Proportion de validation.")
    parser.add_argument("--test-ratio", type=float, default=0.1, help="Proportion de test.")
    return parser


def run_cli(args: argparse.Namespace) -> int:
    if args.count < 0:
        raise SystemExit("Le nombre de CV doit être positif.")
    generator = SyntheticCVGenerator(seed=args.seed, noise_level=args.noise_level)
    records = generator.generate_records(args.count)
    if args.split:
        if args.format != "jsonl":
            raise SystemExit("Le découpage train/validation/test est disponible uniquement en JSONL.")
        split_records = _split_records(records, args.train_ratio, args.validation_ratio, args.test_ratio, args.seed)
        output_paths = build_output_paths(args.output)
        for split_name, split_records_list in split_records.items():
            _write_jsonl(output_paths[split_name], split_records_list)
        print(f"Dataset généré avec séparation train/validation/test dans {Path(args.output).parent}")
        return 0

    write_dataset(records, args.output, output_format=args.format)
    print(f"Dataset généré: {Path(args.output)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    return run_cli(args)


if __name__ == "__main__":
    raise SystemExit(main())
