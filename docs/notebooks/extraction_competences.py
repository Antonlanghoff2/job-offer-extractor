# %% [markdown]
# # Extraction hybride de compétences
#
# Ce notebook présente le pipeline d'extraction de compétences amélioré
# pour TrendRadar IA.
#
# ## Objectif métier
#
# Extraire et normaliser les compétences depuis les offres d'emploi France Travail
# en combinant :
# 1. Les compétences structurées de l'API
# 2. L'extraction lexicale (dictionnaire NER)
# 3. L'extraction des savoir-faire (phrases verbales → compétences nominales)
# 4. Le rapprochement sémantique avec un référentiel
#
# ## Données d'entrée
#
# - Texte brut de l'offre d'emploi
# - Compétences structurées de l'API France Travail (optionnel)
#
# ## Données de sortie
#
# - Liste de compétences normalisées avec :
#   - Nom canonique
#   - Texte brut source
#   - Phrase source
#   - Type d'extraction (explicit, semantic, implicit)
#   - Score de confiance
#   - Catégorie

# %%
from src.skill_extraction import extract_skills_from_offer
from src.skill_extraction.savoir_faire_extractor import extract_savoir_faire

# %% [markdown]
# ## 1. Extraction des savoir-faire
#
# Le module `savoir_faire_extractor` transforme les phrases verbales en
# compétences nominales normalisées.

# %%
texte = "Vous serez chargé de concevoir et gérer un projet d'analyse de données."
resultats = extract_savoir_faire(texte)

print("Phrases verbales détectées:")
for canonical, raw, sentence in resultats:
    print(f"  {canonical!r} <- {raw!r}")

# %% [markdown]
# ## 2. Pipeline complet
#
# La fonction `extract_skills_from_offer` orchestre l'ensemble du pipeline.

# %%
texte_offre = """
Nous recherchons un Data Scientist pour rejoindre notre équipe.

Missions :
- Concevoir et déployer des modèles de machine learning
- Analyser et structurer les données
- Collaborer avec les équipes produit

Profil recherché :
- Maîtrise de Python et SQL
- Expérience avec PyTorch ou TensorFlow
- Connaissance de Docker et Kubernetes
"""

competences = extract_skills_from_offer(texte_offre)

print(f"Compétences extraites: {len(competences)}")
for skill in competences:
    print(f"  - {skill.canonical_name} ({skill.extraction_type}, conf={skill.confidence:.2f})")

# %% [markdown]
# ## 3. Normalisation des phrases verbales
#
# Les phrases comme "Développer des modèles prédictifs" sont transformées
# en "Développement de modèles prédictifs".

# %%
from src.skill_extraction.skill_normalizer import normalize_phrase_to_skill

phrases = [
    "Développer des modèles prédictifs",
    "Analyser les données clients",
    "Gérer une base de données",
    "Concevoir l'architecture du système",
]

print("Normalisation des phrases verbales:")
for phrase in phrases:
    normalized = normalize_phrase_to_skill(phrase)
    print(f"  {phrase!r} -> {normalized!r}")

# %% [markdown]
# ## 4. Gestion des négations et options
#
# Le pipeline détecte les contextes de négation et les compétences optionnelles.

# %%
texte_negation = """
Aucune connaissance de Kubernetes n'est requise.
La maîtrise de React serait un plus.
Python est obligatoire.
"""

skills = extract_skills_from_offer(texte_negation)

print("Compétences avec contexte:")
for skill in skills:
    status = "OPTIONNEL" if skill.optional else "REQUIS"
    if skill.negated:
        status = "NIÉ"
    print(f"  - {skill.canonical_name}: {status}")

# %% [markdown]
# ## 5. Déduplication et fusion
#
# Les variantes de casse, accents et pluriels sont fusionnées.

# %%
texte_variantes = "Python python PYTHON SQL sql"
skills = extract_skills_from_offer(texte_variantes)

print(f"Après déduplication: {len(skills)} compétences")
for skill in skills:
    print(f"  - {skill.canonical_name}")

# %% [markdown]
# ## 6. Mode debug
#
# Le mode debug permet de voir le détail de l'extraction.

# %%
skills_debug = extract_skills_from_offer("Maîtrise de Python et Docker", debug=True)

# %% [markdown]
# ## 7. Intégration avec les compétences structurées
#
# Le pipeline peut combiner les compétences de l'API avec celles extraites du texte.

# %%
competences_api = ["Python", "Docker", "Kubernetes"]
texte_description = "Nous utilisons aussi PyTorch et TensorFlow."

skills = extract_skills_from_offer(
    texte_description,
    structured_competences=competences_api
)

print("Compétences combinées:")
for skill in skills:
    source = "API" if skill.source_sentence == "(API France Travail)" else "Texte"
    print(f"  - {skill.canonical_name} (source: {source})")

# %% [markdown]
# ## Résumé
#
# Le pipeline d'extraction hybride permet :
# - D'extraire plus de compétences depuis les descriptions
# - De normaliser les phrases verbales en compétences nominales
# - De gérer les négations et les options
# - De dédupliquer les variantes
# - De combiner les sources structurées et textuelles
#
# ## Limites connues
#
# - Le rapprochement sémantique nécessite Sentence Transformers (optionnel)
# - Certaines formulations très spécifiques peuvent ne pas être détectées
# - Le référentiel de compétences doit être maintenu manuellement
