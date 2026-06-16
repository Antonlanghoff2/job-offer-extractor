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

## License

Copyright Anton Langhoff <anton@langhoff.fr>  
SPDX-License-Identifier: MIT
