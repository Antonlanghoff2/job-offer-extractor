# AGENTS.md — Règles de développement TrendRadar IA

## Langue

* Toute la documentation destinée aux développeurs doit être rédigée en français.
* Les noms de classes, fonctions et variables peuvent rester en anglais lorsqu’ils correspondent aux conventions du projet.
* Les explications doivent être compréhensibles par une personne découvrant le projet.

## Documentation obligatoire du code

Lors de toute création ou modification de code Python, Codex doit systématiquement :

1. Ajouter une docstring à chaque module important.
2. Ajouter une docstring à chaque classe publique.
3. Ajouter une docstring à chaque fonction ou méthode publique.
4. Documenter les paramètres, les valeurs de retour et les exceptions.
5. Expliquer le rôle métier du code, pas uniquement son fonctionnement technique.
6. Ajouter des commentaires uniquement lorsqu’ils expliquent une décision non évidente.
7. Éviter les commentaires qui répètent littéralement le code.

Utiliser autant que possible le format de docstring Google :

```python
def calculate_match_score(profile: UserProfile, offer: JobOffer) -> float:
    """Calcule la compatibilité entre un profil et une offre d’emploi.

    Le score combine les compétences, les formations, les expériences
    professionnelles et les préférences territoriales de l’utilisateur.

    Args:
        profile: Profil utilisateur normalisé.
        offer: Offre d’emploi à comparer au profil.

    Returns:
        Score de compatibilité compris entre 0.0 et 1.0.

    Raises:
        ValueError: Si le profil ou l’offre ne contient aucune compétence.
    """
```

## Documentation pédagogique exportable vers Jupyter

Tout nouveau module important doit pouvoir être présenté dans un notebook Jupyter.

Pour chaque fonctionnalité importante, la documentation doit permettre d’identifier :

* l’objectif métier ;
* les données d’entrée ;
* les données de sortie ;
* les principales étapes de traitement ;
* les dépendances utilisées ;
* un exemple minimal d’utilisation ;
* les erreurs possibles ;
* les limites connues.

Les exemples doivent être courts, autonomes et exécutables autant que possible.

## Marqueurs de documentation

Lorsqu’un fichier Python contient un déroulement pédagogique pertinent, utiliser les marqueurs Jupytext :

```python
# %% [markdown]
# ## Titre de la section
#
# Explication pédagogique en français.

# %%
result = execute_example()
```

Ne pas ajouter ces marqueurs dans tous les fichiers métier.

Les marqueurs Jupytext sont réservés aux fichiers situés dans :

```text
docs/notebooks/
```

Le code de production situé dans `src/` doit rester organisé comme du code Python classique.

## Structure recommandée

```text
src/
    services/
    models/
    parsers/
    matching/

docs/
    notebooks/
        architecture_projet.py
        parsing_cv.py
        matching_offres.py
    generated/

scripts/
    generate_notebooks.py
```

Les fichiers de `docs/notebooks/` doivent importer le code réel depuis `src/`.

Ne pas dupliquer les algorithmes de production dans les notebooks.

## Export vers Jupyter

Les fichiers pédagogiques doivent être compatibles avec Jupytext.

Commande d’export :

```bash
jupytext --to ipynb docs/notebooks/*.py
```

Lorsque Codex ajoute ou modifie une fonctionnalité importante, il doit :

1. mettre à jour les docstrings du code concerné ;
2. mettre à jour le notebook pédagogique correspondant ;
3. ajouter un exemple d’utilisation représentatif ;
4. vérifier que les imports sont valides ;
5. vérifier que le notebook peut être exécuté dans l’ordre ;
6. ne jamais inclure de secret, clé API ou donnée personnelle dans le notebook.

## Synchronisation du code et de la documentation

Une modification est considérée comme incomplète lorsque :

* une fonction publique a changé sans mise à jour de sa docstring ;
* le comportement documenté ne correspond plus au code ;
* un exemple utilise une ancienne API ;
* une fonctionnalité importante n’est représentée dans aucun notebook ;
* le notebook du module concerné ne peut plus être exécuté.

## Tests documentaires

Lorsque cela est pertinent, les exemples simples des docstrings doivent être compatibles avec `doctest`.

Avant de terminer une tâche documentaire, exécuter si possible :

```bash
python -m compileall src docs/notebooks
python -m doctest chemin/du/module.py
jupytext --to ipynb docs/notebooks/*.py
```

## Règles de qualité

* Ne jamais inventer le comportement d’une fonction.
* Lire l’implémentation et les tests avant de la documenter.
* Signaler clairement les comportements incertains.
* Ne pas présenter une hypothèse comme une fonctionnalité existante.
* Préférer une documentation courte et exacte à une documentation longue et fausse.
* Respecter le copyright suivant dans tout nouveau fichier :

```text
Copyright Anton Langhoff
```

## Fin de tâche

À la fin de chaque intervention, Codex doit indiquer :

* les fichiers de code modifiés ;
* les fichiers de documentation modifiés ;
* les notebooks créés ou actualisés ;
* les commandes de validation exécutées ;
* les éventuelles parties qui restent non documentées.


## Mise à jour obligatoire des notebooks

À chaque création ou modification d’une fonctionnalité importante dans `src/`,
Codex doit obligatoirement :

1. Identifier le notebook correspondant dans `docs/notebooks/`.
2. Le créer s’il n’existe pas.
3. Mettre à jour ses explications en français.
4. Ajouter ou actualiser un exemple exécutable utilisant le vrai code de `src/`.
5. Ne jamais recopier l’implémentation complète dans le notebook.
6. Importer les fonctions et classes directement depuis `src/`.
7. Générer ou régénérer le fichier `.ipynb` avec Jupytext.
8. Vérifier que le notebook s’exécute dans l’ordre.
9. Considérer la tâche comme incomplète si le code a changé mais que le
   notebook correspondant n’a pas été mis à jour.

Correspondances principales :

- `src/cv_parser/` → `docs/notebooks/cv_parser.py`
- `src/matching/` → `docs/notebooks/matching_offres.py`
- `src/job_extractor/` → `docs/notebooks/extraction_offres.py`
- `src/models/` → `docs/notebooks/modeles_ia.py`
- `src/web_app.py` → `docs/notebooks/interface_web.py`

Les notebooks pédagogiques doivent importer le vrai code :

```python
from src.matching.matcher import calculate_match
