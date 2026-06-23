# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

# %% [markdown]
# # Extraction hybride de compétences — Pipeline à 4 niveaux
#
# Ce notebook présente le pipeline d'extraction de compétences mis en place
# dans TrendRadar IA pour analyser les offres d'emploi.
#
# Le système combine quatre niveaux d'extraction :
#
# 1. **Extraction lexicale** — détection des compétences explicites via le
#    dictionnaire NER et la liste `KNOWN_SKILLS`.
# 2. **Extraction de candidats** — extraction d'expressions candidates depuis
#    les missions et le profil recherché.
# 3. **Rapprochement sémantique** — comparaison des candidats avec un
#    référentiel JSON via similarité textuelle ou Sentence Transformers.
# 4. **Normalisation** — fusion des doublons et application des priorités
#    (explicit > semantic > implicit).
#
# L'extraction reste explicable, testable et ne repose sur aucun LLM distant.

# %% [markdown]
# ## Pré-requis
#
# - Python >= 3.8
# - `sentence-transformers` est optionnel (fallback textuel par défaut)
#
# Modules utilisés :
#
# - `src.skill_extraction.skill_pipeline`
# - `src.skill_extraction.lexical_extractor`
# - `src.skill_extraction.candidate_extractor`
# - `src.skill_extraction.semantic_matcher`
# - `src.skill_extraction.models`

# %%
from __future__ import annotations

import json
from pprint import pprint

from src.skill_extraction import ExtractedSkill, extract_skills_from_offer
from src.skill_extraction.candidate_extractor import extract_candidates
from src.skill_extraction.lexical_extractor import extract_explicit_skills
from src.skill_extraction.semantic_matcher import reset_caches

reset_caches()


# %% [markdown]
# ## Niveau 1 — Extraction lexicale
#
# Détecte les compétences explicitement mentionnées dans le texte.
# Chaque compétence est reconnue par le dictionnaire NER ou la liste
# `KNOWN_SKILLS`. Le score de confiance est 1.0.

# %%
texte_explicite = "Maîtrise de Python, Docker et PostgreSQL requise."
skills_explicites = extract_explicit_skills(texte_explicite)
for skill in skills_explicites:
    print(f"  {skill.canonical_name} (type={skill.extraction_type}, confiance={skill.confidence})")


# %% [markdown]
# ## Niveau 2 — Extraction de candidats
#
# Extrait des expressions candidates depuis les formulations du texte :
# verbes d'action, groupes nominaux techniques, listes de compétences.

# %%
texte_missions = "Vous mettrez les modèles en production et surveillerez leur dérive."
candidats = extract_candidates(texte_missions)
for candidat, phrase in candidats:
    print(f"  Candidat : {candidat!r}")
    print(f"  Phrase   : {phrase!r}")
    print()


# %% [markdown]
# ## Niveau 3 — Rapprochement sémantique
#
# Compare les candidats avec le référentiel `data/referentials/skills.json`.
# Sans Sentence Transformers, la comparaison est textuelle (similarité cosinus
# sur les tokens). Avec Sentence Transformers, les embeddings sont utilisés.

# %% [markdown]
# ## Pipeline complet
#
# La fonction `extract_skills_from_offer` orchestre les 4 niveaux.

# %%
texte_complet = """
Développeur Machine Learning - CDI Paris

Vous développerez et maintiendrez des flux de traitement et d'alimentation de données.
Vous mettrez les modèles en production et surveillerez leur dérive.

Compétences requises : Python, Docker, PostgreSQL, machine learning.
Une connaissance de Kubernetes serait un plus.
Aucune connaissance de SAP n'est requise.
"""

skills = extract_skills_from_offer(texte_complet)
print(f"Compétences extraites : {len(skills)}")
print()
for skill in skills:
    print(f"  [{skill.extraction_type:>8} | {skill.confidence:.2f}] {skill.canonical_name}")
    print(f"    Texte brut : {skill.raw_text!r}")
    print(f"    Catégorie  : {skill.category}")
    if skill.optional:
        print(f"    → Souhaitée mais non requise")
    if skill.negated:
        print(f"    → Contexte de négation")
    print()


# %% [markdown]
# ## Format de sortie détaillé
#
# Chaque compétence conserve sa trace d'extraction pour l'explicabilité.

# %%
for skill in skills:
    pprint(skill.to_dict(), width=100)
    print()


# %% [markdown]
# ## Limites connues
#
# - L'extraction implicite n'est pas certaine : elle indique un rapprochement
#   avec le référentiel, pas une compétence explicitement demandée.
# - Sans Sentence Transformers, la similarité textuelle est conservatrice.
# - Le référentiel JSON doit être maintenu manuellement pour couvrir de
#   nouveaux domaines métier.
# - Les faux positifs restent possibles sur des formulations très éloignées
#   du référentiel.

# %% [markdown]
# ## Export Jupyter
#
# ```bash
# jupytext --to ipynb docs/notebooks/extraction_hybride.py
# ```
