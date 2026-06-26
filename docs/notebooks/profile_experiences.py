# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

# %% [markdown]
# # Extraction des compétences depuis les expériences professionnelles
#
# Ce notebook présente le service métier qui lit l'intitulé et la description d'une
# expérience professionnelle pour proposer des compétences exploitables dans le profil.
#
# Objectif métier:
# - suggérer des compétences réellement soutenues par le texte;
# - normaliser les variantes courantes;
# - éviter les doublons avec les compétences déjà présentes dans le profil.
#
# Entrées:
# - `job_title`: intitulé du poste;
# - `description`: description des missions;
# - `existing_skills`: liste optionnelle de compétences déjà validées.
#
# Sortie:
# - liste de dictionnaires JSON-compatibles contenant au minimum le nom, la provenance et la confiance.
#
# Limites:
# - le service reste conservateur et n'invente pas de compétences non observables;
# - l'extraction repose sur des règles métiers et sur les extracteurs de compétences existants.

# %%
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.profile_extraction.experience_skill_extractor import extract_skills_from_experience

# %% [markdown]
# ## Exemple minimal
#
# L'exemple ci-dessous illustre une expérience orientée développement backend.

# %%
skills = extract_skills_from_experience(
    "Développeur backend Python",
    "Développement d'API REST avec Flask, PostgreSQL, Docker et Git. Mise en place de tests automatisés.",
)

skills

# %% [markdown]
# ## Déduplication avec des compétences déjà présentes
#
# Si le profil contient déjà certaines compétences, elles sont exclues des suggestions.

# %%
filtered_skills = extract_skills_from_experience(
    "Ingénieur DevOps",
    "Déploiement sur GitLab CI et administration PostgreSQL avec Python3.",
    existing_skills=["Python", "PostgreSQL"],
)

filtered_skills

# %% [markdown]
# ## Lecture métier
#
# Le service accepte aussi les intitulés issus de métiers techniques hors développement,
# par exemple dans l'audio ou la maintenance.

# %%
extract_skills_from_experience(
    "Ingénieur du son",
    "Installation et exploitation d'un réseau audio Dante, mixage sur console numérique et maintenance du parc.",
)
