# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

# %% [markdown]
# # Matching des offres
#
# Ce notebook présente la logique métier centrale du matching utilisée par
# la page « Mes offres ». Il s'appuie directement sur le code de production
# du dossier `src/` pour garantir que les exemples reflètent le comportement
# réel de l'application.
#
# Objectif métier:
# - calculer des sous-scores explicables pour les compétences, l'expérience,
#   le diplôme et le contrat;
# - agréger ces sous-scores dans un score global pondéré;
# - éviter qu'une information absente soit interprétée comme une bonne
#   correspondance.
#
# Données d'entrée:
# - un profil utilisateur normalisé;
# - une offre brute ou normalisée;
# - des pondérations optionnelles.
#
# Données de sortie:
# - un dictionnaire de matching exploitable par l'API, l'interface et les
#   exports;
# - un score global sur 100;
# - des sous-scores détaillés et des messages d'explication.
#
# Limites connues:
# - l'expérience est évaluée sur des années exploitables et sur une
#   expression textuelle simple;
# - le diplôme repose sur des intitulés normalisés;
# - le contrat doit être renseigné dans le profil et dans l'offre pour
#   produire un score positif.

# %%
from src.services.matching_service import (
    calculate_matching_score,
    compute_contract_score,
    compute_diploma_score,
    compute_experience_score,
    compute_skill_score,
)

# %% [markdown]
# ## Sous-scores métier
#
# Les fonctions publiques du service retournent un `ScoreComponent` avec:
# - `score`: valeur sur 100;
# - `applicable`: indique si le critère participe au calcul global;
# - `details`: explication métier lisible.

# %%
profile_skills = [
    {"name": "Python", "normalized_name": "Python"},
    {"name": "Flask", "normalized_name": "Flask"},
]
offer_skills = ["Python", "Django"]

skill_result = compute_skill_score(profile_skills, offer_skills)
skill_result

# %%
experience_result = compute_experience_score([
    {"duration_years": 3.0},
], "3 ans")

contract_result = compute_contract_score("CDI", "CDI")
diploma_result = compute_diploma_score([
    {"title": "Master Informatique"},
], ["Master Informatique"])

experience_result, diploma_result, contract_result

# %% [markdown]
# ## Matching complet
#
# L'exemple suivant montre le résultat complet retourné par le moteur.
# Les sous-scores absents restent à 0 lorsqu'ils ne peuvent pas être évalués.

# %%
profile = {
    "skills": profile_skills,
    "experiences": [{"duration_years": 3.0, "job_title": "Développeur backend"}],
    "diplomas": [{"title": "Master Informatique"}],
    "contract_preference": "CDI",
}

offer = {
    "id": "demo-1",
    "titre": "Développeur backend Python",
    "competences": ["Python", "Django"],
    "experience_requise": "3 ans",
    "diplomes_requis": ["Master Informatique"],
    "contrat": "CDI",
    "source": "France Travail",
}

match = calculate_matching_score(profile, offer)
match

# %% [markdown]
# ## Lecture rapide du résultat
#
# - `global_score` est la valeur utilisée pour le tri des offres;
# - `criterion_scores` contient les sous-scores normalisés sur 0 à 1 pour
#   le calcul pondéré;
# - `skill_score`, `experience_score`, `diploma_score` et `contract_score`
#   sont les valeurs affichables par l'interface.

# %%
{
    "score_global": match["global_score"],
    "competences": match["skill_score"],
    "experience": match["experience_score"],
    "diplome": match["diploma_score"],
    "contrat": match["contract_score"],
    "message": match["explanation"]["summary"],
}
