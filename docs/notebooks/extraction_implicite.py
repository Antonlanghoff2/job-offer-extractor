# %% [markdown]
# # Extraction de compétences implicites
#
# Ce notebook présente le module d'extraction de compétences implicites
# pour TrendRadar IA.
#
# ## Objectif métier
#
# Déduire des compétences à partir d'actions et de responsabilités décrites
# dans les offres d'emploi, sans que celles-ci ne soient explicitement mentionnées.
#
# ## Exemples
#
# - « Vous déploierez les modèles en production » → MLOps
# - « Vous concevrez des flux d'alimentation des données » → Data Engineering
# - « Vous développerez des services capables de traiter plusieurs milliers de requêtes » → Backend, Scalabilité
#
# ## Architecture
#
# 1. Segmentation de l'offre en phrases
# 2. Identification des phrases de missions/responsabilités
# 3. Détection des négations (pour éviter les faux positifs)
# 4. Matching avec les indicateurs du référentiel
# 5. Matching sémantique avec Sentence Transformers (optionnel)

# %%
from src.skill_extraction import (
    extract_implicit_skills,
    extract_skills_categorized,
    extract_skills_from_offer,
)
from src.skill_extraction.implicit_extractor import reset_caches

reset_caches()

# %% [markdown]
# ## 1. Extraction implicite de base
#
# Le module `extract_implicit_skills` détecte les compétences implicites
# depuis les descriptions de missions.

# %%
texte = "Vous déploierez les modèles en production et surveillerez leur dérive."
skills, debug_infos = extract_implicit_skills(texte, debug=True)

print(f"Compétences implicites détectées: {len(skills)}")
for skill in skills:
    print(f"  - {skill.canonical_name}")
    print(f"    Raison: {skill.reason}")
    print(f"    Score: {skill.confidence:.2f}")

# %% [markdown]
# ## 2. Data Engineering implicite

# %%
texte = "Vous concevrez des flux d'alimentation, de transformation et de contrôle des données."
skills, _ = extract_implicit_skills(texte)

print(f"Compétences implicites détectées: {len(skills)}")
for skill in skills:
    print(f"  - {skill.canonical_name}: {skill.reason}")

# %% [markdown]
# ## 3. Backend et Scalabilité

# %%
texte = "Vous développerez des services capables de traiter plusieurs milliers de requêtes simultanées."
skills, _ = extract_implicit_skills(texte)

print(f"Compétences implicites détectées: {len(skills)}")
for skill in skills:
    print(f"  - {skill.canonical_name}: {skill.reason}")

# %% [markdown]
# ## 4. Détection des négations
#
# Les phrases contenant des négations ne produisent pas de compétences.

# %%
texte = "Aucune connaissance de Kubernetes n'est requise pour ce poste."
skills, debug_infos = extract_implicit_skills(texte, debug=True)

print(f"Compétences détectées: {len(skills)}")
print(f"Phrases analysées: {len(debug_infos)}")
for info in debug_infos:
    print(f"  Phrase: {info.sentence[:60]}...")
    print(f"  Négation détectée: {info.is_negated}")

# %% [markdown]
# ## 5. Éviter les faux positifs
#
# Les phrases trop génériques ne produisent pas de compétences.

# %%
texte = "Vous travaillerez dans une équipe dynamique et collaborative."
skills, _ = extract_implicit_skills(texte)

print(f"Compétences détectées: {len(skills)}")
print("(Aucune compétence ne doit être extraite)")

# %% [markdown]
# ## 6. Séparation explicite / sémantique / implicite
#
# La fonction `extract_skills_categorized` retourne les compétences
# séparées par type d'extraction.

# %%
texte = """
Nous recherchons un Data Scientist.

Profil requis :
- Python et SQL
- Expérience avec Docker

Missions :
- Vous déploierez les modèles en production
- Vous concevrez des flux de données
- Vous surveillerez la dérive des modèles
"""

result = extract_skills_categorized(texte)

print("Compétences explicites:")
for skill in result["competences_explicit"]:
    print(f"  - {skill.canonical_name}")

print("\nCompétences sémantiques:")
for skill in result["competences_semantic"]:
    print(f"  - {skill.canonical_name}")

print("\nCompétences implicites:")
for skill in result["competences_implicit"]:
    print(f"  - {skill.canonical_name}")
    print(f"    Raison: {skill.reason}")

# %% [markdown]
# ## 7. Priorité d'extraction
#
# Si une compétence existe explicitement, la version implicite est supprimée.
# Priorité : explicite > sémantique > implicite

# %%
texte = "Python requis. Vous développerez des applications Python."
result = extract_skills_categorized(texte)

print("Compétences explicites:")
for skill in result["competences_explicit"]:
    print(f"  - {skill.canonical_name} (type={skill.extraction_type})")

print("\nCompétences implicites:")
for skill in result["competences_implicit"]:
    print(f"  - {skill.canonical_name} (type={skill.extraction_type})")

print("\nPython apparaît uniquement dans les explicites (pas de doublon)")

# %% [markdown]
# ## 8. Mode debug complet
#
# Le mode debug affiche :
# - Phrase analysée
# - Compétences candidates
# - Scores
# - Seuils appliqués
# - Résultats acceptés/rejetés
# - Raisons du rejet

# %%
texte = """
Vous déploierez les modèles en production.
Aucune connaissance de Kubernetes n'est requise.
Vous travaillerez dans une équipe dynamique.
"""

skills, debug_infos = extract_implicit_skills(texte, debug=True)

print("Analyse détaillée:")
for info in debug_infos:
    print(f"\n  Phrase: {info.sentence}")
    print(f"  Mission: {info.is_mission}")
    print(f"  Négation: {info.is_negated}")
    print(f"  Générique: {info.is_generic}")
    if info.accepted:
        print(f"  Acceptées: {[a['skill'] for a in info.accepted]}")
    if info.rejected:
        print(f"  Rejetées: {[r.get('reason', 'unknown') for r in info.rejected]}")

# %% [markdown]
# ## 9. Justification traçable
#
# Chaque compétence implicite possède une justification.

# %%
texte = "Vous sécuriserez les applications et gérerez l'authentification."
skills, _ = extract_implicit_skills(texte)

print("Compétences avec justification:")
for skill in skills:
    print(f"  - {skill.canonical_name}")
    print(f"    Source: {skill.source_sentence[:60]}...")
    print(f"    Raison: {skill.reason}")
    print(f"    Type: {skill.extraction_type}")
    print(f"    Confiance: {skill.confidence:.2f}")

# %% [markdown]
# ## 10. Configuration
#
# Les paramètres suivants sont configurables via des variables d'environnement :
#
# - `IMPLICIT_SKILL_THRESHOLD` : Seuil de similarité (défaut: 0.78)
# - `MAX_IMPLICIT_SKILLS_PER_SENTENCE` : Max compétences par phrase (défaut: 3)
# - `ENABLE_IMPLICIT_SKILLS` : Activer/désactiver l'extraction implicite
# - `ENABLE_SENTENCE_TRANSFORMERS` : Activer Sentence Transformers
# - `DEBUG_IMPLICIT_EXTRACTION` : Activer le mode debug

# %%
import os

print("Configuration actuelle:")
print(f"  IMPLICIT_SKILL_THRESHOLD: {os.getenv('IMPLICIT_SKILL_THRESHOLD', '0.78')}")
print(f"  MAX_IMPLICIT_SKILLS_PER_SENTENCE: {os.getenv('MAX_IMPLICIT_SKILLS_PER_SENTENCE', '3')}")
print(f"  ENABLE_IMPLICIT_SKILLS: {os.getenv('ENABLE_IMPLICIT_SKILLS', 'true')}")
print(f"  ENABLE_SENTENCE_TRANSFORMERS: {os.getenv('ENABLE_SENTENCE_TRANSFORMERS', 'false')}")

# %% [markdown]
# ## Résumé
#
# L'extraction implicite permet :
# - De déduire des compétences depuis les descriptions de missions
# - D'éviter les faux positifs grâce à la détection des négations
# - De filtrer les phrases trop génériques
# - De fournir une justification traçable pour chaque compétence
# - De séparer les compétences par type d'extraction
#
# ## Limites connues
#
# - Le matching par indicateurs est limité aux formulations du référentiel
# - Sentence Transformers améliore la détection mais nécessite un modèle
# - Certaines formulations très spécifiques peuvent ne pas être détectées
# - Le référentiel d'indicateurs doit être maintenu manuellement
