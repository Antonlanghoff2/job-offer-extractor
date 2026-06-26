# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

# %% [markdown]
# # Extraction des données des offres
#
# Ce notebook présente la logique métier de l'étape 3 du rafraîchissement
# TrendRadar IA: transformer une offre normalisée en offre enrichie, puis
# déterminer si cette extraction est réellement réutilisable.
#
# ## Objectif métier
#
# - extraire des compétences, diplômes, salaires et contacts depuis le texte
#   source d'une offre;
# - stocker une métadonnée de traçabilité pour éviter de confondre un simple
#   horodatage avec une extraction complète;
# - invalider les caches lorsque la version de l'extracteur change.
#
# ## Entrées
#
# - une liste d'offres normalisées au format JSON;
# - le texte source exploitable de chaque offre;
# - la version courante de l'extracteur.
#
# ## Sorties
#
# - un fichier `offres_enrichies.json`;
# - des statistiques de traitement;
# - des métadonnées `_extraction_metadata` exploitables par les étapes
#   suivantes du pipeline.
#
# ## Limites connues
#
# - une offre sans texte source est conservée mais non enrichie;
# - une extraction vide ne doit jamais être considérée comme valide;
# - le cache est versionné et doit être recalculé quand le schéma évolue.

# %%
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.jobs import extract_offer_data as extraction_job
from src.jobs.cache import CacheStore, compute_hash
from src.jobs.extract_offer_data import EXTRACTION_CACHE_VERSION, extraction_is_complete

# %% [markdown]
# ## Exemple minimal
#
# Le bloc suivant isole le module dans un répertoire temporaire pour montrer
# le comportement réel de `extract_all_offer_data` sans toucher aux fichiers
# du projet.

# %%
normalized_offers = [
    {
        "id": "offer-1",
        "description": "Développeur Python. Compétences: Python, SQL. CDI.",
        "intitule": "Développeur Python",
        "source": "France Travail",
    },
    {
        "id": "offer-2",
        "description": "",
        "intitule": "",
        "source": "France Travail",
    },
]

with tempfile.TemporaryDirectory() as tmp_dir:
    tmp_path = Path(tmp_dir)
    normalized_path = tmp_path / "offres_normalisees.json"
    enriched_path = tmp_path / "offres_enrichies.json"
    normalized_path.write_text(json.dumps(normalized_offers, ensure_ascii=False, indent=2), encoding="utf-8")

    extraction_job.NORMALIZED_OFFERS_PATH = normalized_path
    extraction_job.ENRICHED_OFFERS_PATH = enriched_path
    extraction_job.cache_store = CacheStore(tmp_path / "cache")

    stats = extraction_job.extract_all_offer_data()
    enriched = json.loads(enriched_path.read_text(encoding="utf-8"))

print(stats)
print(enriched[0]["_extraction_metadata"])
print(enriched[1]["id"])

# %% [markdown]
# ## Vérifier qu'une extraction est complète
#
# Une extraction n'est réutilisable que si elle est cohérente avec l'offre
# source, produite par la bonne version et réellement renseignée.

# %%
source_hash = compute_hash(normalized_offers[0])
complete_offer = {
    "id": "offer-1",
    "competences_requises_noms": ["Python"],
    "competences_requises_detaillees": [{"canonical_name": "Python"}],
    "diplomes_requis": [],
    "salaires": [],
    "contacts": [],
    "_extraction_metadata": {
        "extracted": True,
        "complete": True,
        "source_offer_id": "offer-1",
        "source_offer_hash": source_hash,
        "extraction_version": EXTRACTION_CACHE_VERSION,
        "extracted_at": "2026-06-26T00:00:00+00:00",
        "competences_count": 1,
        "competences_detaillees_count": 1,
        "diplomes_count": 0,
        "salaires_count": 0,
        "contacts_count": 0,
        "has_salary": False,
        "has_teletravail": False,
    },
}

print(extraction_is_complete(complete_offer, EXTRACTION_CACHE_VERSION))

# %% [markdown]
# ## Exemple de cache obsolète
#
# Si la version de l'extracteur change, le cache doit être recalculé même si
# le fichier existe encore sur disque.

# %%
obsolete_offer = {
    **complete_offer,
    "_extraction_metadata": {
        **complete_offer["_extraction_metadata"],
        "extraction_version": "1.0",
    },
}

print(extraction_is_complete(obsolete_offer, EXTRACTION_CACHE_VERSION))
