# job_offer_extractor

Extract structured information from raw French job-offer texts using a lightweight
machine-learning pipeline (scikit-learn). No LLM required.

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

## License

Copyright Anton Langhoff <anton@langhoff.fr>  
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

Lancement :

```bash
python -m src.web_app
```

Par défaut, l'application écoute sur `http://127.0.0.1:8000`.


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
