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
python src/integrate_series_offres.py
```

The command creates:

- `data/processed/contrat_long.csv`
- `data/processed/metier_context_t3_2025.csv`

## License

Copyright Anton Langhoff <anton@langhoff.fr>  
SPDX-License-Identifier: MIT
