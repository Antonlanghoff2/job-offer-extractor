# job_offer_extractor

Extract structured information from raw French job-offer texts using a lightweight
machine-learning pipeline (scikit-learn). No LLM required.

Supported Python version: **Python >= 3.8**.

## Project structure

```
job_offer_extractor/
├── data/
│   ├── train_segments.csv    # Labelled segments for training
│   └── sample_offers.txt     # Raw example offers
├── models/                   # Persisted vectorizer + classifier (generated)
├── src/
│   ├── __init__.py
│   ├── preprocessing.py      # Text cleaning & segmentation
│   ├── feature_extraction.py # TF-IDF vectoriser + hand-crafted features
│   ├── train_classifier.py   # Training pipeline
│   ├── integrate_series_offres.py # France Travail aggregated series export
│   ├── trend_aggregation.py   # Reusable market trend aggregation core
│   ├── offer_normalization.py # Common schema for sources
│   ├── source_comparison.py   # France Travail vs Indeed comparison
│   ├── web_app.py            # France Travail dashboard
│   ├── comparison_web_app.py # France Travail / Indeed comparison dashboard
│   ├── extractors.py         # Rule-based post-processing
│   ├── predict.py            # Prediction API & CLI
│   ├── cv_dataset_core.py    # Synthetic CV generation / export / validation core
│   ├── cv_dataset_generator.py # Synthetic CV dataset CLI
│   ├── validate_cv_dataset.py # Synthetic CV dataset validator CLI
│   └── evaluate.py           # Evaluation & reporting
├── README.md
└── requirements.txt
```

## Quickstart

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Train the model
python -m src.train_classifier --csv data/train_segments.csv

# 3. Extract from sample offers
python -m src.predict data/sample_offers.txt --pretty
```


## Démarrage

Le projet a trois points d'entrée utiles au quotidien:

- `python -m src.import_offres` récupère les offres France Travail via l'API et écrit un snapshot local dans `data/raw/`.
- `python -m src.web_app` démarre le tableau de bord principal pour lire les offres France Travail, les tendances et le contexte marché.
- `python -m src.comparison_web_app` démarre le tableau de bord de comparaison France Travail / Indeed.

Ordre conseillé pour repartir d'un snapshot propre:

1. Renseigner `FRANCE_TRAVAIL_CLIENT_ID` et `FRANCE_TRAVAIL_CLIENT_SECRET` dans `.env` si tu veux interroger l'API.
2. Télécharger ou régénérer les offres:

```bash
python -m src.import_offres --output data/raw/offres_france_travail.json
```

3. Ouvrir le tableau de bord principal:

```bash
python -m src.web_app
```

4. Ouvrir le tableau de bord de comparaison:

```bash
python -m src.comparison_web_app
```

Par défaut, le tableau de bord principal écoute sur `http://127.0.0.1:8000` et le tableau de bord de comparaison sur `http://127.0.0.1:8001`.

## Labels

| Label      | Meaning                          |
|------------|----------------------------------|
| TITLE      | Job title                        |
| SALARY     | Salary range or compensation     |
| LOCATION   | City / region / workplace        |
| SKILLS     | Required technologies / tools    |
| CONTRACT   | Contract type (CDI, CDD, etc.)   |
| EXPERIENCE | Experience level required        |
| REMOTE     | Remote-work policy               |
| OTHER      | Miscellaneous information        |

## Evaluation

```bash
python -m src.evaluate --csv data/train_segments.csv
```


## France Travail market context

The workbook `data_external/france_travail_series/series_offres_diffusees_T42025.xlsx`
is an aggregated France Travail source about distributed job offers: monthly
series, contract types, domains and job families, including T3 2025 data. It is
not a corpus of raw job ads and must not be used to directly train the model 1
job-offer extraction classifier.

This source enriches model 2, the future training recommendation layer, with
market context. It does not replace raw job-offer examples used by model 1.
Until labelled recommendation outcomes exist, the pipeline only prepares an
empty future target column named `score_formation`; it does not train a
supervised model from invented labels.

Generate the processed CSV files with:

```bash
python -m src.integrate_series_offres
```

The command creates:

- `data/processed/contrat_long.csv`
- `data/processed/metier_context_t3_2025.csv`


## Génération du dataset de CV synthétiques

Cette fonctionnalité crée un corpus de CV français entièrement synthétiques, avec annotations NER, pour préparer l'entraînement d'un futur modèle d'extraction.

### Installation des dépendances

```bash
pip install -r requirements.txt
```

### Génération simple

```bash
python -m src.cv_dataset_generator
```

### Génération de 5000 CV

```bash
python -m src.cv_dataset_generator \
  --count 5000 \
  --output data/cv/synthetic_cv_dataset.jsonl \
  --seed 42
```

### Seed

L'option `--seed` rend le dataset reproductible à l'identique. Deux exécutions avec les mêmes paramètres produisent les mêmes CV, dans le même ordre.

### Templates

Les templates disponibles sont `classic`, `compact`, `technical`, `academic`, `creative`, `minimal` et `noisy_pdf`.

### Niveaux de bruit

L'option `--noise-level` accepte `0`, `1`, `2` et `3`.

- `0` : texte propre
- `1` : bruit léger
- `2` : bruit moyen
- `3` : bruit important, avec défauts proches d'une extraction PDF imparfaite

### Validation

```bash
python -m src.validate_cv_dataset \
  --input data/cv/synthetic_cv_dataset.jsonl
```

### Exports spaCy

```bash
python -m src.cv_dataset_generator \
  --count 100 \
  --format spacy \
  --output data/cv/test_spacy.jsonl
```

Le même dataset JSONL principal peut aussi être converti vers le format spaCy via la fonction `convert_jsonl_dataset_to_spacy`.

### Exports Hugging Face

```bash
python -m src.cv_dataset_generator \
  --count 100 \
  --format huggingface \
  --output data/cv/test_huggingface.jsonl
```

Le format Hugging Face exporte des tokens simples et des tags BIO de même longueur.

### Découpage train/validation/test

```bash
python -m src.cv_dataset_generator \
  --count 1000 \
  --split \
  --train-ratio 0.8 \
  --validation-ratio 0.1 \
  --test-ratio 0.1
```

Le découpage écrit `data/cv/train.jsonl`, `data/cv/validation.jsonl` et `data/cv/test.jsonl` dans le dossier cible dérivé de `--output`.

### Lancement des tests

```bash
pytest -q
```

Avertissement: les CV synthétiques ne doivent pas être utilisés seuls pour évaluer la qualité réelle du modèle. Une évaluation finale doit être réalisée sur un jeu de vrais CV anonymisés et annotés manuellement.

## License

Copyright Anton Langhoff <antonlanghoff@gmail.com>  
SPDX-License-Identifier: MIT

## Agrégation des tendances

Le module d'agrégation transforme des offres extraites et normalisées en
tendances marché exploitables par le modèle 2 de recommandation de formation.
La logique réutilisable vit dans `src/trend_aggregation.py` et la commande CLI
se trouve dans `scripts/aggregate_trends.py`.

Il fonctionne sur un flux ou une liste de JSON déjà structurés, filtre par
territoire et par fenêtre glissante en jours, puis calcule les fréquences de
compétences, métiers, niveaux et contrats.

Commande CLI:

```bash
python scripts/aggregate_trends.py \
  --input data/processed/offres_extraites.json \
  --territoire Lyon \
  --periode 30 \
  --output data/processed/tendances_lyon_30j.json
```

Le fichier sample `data/samples/offres_extraites_sample.json` permet de
valider le flux de bout en bout sans dépendre des données de production.



## Interface web

Le tableau de bord principal sert à lire les offres France Travail extraites,
les tendances calculées à partir de ces offres et le contexte marché T3 2025.
Il ne réentraîne rien: il agrège des données déjà normalisées et les rend
exploitables pour le modèle 2.

La recherche est désormais partagée par URL et fonctionne en GET. Les filtres
principaux sont:

- `mots_cles` pour le mot-clé métier ou technologique recherché
- `territoire_type` avec les valeurs `commune`, `departement`, `region` ou `all`
- `territoire` pour le code ou la valeur du territoire ciblé
- `distance` pour une recherche autour d'une commune
- `page` et `per_page` pour la pagination des cartes d'offres

Exemples d'URL:

```text
/?mots_cles=python&territoire_type=departement&territoire=75
/?mots_cles=data&territoire_type=commune&territoire=69123&distance=20
/?mots_cles=ia&territoire_type=region&territoire=84
/?mots_cles=python&territoire_type=all
```

Signification des codes:

- `commune`: code INSEE de commune, par exemple `69123`
- `departement`: code départemental, par exemple `75`
- `region`: code INSEE de région, par exemple `84`

La pagination conserve les filtres courants via `page` et `per_page`.
Le tableau affiche les statistiques, puis la section **Offres associées** avec
un bouton cliquable vers l'annonce d'origine quand l'URL est disponible.

Lancement:

```bash
python -m src.web_app
```

Par défaut, l'application écoute sur `http://127.0.0.1:8000`.
Si ce port est déjà pris, tu peux lancer un autre port avec `python -m src.web_app --port 8002`.

Lien direct vers la page d'accueil de recherche:

- [http://127.0.0.1:8000/](http://127.0.0.1:8000/)


## Ingestion API

Le collecteur France Travail interroge maintenant plusieurs requêtes métiers,
pagine par fenêtres `range` de 150 offres, fusionne les résultats et
supprime les doublons à partir de l'identifiant France Travail.

Le script `src/import_offres.py` accepte désormais :

- `--page-size` pour régler la taille des fenêtres API
- `--max-pages` pour limiter le nombre de pages par requête
- `--max-results` pour limiter le volume par requête
- `--territory-mode` pour activer la collecte sur les territoires prédéfinis
- `--territories` pour fournir une liste personnalisée de territoires

Exemple standard:

```bash
python -m src.import_offres --output data/raw/offres_france_travail.json
```

Exemple avec mode territoire:

```bash
python -m src.import_offres --territory-mode --output data/raw/offres_france_travail.json
```

## Comparaison France Travail / Indeed

Le tableau de bord de comparaison charge un export France Travail et un export
Indeed, puis affiche les écarts entre les deux sources. Il met en avant les
compétences communes, les compétences exclusives, les métiers et les contrats.
Le fichier Indeed doit être un JSON de liste, avec des champs proches de
`title`, `location`, `skills`, `contract` et `seniority`, ou déjà normalisé
dans le format commun.

Lancement du dashboard :

```bash
python -m src.comparison_web_app
```

Comparaison en ligne de commande :

```bash
python scripts/compare_sources.py \
  --france-travail data/raw/offres_france_travail.json \
  --indeed data/samples/offres_indeed_sample.json \
  --territoire Lyon \
  --periode 30 \
  --output data/processed/comparison_ft_indeed.json
```


## Espace utilisateur

TrendRadar IA inclut un espace privé pour gérer un profil professionnel, importer un CV et recevoir un classement déterministe des offres. Il est intégré aux deux applications Flask existantes, sans point d'entrée parallèle.

Routes principales:

- `/register`
- `/login`
- `/logout`
- `/profile`
- `/profile/skills`
- `/profile/diplomas`
- `/profile/experiences`
- `/profile/cv`
- `/profile/cv/validate`
- `/mes-offres`
- `/mes-offres/<offer_id>`
- `/dashboard-utilisateur`

### Installation

Les dépendances utilisateur et CV sont déclarées dans `requirements.txt`:

- `Flask-Login`
- `Flask-WTF`
- `Flask-SQLAlchemy`
- `Flask-Migrate`
- `pypdf`
- `python-docx`

Le portail actuel utilise SQLite et les sessions Flask directement, car le projet n'avait pas encore d'ORM ni d'infrastructure de migration active. `pypdf` et `python-docx` sont utilisés automatiquement lorsqu'ils sont installés; un parseur de repli garde les tests locaux indépendants de ces paquets.

```bash
pip install -r requirements.txt
```

### Base et migrations

Par défaut, la base SQLite est créée dans `instance/trendradar.sqlite` au démarrage de l'application.

Pour connecter une base utilisateurs locale: 

1. Copier `.env.example` vers `.env`.
2. Définir au minimum `SECRET_KEY`, `DATABASE_PATH` et `UPLOAD_FOLDER`.
3. Créer le dossier de stockage si besoin: `mkdir -p instance/uploads`.
4. Lancer une fois l'application pour créer le schéma: `python -m src.web_app`.
5. Si une base existait déjà avant l'ajout du portail, appliquer la migration SQL: 

```bash
sqlite3 instance/trendradar.sqlite < migrations/001_user_portal.sql
```

6. Redémarrer l'application et ouvrir `/register` pour créer le premier compte.

Initialisation automatique:

```bash
python -m src.web_app
```

Migration SQL versionnée disponible:

```bash
sqlite3 instance/trendradar.sqlite < migrations/001_user_portal.sql
```

La migration ajoute `contract_preference` pour les bases créées avant l'ajout du champ. Le helper `init_db()` applique aussi cette colonne de manière idempotente au démarrage.

### CV et uploads

Les CV sont stockés hors du dossier public dans `instance/uploads/` par défaut. Le chemin système n'est pas exposé dans l'interface.

Formats acceptés:

- PDF textuels
- DOCX

Taille maximale recommandée:

- 8 Mo par défaut via `MAX_CONTENT_LENGTH`

Le fichier importé passe d'abord par `/profile/cv/validate`. Les données détectées ne sont enregistrées qu'après confirmation utilisateur.

### Matching

Le score reste explicable et déterministe:

- compétences: 50 %
- métier ou intitulé: 15 %
- expérience: 10 %
- diplôme: 5 %
- localisation: 10 %
- contrat: 5 %
- télétravail: 5 %

Les champs absents dans une offre sont neutralisés plutôt que pénalisés. Les recommandations affichent le score global, les sous-scores, les compétences communes, les compétences manquantes, la source et l'URL originale lorsqu'elle existe.

### Lancement

```bash
python -m src.web_app
python -m src.comparison_web_app
```

Les deux applications partagent le même portail privé.

### Tests

```bash
python -m unittest discover -s tests -p 'test_*.py'
```

### Configuration locale

Le fichier `.env.example` documente les variables utiles:

- `SECRET_KEY`
- `DATABASE_PATH`
- `UPLOAD_FOLDER`
- `MAX_CONTENT_LENGTH`
- `FRANCE_TRAVAIL_CLIENT_ID`
- `FRANCE_TRAVAIL_CLIENT_SECRET`

### Données personnelles

Les profils et CV contiennent des données personnelles. Ne commite pas `instance/`, `instance/uploads/` ni une base SQLite locale. Le dossier d'upload et la base locale sont exclus par `.gitignore`.
