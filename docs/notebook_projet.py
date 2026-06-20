# %% [markdown]
# # TrendRadar IA — Notebook pédagogique du projet
#
# Ce notebook a pour objectif de faire découvrir le projet **TrendRadar IA**
# à une personne qui arrive sur le dépôt pour la première fois.
#
# Il ne remplace pas la lecture du code source, mais il aide à comprendre :
#
# - l’objectif général du projet ;
# - son architecture ;
# - le rôle des principaux fichiers ;
# - le pipeline d’exécution, du texte brut jusqu’aux tableaux de bord ;
# - les composants importants à connaître pour naviguer dans le dépôt ;
# - les limites actuelles et les pistes d’amélioration.
#
# Le notebook est rédigé en français et utilise le format **Jupytext** afin
# de rester lisible dans un fichier `.py` tout en étant convertible en
# `.ipynb`.

# %% [markdown]
# ## Prérequis et mode d’emploi
#
# Le projet s’exécute avec **Python >= 3.8**. Les dépendances sont listées
# dans `requirements.txt` et couvrent notamment :
#
# - Flask pour l’interface web ;
# - scikit-learn pour le modèle de segmentation des offres ;
# - pandas et joblib pour le traitement et la persistance ;
# - Faker pour le jeu de données de CV synthétiques ;
# - openpyxl, pypdf et python-docx pour certaines lectures de fichiers ;
# - Flask-Login, Flask-WTF, Flask-SQLAlchemy et Flask-Migrate pour la partie
#   portail utilisateur.
#
# Ce notebook suppose que vous l’exécutez depuis la racine du dépôt, mais il
# sait aussi retrouver le projet en remontant l’arborescence courante.
#
# Si vous souhaitez le convertir en notebook Jupyter classique, la commande
# Jupytext est donnée en fin de document.

# %%
from __future__ import annotations

import json
from pathlib import Path
from pprint import pprint
from typing import Any, Dict, Iterable, List, Optional, Tuple


def find_project_root(start: Optional[Path] = None) -> Path:
    """Return the repository root by walking upward from ``start``."""

    start = (start or Path.cwd()).resolve()
    for candidate in [start, *start.parents]:
        if (candidate / "README.md").exists() and (candidate / "src").exists():
            return candidate
    return start


PROJECT_ROOT = find_project_root()
print(f"Racine du projet détectée: {PROJECT_ROOT}")


def pretty(obj: Any) -> None:
    """Print a JSON-friendly object in a readable way."""

    print(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True))


demo_offers: List[Dict[str, Any]] = [
    {
        "id": "demo-001",
        "intitule": "Développeur Python / FastAPI",
        "metier": "Développeur Python",
        "competences_requises": ["Python", "FastAPI", "Docker", "PostgreSQL", "Git"],
        "niveau": "intermediaire",
        "contrat": "CDI",
        "territoire": "Lyon",
        "date_publication": "2026-05-15",
        "source": "demo",
        "url_originale": "https://example.org/offre/1",
    },
    {
        "id": "demo-002",
        "intitule": "Data Analyst",
        "metier": "Data Analyst",
        "competences": ["Python", "SQL", "Pandas", "BI", "Dataviz"],
        "niveau": "junior",
        "contrat": "CDD",
        "territoire": "Lyon",
        "date_publication": "2026-05-20",
        "source": "demo",
        "url_originale": "https://example.org/offre/2",
    },
    {
        "id": "demo-003",
        "intitule": "Ingénieur IA",
        "metier": "Ingénieur IA",
        "competences_requises": ["Python", "PyTorch", "LLM", "RAG", "Docker"],
        "niveau": "senior",
        "contrat": "CDI",
        "territoire": "Paris",
        "date_publication": "2026-05-18",
        "source": "demo",
        "url_originale": "https://example.org/offre/3",
    },
]

demo_profile: Dict[str, Any] = {
    "competences": ["Python", "SQL", "FastAPI", "Docker", "Git"],
    "metier": "Développeur Python",
    "experience": "intermediaire",
    "diplome": "Bac+5",
    "localisation": "Lyon",
    "contrat": "CDI",
    "teletravail": "hybride",
    "salaire": 45000,
    "minimum_salary": 45000,
    "experiences": [{"job_title": "Développeur Python"}],
    "diplomas": ["Bac+5"],
}

demo_cv_text = """Camille Martin
Développeuse Python
camille.martin@example.org
06 12 34 56 78
Lyon

EXPÉRIENCES PROFESSIONNELLES
Développeuse Python - Atelier Numérique - Lyon
2022 - 2025
API REST, FastAPI, PostgreSQL, Docker

FORMATION
Master Informatique
Université Lumière Lyon 2
2020 - 2022

COMPÉTENCES
Python, SQL, FastAPI, Docker, Git
"""

# %% [markdown]
# ## 1. Ce que fait le projet, en une phrase
#
# TrendRadar IA extrait et structure des informations à partir de textes
# d’offres d’emploi et de CV, puis les exploite pour :
#
# - classer des offres selon un profil utilisateur ;
# - analyser les compétences demandées par territoire ;
# - proposer des recommandations de formation cohérentes ;
# - importer et valider des CV structurés ;
# - produire des jeux de données synthétiques pour de futures tâches NER.
#
# Le projet combine donc :
#
# - un **pipeline de traitement de texte** ;
# - des **règles métier déterministes** ;
# - un **modèle scikit-learn léger** ;
# - plusieurs **applications Flask** ;
# - des **exports de données** et des **outils de validation**.

# %% [markdown]
# ## 2. Vue d’ensemble de l’architecture
#
# L’architecture est volontairement pragmatique : les briques sont séparées
# par rôle, mais elles restent simples à comprendre.
#
# Schéma logique :
#
# 1. les offres brutes sont récupérées ou lues depuis un snapshot local ;
# 2. elles sont normalisées pour obtenir un format stable ;
# 3. le moteur de matching compare les offres au profil utilisateur ;
# 4. l’agrégation de tendances calcule les compétences les plus fréquentes ;
# 5. la couche recommandation de formation transforme ces tendances en
#    propositions pédagogiques ;
# 6. le portail utilisateur expose les pages de profil, d’offres, de CV et de
#    tableau de bord ;
# 7. le générateur de CV synthétiques prépare un futur corpus d’entraînement
#    pour de l’extraction d’informations.

# %% [markdown]
# ## 3. Carte rapide des fichiers importants
#
# Le bloc suivant affiche les fichiers les plus utiles pour comprendre le
# projet. Il ne remplace pas l’exploration du dépôt, mais il permet de se
# repérer rapidement.

# %%
from collections import OrderedDict


def iter_key_files() -> Iterable[Tuple[str, List[str]]]:
    return [
        (
            "Entrées web",
            [
                "src/web_app.py",
                "src/comparison_web_app.py",
                "src/user_portal.py",
            ],
        ),
        (
            "Modèle d’extraction d’offres",
            [
                "src/preprocessing.py",
                "src/feature_extraction.py",
                "src/train_classifier.py",
                "src/predict.py",
                "src/extractors.py",
            ],
        ),
        (
            "Tendances et recommandations",
            [
                "src/trend_aggregation.py",
                "src/services/offer_repository.py",
                "src/services/matching_service.py",
                "src/services/formation_recommendation.py",
                "src/model2_market_context.py",
                "src/matching/scoring.py",
                "src/matching/weights.py",
            ],
        ),
        (
            "CV et jeux synthétiques",
            [
                "src/cv_parser/parser.py",
                "src/cv_parser/education_extractor.py",
                "src/cv_parser/experience_extractor.py",
                "src/cv_parser/skill_extractor.py",
                "src/cv_dataset_core.py",
                "src/cv_dataset_generator.py",
                "src/validate_cv_dataset.py",
            ],
        ),
        (
            "Données et configuration",
            [
                "data/train_segments.csv",
                "data/raw/offres_france_travail.json",
                "data/processed/metier_context_t3_2025.csv",
                "config/formation_domains.json",
                "requirements.txt",
                "README.md",
            ],
        ),
        (
            "Tests",
            [
                "tests/test_web_app.py",
                "tests/test_user_portal.py",
                "tests/test_matching_service.py",
                "tests/test_trend_aggregation.py",
                "tests/test_cv_parser.py",
                "tests/test_cv_dataset_generator.py",
                "tests/test_validate_cv_dataset.py",
                "tests/test_formation_recommendation.py",
            ],
        ),
    ]


for section, files in iter_key_files():
    print(f"\n## {section}")
    for relative_path in files:
        path = PROJECT_ROOT / relative_path
        status = "✓" if path.exists() else "✗"
        print(f"  {status} {relative_path}")

# %% [markdown]
# ## 4. Les points d’entrée web
#
# Le projet expose deux applications Flask principales :
#
# - `python -m src.web_app` : tableau de bord principal, recherche d’offres,
#   tendances par territoire et intégration de l’espace utilisateur ;
# - `python -m src.comparison_web_app` : tableau de bord de comparaison entre
#   plusieurs sources d’offres.
#
# Le module `src.user_portal.py` complète cette architecture avec le profil
# utilisateur, l’édition des compétences et des formations, l’import de CV,
# les recommandations personnelles et les pages “Mon compte”.
#
# Ici, on n’ouvre pas le serveur Flask pour éviter d’introduire un effet de
# bord. Le but du notebook est d’expliquer le code, pas de lancer un service.

# %% [markdown]
# ## 5. Du texte brut à une offre exploitable
#
# Le pipeline d’extraction d’offres commence par des fonctions simples de
# prétraitement, puis ajoute des règles et un classifieur léger.
#
# Les deux fonctions les plus faciles à lire sont :
#
# - `src.preprocessing.clean_text`
# - `src.preprocessing.segment_offer`
#
# Elles servent à normaliser le texte et à le découper en segments avant la
# prédiction.

# %%
from src.preprocessing import clean_text, segment_offer


raw_offer = """Développeur Python Senior - job post
Entreprise Exemple
Lyon
De 40 000 € à 50 000 € par an - CDI
Compétences : Python, FastAPI, Docker, PostgreSQL
Télétravail partiel possible"""

cleaned_offer = clean_text(raw_offer)
segments = segment_offer(raw_offer)

print("Texte nettoyé :")
print(cleaned_offer)
print("\nSegments détectés :")
for index, segment in enumerate(segments, start=1):
    print(f"{index:02d}. {segment}")

# %% [markdown]
# ### Ce que l’on observe
#
# - le texte est rendu plus homogène ;
# - les retours de ligne, blancs et artefacts mineurs sont neutralisés ;
# - le texte est ensuite découpé en segments plus faciles à classer.
#
# Cette étape est importante parce que le modèle d’extraction ne travaille pas
# directement sur des fichiers bruts très hétérogènes.

# %% [markdown]
# ## 6. Préparation des caractéristiques pour le modèle 1
#
# Le module `src.feature_extraction` transforme les segments en variables
# numériques. Il combine :
#
# - une représentation TF-IDF ;
# - quelques indicateurs métiers simples.
#
# Le but n’est pas de construire un modèle “magique”, mais un pipeline court,
# lisible et reproductible.

# %%
from src.feature_extraction import build_feature_matrix, build_vectorizer


toy_texts = [
    "Développeur Python FastAPI Docker",
    "Rémunération attractive et poste en CDI",
    "Compétences : SQL, pandas, dataviz",
]

vectorizer = build_vectorizer(max_features=100)
feature_matrix = build_feature_matrix(vectorizer, toy_texts)

print("Nombre de textes :", len(toy_texts))
print("Dimension de la matrice :", feature_matrix.shape)

# %% [markdown]
# ## 7. Le modèle 1 en un coup d’œil
#
# Le fichier `src.train_classifier.py` orchestre :
#
# 1. le chargement du jeu de segments étiquetés ;
# 2. la vectorisation ;
# 3. l’entraînement du classifieur ;
# 4. l’évaluation ;
# 5. la sauvegarde du modèle dans `models/`.
#
# Le fichier `src.predict.py` reprend ensuite le pipeline pour prédire les
# étiquettes de segments sur une offre brute, puis applique les extracteurs
# métier du module `src.extractors.py`.
#
# Dans ce notebook, on ne ré-entraîne pas le modèle complet : on explique la
# chaîne d’ensemble et on reste sur des exemples de petite taille.

# %% [markdown]
# ## 8. Chargement des offres normalisées et tendances par territoire
#
# Les offres de production sont généralement lues depuis un snapshot local
# plutôt que directement depuis le réseau. La fonction
# `src.services.offer_repository.load_normalized_offers` renvoie :
#
# - une liste d’offres normalisées ;
# - ou un message d’erreur lisible si le fichier est absent ou invalide.
#
# À partir de ces offres, le projet calcule :
#
# - les 10 compétences les plus demandées ;
# - le volume d’offres ;
# - la période couverte ;
# - le détail des tendances par territoire.

# %%
from src.services.offer_repository import build_territory_trends_context, get_top_skills_by_territory, load_normalized_offers


raw_offers_path = PROJECT_ROOT / "data" / "raw" / "offres_france_travail.json"
if raw_offers_path.exists():
    loaded_offers, load_error = load_normalized_offers(raw_offers_path)
    print(f"Offres chargées depuis le snapshot local : {len(loaded_offers)}")
    print("Erreur :", load_error)
else:
    loaded_offers = demo_offers
    print("Snapshot local absent, utilisation du jeu de démonstration.")

top_skills = get_top_skills_by_territory(loaded_offers, territory="Lyon", limit=5)
trends_context = build_territory_trends_context(loaded_offers, territory="Lyon", limit=5)

print("\nTop compétences à Lyon :")
pretty(top_skills)

print("\nContexte de page pour les tendances :")
pretty(trends_context)

# %% [markdown]
# ### Point important
#
# L’agrégation ne se limite pas à compter des mots.
#
# Le code :
#
# - normalise les libellés ;
# - fusionne les variantes de casse ;
# - regroupe les compétences équivalentes ;
# - filtre les offres selon le territoire et la période ;
# - renvoie une structure stable pour l’interface Flask.

# %% [markdown]
# ## 9. Le moteur de matching utilisateur
#
# Le moteur de matching compare un profil à une offre et produit :
#
# - un score global ;
# - des sous-scores par critère ;
# - les compétences communes ;
# - les compétences manquantes ;
# - une explication lisible.
#
# Les pondérations sont configurables via `src.matching.weights`.

# %%
from src.matching.weights import DEFAULT_MATCHING_WEIGHTS, validate_matching_weights
from src.matching.scoring import calculate_weighted_score, build_scoring_result
from src.services.matching_service import compute_match


custom_weights, error = validate_matching_weights(DEFAULT_MATCHING_WEIGHTS)
print("Validation des pondérations :", error or "OK")

criterion_scores = {
    "competences": 0.8,
    "metier": 1.0,
    "experience": 0.5,
    "diplome": None,
    "localisation": 1.0,
    "contrat": 1.0,
    "teletravail": 0.0,
    "salaire": None,
}

weighted_score = calculate_weighted_score(criterion_scores, custom_weights)
scoring_result = build_scoring_result(
    criterion_scores,
    custom_weights,
    common_skills=["Python", "FastAPI"],
    missing_skills=["Kubernetes"],
    source="demo",
    url_originale="https://example.org/offre/1",
)

print(f"Score pondéré sur 100 : {weighted_score}")
print("\nRésultat détaillé :")
pretty(scoring_result)

matching_result = compute_match(demo_profile, demo_offers[0], weights=custom_weights)
print("\nExtrait du matching profil/offre :")
print("Score global :", matching_result.get("global_score"))
print("Résumé :", matching_result.get("explanation", {}).get("summary"))
print("Compétences communes :", matching_result.get("matching_skills"))

# %% [markdown]
# ### Comment lire ce résultat
#
# Le moteur essaie de rester explicable.
#
# Pour chaque critère, on distingue :
#
# - le **score** du critère ;
# - le **poids initial** ;
# - le **poids effectif** après neutralisation des critères absents ;
# - le **statut** du champ.
#
# Le score global final reste sur une échelle de 0 à 100, ce qui facilite
# l’affichage dans l’interface web.

# %% [markdown]
# ## 10. Recommandation de formation
#
# Le projet contient aussi une couche de recommandation pédagogique. Elle ne
# s’appuie pas sur un modèle génératif externe : elle convertit les tendances
# du marché en propositions de formation déterministes.
#
# Le service principal est `src.services.formation_recommendation.build_recommendation_context`.

# %%
from src.services.formation_recommendation import build_recommendation_context


recommendation_context = build_recommendation_context(demo_offers, territoire="Lyon", periode_jours=3650)
print("Clés du contexte :", sorted(recommendation_context.keys()))
print("\nRecommandation structurée :")
pretty(recommendation_context.get("recommendation", {}))

# %% [markdown]
# ### Ce que cette couche apporte
#
# Elle transforme des statistiques de marché en contenu pédagogique exploitable
# par une équipe formation ou un utilisateur final :
#
# - titre de formation ;
# - compétences cibles ;
# - public cible ;
# - prérequis ;
# - objectifs pédagogiques ;
# - modules ;
# - justification ;
# - limites.
#
# C’est un bon exemple de logique déterministe, testable et sans appel réseau.

# %% [markdown]
# ## 11. Comprendre le parseur de CV
#
# Le sous-système `src.cv_parser` a pour rôle de lire un CV texte et de le
# transformer en structure exploitable par le portail utilisateur.
#
# Il sépare notamment :
#
# - les formations ;
# - les compétences ;
# - les expériences professionnelles ;
# - les sections détectées ;
# - le texte brut conservé pour référence.
#
# Les composants principaux sont :
#
# - `section_detector.py` : détection des titres de section ;
# - `block_builder.py` : regroupement contextuel des lignes ;
# - `education_extractor.py` : extraction des formations ;
# - `experience_extractor.py` : extraction des expériences ;
# - `skill_extractor.py` : extraction des compétences ;
# - `parser.py` : orchestration de l’ensemble.

# %%
from src.cv_parser.parser import parse_cv_text


parsed_cv = parse_cv_text(demo_cv_text)
print("Formations extraites :", len(parsed_cv["formations"]))
print("Compétences extraites :", len(parsed_cv["competences"]))
print("Expériences extraites :", len(parsed_cv["experiences_professionnelles"]))
print("Sections détectées :", parsed_cv["sections_detectees"])

print("\nAperçu des formations :")
pretty(parsed_cv["formations"])

print("\nAperçu des compétences :")
pretty(parsed_cv["competences"])

print("\nAperçu des expériences :")
pretty(parsed_cv["experiences_professionnelles"])

# %% [markdown]
# ### Pourquoi le parseur est séparé en plusieurs modules
#
# Un CV n’est pas une simple liste de lignes.
#
# Le code du projet tient compte du contexte pour éviter les erreurs classiques
# :
#
# - interpréter un établissement comme un diplôme ;
# - découper une formation multiligne en plusieurs éléments ;
# - confondre loisirs et sections métier ;
# - perdre la relation entre une expérience et ses missions.
#
# La séparation en modules rend ces corrections plus faciles à tester.

# %% [markdown]
# ## 12. Le builder d’annotations du dataset synthétique
#
# Le projet inclut aussi un générateur de CV synthétiques, utile pour préparer
# un futur modèle NER.
#
# La brique centrale est `AnnotatedTextBuilder` : elle construit du texte en
# gardant les offsets exacts des entités annotées.

# %%
from src.cv_dataset_core import AnnotatedTextBuilder


builder = AnnotatedTextBuilder()
builder.append_entity("Jean Dupont", "NAME")
builder.newline()
builder.append_entity("Développeur Python", "JOB_TITLE")
builder.newline()
builder.append("Paris - ")
builder.append_entity("jean.dupont@example.org", "EMAIL")

generated_text, generated_entities = builder.build()

print("Texte généré :")
print(generated_text)
print("\nEntités :")
pretty(generated_entities)

assert generated_text[generated_entities[0]["start"]:generated_entities[0]["end"]] == generated_entities[0]["text"]

# %% [markdown]
# ## 13. Génération d’un petit dataset synthétique
#
# Le module `src.cv_dataset_generator` encapsule le générateur de CV
# synthétiques. Il permet :
#
# - de produire un dataset JSONL ;
# - d’exporter en format spaCy ;
# - d’exporter en format Hugging Face BIO ;
# - de découper les données en train / validation / test ;
# - de rester reproductible grâce à une graine.
#
# Ici, on génère un petit échantillon pour illustrer l’API.

# %%
from src.cv_dataset_generator import (
    convert_to_huggingface_records,
    convert_to_spacy_records,
    generate_dataset,
)


synthetic_records = generate_dataset(count=2, seed=42, noise_level=0)
print("Nombre de CV générés :", len(synthetic_records))
print("Première fiche synthétique :")
pretty(
    {
        "id": synthetic_records[0]["id"],
        "template": synthetic_records[0]["metadata"]["template"],
        "labels": [entity["label"] for entity in synthetic_records[0]["entities"][:5]],
    }
)

spacy_records = convert_to_spacy_records(synthetic_records[:1])
huggingface_records = convert_to_huggingface_records(synthetic_records[:1])

print("\nExport spaCy :")
pretty(spacy_records[0])

print("\nExport Hugging Face BIO :")
pretty(huggingface_records[0])

# %% [markdown]
# ## 14. Validation du dataset synthétique
#
# Le validateur vérifie les points essentiels :
#
# - JSON lisible ;
# - identifiants uniques ;
# - offsets cohérents ;
# - absence de chevauchements ;
# - labels autorisés ;
# - présence minimale de `NAME` et d’un moyen de contact sur la majorité des
#   CV.
#
# Il produit un rapport détaillé et retourne un code de sortie différent de 0
# si des anomalies sont détectées.

# %%
from src.validate_cv_dataset import ValidationReport, format_report, validate_records


validation_report = validate_records(synthetic_records)
print(format_report(validation_report))

# %% [markdown]
# ## 15. Ce qu’il faut retenir des modules principaux
#
# Pour naviguer efficacement dans le dépôt, retenez surtout :
#
# - `src.web_app.py` et `src.comparison_web_app.py` : points d’entrée Flask ;
# - `src.user_portal.py` : espace utilisateur, profil, CV, recommandations ;
# - `src.preprocessing.py` : nettoyage et segmentation des offres ;
# - `src.feature_extraction.py` et `src.train_classifier.py` : apprentissage du
#   classifieur de segments ;
# - `src.predict.py` et `src.extractors.py` : inférence et post-traitement ;
# - `src.offer_normalization.py` : schéma stable d’une offre normalisée ;
# - `src.trend_aggregation.py` et `src.services.offer_repository.py` :
#   agrégation des tendances ;
# - `src.matching/` et `src.services/matching_service.py` : score de matching
#   explicable ;
# - `src.services.formation_recommendation.py` : recommandation de formation ;
# - `src.cv_parser/` : import et structuration des CV ;
# - `src.cv_dataset_core.py`, `src.cv_dataset_generator.py`,
#   `src.validate_cv_dataset.py` : génération et contrôle des CV synthétiques.

# %% [markdown]
# ## 16. Dépendances externes et prérequis
#
# Le projet dépend de bibliothèques externes, mais elles restent classiques :
#
# - **Flask** pour l’interface web ;
# - **scikit-learn** pour le modèle de segmentation ;
# - **pandas** pour certains exports et agrégations ;
# - **joblib** pour la persistance du modèle ;
# - **requests** pour les appels à l’API France Travail ;
# - **Faker** pour la génération synthétique ;
# - **pypdf** et **python-docx** pour l’extraction de CV ;
# - **openpyxl** pour la lecture de classeurs Excel ;
# - **Flask-Login**, **Flask-WTF**, **Flask-SQLAlchemy** et
#   **Flask-Migrate** pour l’espace utilisateur.
#
# Aucun de ces composants n’est là pour “faire joli” : chacun correspond à un
# besoin concret du projet.

# %% [markdown]
# ## 17. Limites actuelles, erreurs possibles et pistes d’amélioration
#
# Ce projet est déjà structuré, mais il reste des limites réalistes :
#
# - la qualité du matching dépend de la qualité des données d’entrée ;
# - certaines offres peuvent être très incomplètes ou mal normalisées ;
# - le parsing de CV repose sur un mélange de règles et de heuristiques ;
# - la recommandation de formation est déterministe et donc prudente ;
# - les exports synthétiques sont utiles pour l’entraînement, mais ne valent
#   pas un vrai corpus annoté manuellement ;
# - l’interface reste volontairement légère, ce qui facilite la maintenance,
#   mais limite les interactions avancées.
#
# Pistes d’amélioration plausibles :
#
# - enrichir les jeux de tests sur les cas de bord ;
# - améliorer les normalisations métier ;
# - ajouter davantage de métriques d’évaluation ;
# - documenter encore mieux les formats JSON intermédiaires ;
# - renforcer la qualité des recommandations avec davantage de données
#   historiques réelles.

# %% [markdown]
# ## 18. Conversion en notebook Jupyter
#
# Une fois ce fichier enregistré, vous pouvez le convertir en `.ipynb` avec
# Jupytext :
#
# ```bash
# jupytext --to ipynb docs/notebook_projet.py -o docs/notebook_projet.ipynb
# ```
#
# Si vous souhaitez ouvrir directement le fichier `.py` dans un environnement
# compatible Jupytext, ce n’est même pas obligatoire : la plupart des outils
# savent lire ce format nativement.

