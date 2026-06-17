# Copyright Anton Langhoff

import json
import re
from pathlib import Path
from collections import Counter, defaultdict


INPUT_FILE = Path("data/raw/offres_france_travail.json")
OUTPUT_FILE = Path("data/processed/tendances.json")


COMPETENCES_REFERENTIEL = [
    "Python",
    "JavaScript",
    "SQL",
    "NoSQL",
    "FastAPI",
    "Django",
    "Flask",
    "React",
    "Docker",
    "Kubernetes",
    "Git",
    "Linux",
    "API",
    "Machine Learning",
    "Deep Learning",
    "NLP",
    "LLM",
    "RAG",
    "LangChain",
    "OpenAI",
    "Hugging Face",
    "TensorFlow",
    "PyTorch",
    "Pandas",
    "NumPy",
    "Scikit-learn",
    "Data Engineering",
    "MLOps",
    "Power BI",
    "Tableau",
]


def normalize_text(value: str) -> str:
    if not value:
        return ""
    return value.lower()


def detect_competences(text: str) -> list[str]:
    found = []

    text_lower = normalize_text(text)

    for competence in COMPETENCES_REFERENTIEL:
        pattern = r"\b" + re.escape(competence.lower()) + r"\b"
        if re.search(pattern, text_lower):
            found.append(competence)

    return found


def detect_niveau(text: str) -> str:
    text_lower = normalize_text(text)

    if any(word in text_lower for word in ["junior", "débutant", "debutant", "0 à 2 ans", "0-2 ans"]):
        return "junior"

    if any(word in text_lower for word in ["senior", "lead", "expert", "confirmé", "confirme", "5 ans", "7 ans"]):
        return "senior"

    if any(word in text_lower for word in ["intermédiaire", "intermediaire", "3 ans", "4 ans", "2 à 5 ans"]):
        return "intermediaire"

    return "non_precise"


def get_lieu(offre: dict) -> str:
    lieu = offre.get("lieuTravail", {})

    if isinstance(lieu, dict):
        return (
            lieu.get("commune")
            or lieu.get("libelle")
            or lieu.get("codePostal")
            or "non_precise"
        )

    return "non_precise"


def get_metier(offre: dict) -> str:
    return (
        offre.get("romeLibelle")
        or offre.get("intitule")
        or "non_precise"
    )


def analyse_tendances(offres: list[dict]) -> dict:
    competences_counter = Counter()
    metiers_counter = Counter()
    niveaux_counter = Counter()
    territoires_counter = Counter()

    details_offres = []

    for offre in offres:
        intitule = offre.get("intitule", "")
        description = offre.get("description", "")
        rome_libelle = offre.get("romeLibelle", "")

        texte_total = f"{intitule} {description} {rome_libelle}"

        competences = detect_competences(texte_total)
        niveau = detect_niveau(texte_total)
        metier = get_metier(offre)
        territoire = get_lieu(offre)

        competences_counter.update(competences)
        metiers_counter.update([metier])
        niveaux_counter.update([niveau])
        territoires_counter.update([territoire])

        details_offres.append({
            "id": offre.get("id"),
            "intitule": intitule,
            "metier": metier,
            "territoire": territoire,
            "niveau": niveau,
            "competences": competences,
        })

    return {
        "nombre_offres": len(offres),
        "competences": dict(competences_counter.most_common()),
        "metiers": dict(metiers_counter.most_common()),
        "niveau": dict(niveaux_counter.most_common()),
        "territoires": dict(territoires_counter.most_common()),
        "details_offres": details_offres,
    }


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Fichier introuvable : {INPUT_FILE}")

    with INPUT_FILE.open("r", encoding="utf-8") as f:
        offres = json.load(f)

    tendances = analyse_tendances(offres)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(tendances, f, ensure_ascii=False, indent=2)

    print(json.dumps(tendances, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()