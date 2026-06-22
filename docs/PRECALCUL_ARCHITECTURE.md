# Architecture de Précalcul TrendRadar IA

## Vue d'ensemble

TrendRadar IA utilise maintenant une architecture de précalcul pour éviter les calculs lourds lors des requêtes HTTP. Toutes les données sont précalculées et mises en cache.

## Architecture

```
src/jobs/
├── __init__.py              # Package initialization
├── cache.py                 # Système de cache persistant
├── locking.py               # Verrouillage pour éviter les exécutions simultanées
├── status.py                # Suivi de l'état des tâches
├── import_offers.py         # Import des offres France Travail
├── normalize_offers.py      # Normalisation des offres
├── extract_offer_data.py    # Extraction des compétences, diplômes, salaires
├── aggregate_trends.py      # Agrégation des tendances
├── compute_dashboards.py    # Calcul des tableaux de bord
├── compute_matches.py       # Calcul des matchings utilisateur
└── refresh_all.py           # Orchestration complète
```

## Flux de données

```
1. Import des offres (France Travail API)
   ↓
2. Normalisation (offre_normalization.py)
   ↓
3. Extraction (predict.py + skill_extraction)
   - Compétences (explicites, sémantiques, implicites)
   - Diplômes
   - Salaires
   - Télétravail
   ↓
4. Agrégation des tendances
   - Par territoire
   - Globales
   ↓
5. Calcul des dashboards
   - Top compétences
   - Top métiers
   - Top contrats
   ↓
6. Calcul des matchings
   - Pour chaque utilisateur
   - Pour chaque offre
```

## Fichiers générés

```
data/
├── raw/
│   └── offres_france_travail.json      # Offres brutes
├── processed/
│   ├── offres_normalisees.json         # Offres normalisées
│   ├── offres_enrichies.json           # Offres avec données extraites
│   ├── trends.json                     # Tendances agrégées
│   ├── dashboards.json                 # Données des tableaux de bord
│   └── matches.json                    # Matchings utilisateur
├── cache/
│   └── *.json                          # Cache des calculs intermédiaires
├── status/
│   ├── tasks_status.json               # Statut des tâches
│   └── errors.log                      # Log des erreurs
└── locks/
    └── *.lock                          # Verrous d'exécution
```

## Exécution

### Exécution manuelle

```bash
# Exécuter toutes les étapes
python -m src.jobs.refresh_all

# Exécuter une étape spécifique
python -m src.jobs.import_offers
python -m src.jobs.normalize_offers
python -m src.jobs.extract_offer_data
python -m src.jobs.aggregate_trends
python -m src.jobs.compute_dashboards
python -m src.jobs.compute_matches
```

### Exécution automatique (systemd)

```bash
# Installer les services
sudo bash deploy/install_services.sh

# Vérifier le statut
sudo systemctl status trendradar-refresh.timer
sudo systemctl status trendradar-refresh.service

# Voir les logs
sudo journalctl -u trendradar-refresh.service -f

# Arrêter/démarrer le timer
sudo systemctl stop trendradar-refresh.timer
sudo systemctl start trendradar-refresh.timer
```

Le timer exécute le rafraîchissement toutes les 5 minutes.

## Invalidation du cache

Le cache est invalidé automatiquement lorsque :

1. **Offres** : Le hash des offres change (nouvelles offres, offres modifiées)
2. **Profils** : Le hash du profil utilisateur change
3. **Modèles** : La version du modèle change
4. **Référentiels** : La version du référentiel change

### Invalidation manuelle

```python
from src.jobs.cache import cache_store

# Invalider toutes les entrées d'un type
cache_store.invalidate_by_prefix("offer_extraction:")

# Invalider tout le cache
cache_store.clear_all()
```

## Statut des tâches

```python
from src.jobs.status import task_status

# Vérifier si une tâche est en cours
if task_status.is_task_running("refresh_all"):
    print("Rafraîchissement en cours")

# Obtenir le statut d'une tâche
status = task_status.get_task_status("extract_offer_data")
print(f"Statut: {status['status']}")
print(f"Démarré: {status['started_at']}")
print(f"Terminé: {status['completed_at']}")

# Obtenir les erreurs récentes
errors = task_status.get_recent_errors(limit=10)
for error in errors:
    print(f"{error['timestamp']}: {error['task']} - {error['error']}")
```

## Verrouillage

Le système de verrouillage empêche les exécutions simultanées :

```python
from src.jobs.locking import FileLock, LockError

# Utilisation avec context manager
try:
    with FileLock("my_task"):
        # Exécuter la tâche
        pass
except LockError:
    print("Tâche déjà en cours")

# Utilisation manuelle
lock = FileLock("my_task")
if lock.acquire(blocking=False):
    try:
        # Exécuter la tâche
        pass
    finally:
        lock.release()
else:
    print("Tâche déjà en cours")
```

## Performance

### Avant précalcul

- Chaque requête HTTP :
  - Appelle l'API France Travail
  - Normalise toutes les offres
  - Extrait les compétences (NLP lourd)
  - Calcule les matchings
  - Agrège les tendances
- Temps de réponse : 10-30 secondes
- Charge CPU : Élevée

### Après précalcul

- Les requêtes HTTP lisent uniquement le cache
- Temps de réponse : < 1 seconde
- Charge CPU : Minimale
- Rafraîchissement automatique toutes les 5 minutes

## Monitoring

### Logs

```bash
# Logs de rafraîchissement
tail -f logs/refresh.log

# Logs d'erreurs
tail -f logs/refresh.error.log

# Logs systemd
sudo journalctl -u trendradar-refresh.service -f
```

### Statistiques

```python
from src.jobs.cache import cache_store
from src.jobs.status import task_status

# Statistiques du cache
cache_status = cache_store.get_status()
print(f"Entrées: {cache_status['total_entries']}")
print(f"Taille: {cache_status['total_size_bytes']} bytes")

# Statut des tâches
all_status = task_status.get_all_status()
for task_name, status in all_status['tasks'].items():
    print(f"{task_name}: {status['status']}")
```

## Dépannage

### Le rafraîchissement ne s'exécute pas

```bash
# Vérifier le statut du timer
sudo systemctl status trendradar-refresh.timer

# Vérifier les logs
sudo journalctl -u trendradar-refresh.service -n 50

# Vérifier les verrous
ls -la data/locks/

# Supprimer un verrou bloqué
rm data/locks/refresh_all.lock
```

### Les données ne sont pas à jour

```python
from src.jobs.cache import cache_store

# Vérifier le statut du cache
status = cache_store.get_status()
print(f"Dernière mise à jour: {status['newest_entry']}")

# Forcer le rafraîchissement
cache_store.clear_all()
```

### Erreurs d'extraction

```bash
# Voir les erreurs récentes
tail -n 50 data/status/errors.log

# Voir le statut des tâches
cat data/status/tasks_status.json | python -m json.tool
```

## Tests

```bash
# Tests du cache
pytest tests/test_cache.py -v

# Tests du verrouillage
pytest tests/test_locking.py -v

# Tests du statut
pytest tests/test_status.py -v

# Tous les tests
pytest tests/ -v
```

## Copyright

Copyright Anton Langhoff
