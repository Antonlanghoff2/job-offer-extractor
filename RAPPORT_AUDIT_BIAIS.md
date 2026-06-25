# Rapport d'audit — Biais métier du projet TrendRadar IA

**Date** : 24 juin 2026  
**Objectif** : Identifier les biais IA/Data et planifier la transformation en moteur générique multi-métiers

---

## 1. Biais identifiés

### 1.1 Collecte France Travail (`src/import_offres.py`)

**Problème** : Les 18 requêtes sont exclusivement centrées sur l'IA et la Data.

```python
REQUETES = [
    "intelligence artificielle",
    "machine learning",
    "deep learning",
    "data scientist",
    "data engineer",
    "data analyst",
    "developpeur IA",
    "ingenieur IA",
    "consultant IA",
    "machine learning engineer",
    "python",
    "llm",
    "rag",
    "langchain",
    "pytorch",
    "tensorflow",
    "nlp",
    "mlops",
]
```

**Impact** : 100% des offres collectées sont liées à l'IA/Data.

**Domaines absents** :
- Bâtiment (électricien, plombier, maçon, etc.)
- Santé (infirmier, médecin, aide-soignant, etc.)
- Commerce (vendeur, caissier, etc.)
- Industrie (opérateur, technicien, etc.)
- Transport (conducteur, livreur, etc.)
- Hôtellerie-restauration (cuisinier, serveur, etc.)
- Administration (assistant administratif, etc.)
- Éducation (enseignant, formateur, etc.)
- Agriculture (agriculteur, ouvrier agricole, etc.)
- Sécurité (agent de sécurité, gardien, etc.)
- Maintenance (technicien de maintenance, etc.)
- Artisanat (menuisier, couturier, etc.)
- Audiovisuel (régisseur, technicien son/lumière, etc.)
- Services (coiffeur, esthéticien, etc.)

### 1.2 Liste KNOWN_SKILLS (`src/extractors.py`)

**Problème** : 37 compétences dont ~80% sont techniques/informatiques.

**Compétences IA/Data surreprésentées** :
- Python, Django, Flask, FastAPI
- JavaScript, TypeScript, React, Vue
- SQL, PostgreSQL, MySQL
- Docker, Git, Linux, AWS, Azure
- Machine Learning, scikit-learn, PyTorch, TensorFlow
- Pandas, NumPy
- IA, intelligence artificielle, machine learning, deep learning
- LLM, RAG, LangChain, NLP, MLOps

**Compétences génériques présentes** (minoritaires) :
- Gestion de projet, pilotage projet
- Qualité, coûts, délais
- Relation client
- Anglais professionnel

**Compétences sectorielles absentes** :
- Bâtiment : lecture de plans, câblage électrique, maçonnerie, etc.
- Santé : soins infirmiers, diagnostic médical, etc.
- Commerce : techniques de vente, gestion de caisse, etc.
- Industrie : conduite de machines, contrôle qualité, etc.
- Transport : conduite de véhicules, logistique, etc.
- Restauration : préparation de repas, hygiène alimentaire, etc.

### 1.3 Dictionnaire NER (`src/ner/skill_dictionary.py`)

**Problème** : 98 compétences dont ~70% sont informatiques.

**Catégories dominantes** :
- programmation (Python, PHP, Java, C++, etc.)
- frontend (JavaScript, TypeScript, React, Vue, etc.)
- backend (Symfony, Flask, FastAPI, Django, etc.)
- data (SQL, PostgreSQL, MySQL, NoSQL, etc.)
- ia (Machine learning, Deep learning, NLP, LLM, etc.)
- data_science (scikit-learn, Pandas, NumPy, PyTorch, TensorFlow)

**Catégories sous-représentées** :
- spectacle (Régie son, DMX, ArtNet) — seulement 3 entrées
- management (Gestion de projet, Cahier des charges) — seulement 2 entrées

**Catégories absentes** :
- bâtiment
- santé
- commerce
- industrie
- transport
- hôtellerie-restauration
- administration
- éducation
- agriculture
- sécurité
- maintenance
- artisanat

### 1.4 Référentiel de compétences (`data/referentials/skills.json`)

**État actuel** : Le fichier existe mais contient principalement des compétences techniques informatiques.

**Structure** :
```json
{
  "canonical_name": "Python",
  "category": "Langages",
  "aliases": ["python", "python3", ...],
  "description": "..."
}
```

**Problème** : Pas de champ `domains` pour rattacher une compétence à des secteurs métiers.

### 1.5 Catégories historiques

**Fichiers concernés** :
- `src/trend_aggregation.py`
- `src/services/matching_service.py`
- `src/web_app.py`

**Catégories IA/Data** :
- Machine Learning
- Deep Learning
- NLP
- Data Engineering
- MLOps
- BI (Business Intelligence)

**Impact** : Les tableaux de bord affichent uniquement ces catégories.

### 1.6 Dataset d'entraînement

**Fichier** : `data/raw/jobs_dataset.csv`

**Problème** : Probablement dominé par des offres IA/Data (à vérifier).

**Action requise** :
- Analyser la distribution par domaine
- Créer un dataset équilibré
- Ajouter une colonne `domain`

### 1.7 Tests

**Fichiers** : `tests/test_*.py`

**Problème** : Les exemples de tests utilisent principalement des offres IA/Data.

**Exemples** :
- "Développeur Python"
- "Data Scientist"
- "Ingénieur IA"

**Métiers absents des tests** :
- Infirmier
- Électricien
- Vendeur
- Cuisinier
- Technicien de maintenance
- Assistant administratif
- Conducteur
- etc.

---

## 2. Composants génériques (réutilisables)

### 2.1 Architecture Flask
- Routes et templates : génériques
- Système de cache : générique
- Précalcul : générique

### 2.2 Normalisation des offres
- `src/offer_normalization.py` : générique
- `src/services/offer_normalization.py` : générique

### 2.3 Client France Travail
- `src/france_travail_client.py` : générique
- Pagination et déduplication : génériques

### 2.4 Matching
- `src/services/matching_service.py` : partiellement générique
- Critères de matching : à adapter (télétravail, permis, habilitations)

### 2.5 Extraction de compétences
- `src/skill_extraction/` : partiellement générique
- Pipeline d'extraction : générique
- Dictionnaire de compétences : à étendre

---

## 3. Composants à refactoriser

### 3.1 Collecte (`src/import_offres.py`)
**Action** : Remplacer les requêtes IA par une configuration multi-métiers.

### 3.2 Référentiel de compétences
**Action** :
- Ajouter des compétences multi-sectorielles
- Ajouter un champ `domains` pour chaque compétence
- Créer des catégories génériques

### 3.3 Classification domaine/métier
**Action** : Créer un module pour identifier le domaine et le métier à partir de l'offre.

### 3.4 Extraction générique
**Action** :
- Détecter les compétences explicites et implicites
- Détecter les outils, machines, matériaux
- Détecter les diplômes, certifications, habilitations, permis
- Détecter les contraintes physiques ou horaires

### 3.5 Matching générique
**Action** :
- Ajouter des critères spécifiques (permis, habilitations, certifications)
- Gérer les critères non applicables (télétravail pour un métier de chantier)
- Ne pas attribuer un score nul à un critère non applicable

### 3.6 Tableaux de bord
**Action** :
- Ajouter un filtre par domaine
- Ajouter un filtre par métier
- Afficher le volume d'offres par domaine
- Afficher les top compétences par domaine

### 3.7 Dataset d'entraînement
**Action** :
- Analyser la distribution actuelle
- Créer un dataset équilibré par domaine
- Ajouter une colonne `domain`

### 3.8 Tests
**Action** : Ajouter des tests pour au moins 10 métiers différents.

---

## 4. Plan de migration

### Phase 1 — Infrastructure (Semaine 1)
1. Créer `config/job_domains.json` avec 15+ domaines
2. Modifier `src/import_offres.py` pour utiliser la configuration
3. Créer `src/domain_classifier.py` pour classifier les offres
4. Étendre `data/referentials/skills.json` avec des compétences multi-sectorielles

### Phase 2 — Extraction (Semaine 2)
5. Modifier `src/skill_extraction/` pour détecter les compétences génériques
6. Ajouter la détection des outils, machines, matériaux
7. Ajouter la détection des diplômes, certifications, habilitations, permis
8. Ajouter la détection des contraintes physiques ou horaires

### Phase 3 — Matching (Semaine 3)
9. Modifier `src/services/matching_service.py` pour gérer les critères non applicables
10. Ajouter des critères spécifiques (permis, habilitations, certifications)
11. Adapter les pondérations pour différents types de métiers

### Phase 4 — Interface (Semaine 4)
12. Modifier les tableaux de bord pour afficher les filtres domaine/métier
13. Ajouter des statistiques par domaine
14. Conserver un tableau de bord spécialisé IA comme vue filtrée

### Phase 5 — Tests et validation (Semaine 5)
15. Ajouter des tests pour 10+ métiers différents
16. Valider la distribution du dataset
17. Documenter la migration

---

## 5. Critères de succès

1. La collecte n'est plus limitée à l'IA
2. Le référentiel couvre au moins 15 domaines
3. L'extraction fonctionne sur au moins 10 familles de métiers
4. Le matching ne suppose pas un profil informatique
5. Les critères non applicables sont distingués des critères absents
6. Les tableaux de bord permettent un filtre métier et domaine
7. Le dataset est contrôlé contre les déséquilibres
8. Les anciennes fonctionnalités IA restent disponibles comme spécialisation
9. Les tests passent
10. Un rapport avant/après montre la diversité des métiers analysés

---

## 6. Risques et mitigations

### Risque 1 : Perte de qualité sur l'IA
**Mitigation** : Conserver l'IA comme domaine spécialisé, pas comme modèle général.

### Risque 2 : Complexité accrue
**Mitigation** : Utiliser une configuration externe (JSON) pour les domaines et compétences.

### Risque 3 : Performance dégradée
**Mitigation** : Conserver le précalcul, ne pas ajouter de calculs lourds dans les routes.

### Risque 4 : Rupture de compatibilité
**Mitigation** : Conserver les anciennes fonctions, ajouter une version de schéma.

---

## 7. Conclusion

Le projet est fortement biaisé vers l'IA/Data à tous les niveaux : collecte, extraction, matching, tableaux de bord, tests.

La transformation en moteur générique multi-métiers nécessite une refactorisation complète de la collecte, du référentiel de compétences, de l'extraction, du matching et des tableaux de bord.

L'architecture Flask et le système de précalcul sont génériques et peuvent être conservés.

La migration doit être progressive pour éviter les ruptures de compatibilité et conserver la qualité sur l'IA tout en ajoutant le support d'autres domaines.
