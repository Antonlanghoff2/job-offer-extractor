# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

# %% [markdown]
# # NER des compétences dans TrendRadar IA
#
# Ce notebook explique pourquoi le projet a besoin d'un système de détection
# et de normalisation des compétences, et comment cette brique améliore à la
# fois le matching CV/offres et les statistiques de marché.
#
# L'objectif n'est pas d'entraîner un gros modèle dès maintenant. La première
# version repose sur une approche robuste, déterministe et facile à maintenir :
#
# - un dictionnaire métier de compétences canoniques ;
# - des expressions régulières conservatrices ;
# - une normalisation des alias et des variantes orthographiques ;
# - un regroupement simple des compétences proches ;
# - une interface extensible vers spaCy, CamemBERT ou Sentence-BERT plus tard.

# %% [markdown]
# ## Pré-requis
#
# Le projet fonctionne avec **Python >= 3.8**. Les modules utilisés dans ce
# notebook sont déjà présents dans le dépôt :
#
# - `src.ner.skill_entity_extractor`
# - `src.ner.skill_normalizer`
# - `src.services.matching_service`
# - `src.trend_aggregation`
#
# Si vous voulez convertir ce fichier en notebook classique, la commande
# Jupytext est indiquée à la fin.

# %%
from __future__ import annotations

import json
from pathlib import Path
from pprint import pprint

from src.ner.skill_entity_extractor import extract_skill_entities
from src.ner.skill_normalizer import canonicalize_skill_name, group_skill_variants, normalize_skill_name
from src.services.matching_service import compute_match
from src.trend_aggregation import aggregate_trends


# %% [markdown]
# ## Pourquoi le NER est utile
#
# Sans normalisation, le projet risquerait de compter séparément des variantes
# qui représentent pourtant la même compétence :
#
# - `Python`
# - `python3`
# - `programmation Python`
# - `développement Python`
#
# On obtiendrait alors des statistiques artificielles et un matching moins
# fiable. Le NER permet de ramener ces variantes vers une forme canonique.

# %%
example_text = "Je développe en Python3 avec Flask, puis je travaille sur l'IA et le machine learning."
entities = extract_skill_entities(example_text)

print("Compétences détectées :")
for entity in entities:
    print(f"- {entity.canonical_name} (alias: {entity.alias}, confiance: {entity.confidence})")

# %% [markdown]
# ## Normalisation
#
# La normalisation transforme un texte libre en nom canonique stable.
#
# Exemples :
#
# - `IA` devient `Intelligence artificielle` ;
# - `ML` devient `Machine learning` ;
# - `développement Python` devient `Python`.

# %%
raw_skills = [
    "Python",
    "python3",
    "développement Python",
    "IA",
    "intelligence artificielle",
    "AI",
    "Artificial Intelligence",
    "machine learning",
    "ML",
]

normalized = [normalize_skill_name(skill) for skill in raw_skills]
print("Normalisation individuelle :")
for skill, canonical in zip(raw_skills, normalized):
    print(f"- {skill!r} -> {canonical!r}")

# %% [markdown]
# ## Regroupement des variantes
#
# Une fois les compétences normalisées, on peut les regrouper sous un canonique
# unique. C'est cette structure qui sert ensuite au matching et aux tendances.

# %%
groups = group_skill_variants(raw_skills)
pprint(dict(groups))

# %% [markdown]
# ## Impact sur le matching CV/offres
#
# Le moteur de matching compare désormais des compétences normalisées, et non
# des chaînes brutes. Cela évite de rater une correspondance simplement parce
# qu'un CV dit `programmation Python` et qu'une offre dit `Python3`.

# %%
profile = {
    "skills": [
        {"name": "programmation Python"},
        {"name": "IA"},
    ],
    "desired_jobs": [{"job_title": "Développeur IA"}],
    "experiences": [],
    "diplomas": [],
    "remote_preference": "indifferent",
}

offer = {
    "id": "demo-ner-1",
    "titre": "Développeur Python et IA",
    "competences": ["Python3", "intelligence artificielle"],
    "contrat": "CDI",
    "source": "demo",
    "url_originale": "https://example.org/offre/demo-ner-1",
}

match = compute_match(profile, offer)
print("Score global :", match["global_score"])
print("Compétences communes :", match["matching_skills"])
print("Compétences manquantes :", match["missing_skills"])
print("Résumé :", match["explanation"]["summary"])

# %% [markdown]
# ## Impact sur les tendances de marché
#
# Les statistiques de marché doivent elles aussi compter les compétences sous
# une forme canonique unique. Cela évite de disperser les résultats entre
# `Python`, `python` et `Python3`.
#
# Le résultat peut aussi conserver un détail des variantes observées, utile pour
# la lecture métier.

# %%
offers = [
    {
        "id": "1",
        "date": "2026-06-01",
        "territoire": "Lyon",
        "metier": "Développeur Python",
        "niveau": "intermediaire",
        "contrat": "CDI",
        "competences": ["Python", "python3", "développement Python"],
        "intitule": "Développeur Python",
    },
    {
        "id": "2",
        "date": "2026-06-02",
        "territoire": "Lyon",
        "metier": "Développeur Python",
        "niveau": "intermediaire",
        "contrat": "CDI",
        "competences": ["programmation Python", "Flask"],
        "intitule": "Développeur Python",
    },
    {
        "id": "3",
        "date": "2026-06-03",
        "territoire": "Lyon",
        "metier": "Ingénieur IA",
        "niveau": "senior",
        "contrat": "CDI",
        "competences": ["IA", "AI", "intelligence artificielle"],
        "intitule": "Ingénieur IA",
    },
]

trends = aggregate_trends(offers, territoire="Lyon", periode_jours=30)
print("Compétences agrégées :")
pprint(trends["competences"])
print("\nDétail des variantes :")
pprint(trends["competences_variants"])

# %% [markdown]
# ## Ce qu'il faut retenir
#
# - Le NER permet de détecter des compétences dans du texte libre.
# - La normalisation évite de compter séparément des variantes équivalentes.
# - Le regroupement donne une vue canonique, plus stable pour l'analyse.
# - Le matching et les tendances deviennent plus cohérents et plus explicables.
#
# ### Limites actuelles
#
# - Le dictionnaire initial doit être enrichi au fil des cas rencontrés.
# - La similarité sémantique est volontairement prudente.
# - Les variantes très ambiguës doivent être ajoutées avec des tests.
# - Une couche spaCy ou Sentence-BERT pourra être ajoutée plus tard, mais elle
#   n'est pas nécessaire pour faire fonctionner le MVP.

# %% [markdown]
# ## Conversion en notebook Jupyter
#
# Pour convertir ce fichier en `.ipynb` avec Jupytext :
#
# ```bash
# jupytext --to ipynb docs/notebooks/ner_competences.py
# ```
