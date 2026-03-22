# Guide de contribution

## Prérequis

- Python 3.10, 3.11 ou 3.12
- Docker + Docker Compose (pour les tests d'intégration et le développement)
- Git

## Mise en place de l'environnement de développement

```bash
# 1. Cloner le dépôt
git clone https://github.com/guepardlover77/gradio-amc.git
cd gradio-amc/docker-gradio-amc

# 2. Créer un environnement virtuel
python -m venv .venv
source .venv/bin/activate      # Linux/macOS
# ou
.venv\Scripts\activate         # Windows

# 3. Installer les dépendances
pip install -r requirements.txt -r requirements-test.txt
```

<!-- AUTO-GENERATED -->
## Commandes disponibles

| Commande | Description |
|----------|-------------|
| `docker compose up -d` | Démarrer l'application en arrière-plan |
| `docker compose down` | Arrêter l'application |
| `docker compose build` | Reconstruire l'image Docker |
| `docker compose logs -f` | Suivre les logs en temps réel |
| `./install.sh` | Installation complète (Docker + build + démarrage) |
| `pytest tests/ -m "not slow"` | Lancer les tests unitaires |
| `pytest tests/ -m "not slow" --cov=. --cov-report=term` | Tests + couverture |
| `pytest tests/ -m "slow and docker"` | Tests d'intégration Docker |
| `python -m py_compile app.py` | Vérifier la syntaxe d'un fichier |

<!-- END AUTO-GENERATED -->

## Lancer les tests

```bash
# Tests rapides (recommandé pendant le développement)
pytest tests/ -m "not slow" -v

# Tests d'un fichier spécifique
pytest tests/test_app.py -v

# Tests d'une classe spécifique
pytest tests/test_app.py::TestCompileDocument -v

# Tests avec couverture complète
pytest tests/ -m "not slow" --cov=. --cov-report=html:htmlcov
# → ouvrir htmlcov/index.html dans un navigateur

# Tests d'intégration Docker (démon Docker requis)
pytest tests/ -m "slow and docker" -v
```

<!-- AUTO-GENERATED -->
### Markers pytest

| Marker | Description | Commande pour inclure |
|--------|-------------|----------------------|
| *(aucun)* | Tests unitaires standards | `pytest tests/` |
| `slow` | Tests lents (intégration Docker) | `pytest tests/ -m slow` |
| `docker` | Tests nécessitant un démon Docker | `pytest tests/ -m docker` |

<!-- END AUTO-GENERATED -->

## Écrire de nouveaux tests

Les tests sont dans `tests/`. Chaque module a son fichier dédié :

```
tests/
├── conftest.py                    # Fixtures partagées (project_dir, capture_db, scoring_db…)
├── test_app.py                    # Tests backend Gradio
├── test_gradio_ui.py              # Tests structure UI
├── test_standard_mode.py          # Tests mode Standard
├── test_amc_wrapper.py            # Tests wrapper CLI AMC
├── test_amc_database.py           # Tests bases SQLite
├── test_amc_project.py            # Tests gestion projets
├── test_docker.py                 # Tests config Docker (sans démon)
├── test_docker_integration.py     # Tests intégration Docker
└── test_verification_integration.py  # Tests workflow vérification
```

Les fixtures `project_dir`, `capture_db`, `scoring_db`, `all_dbs` sont disponibles via `conftest.py` sans import.

## Structure du code

```
app.py               ← Point d'entrée Gradio (build_ui, handlers)
standard_mode.py     ← Mode Standard (navigate_step, build_standard_ui)
amc_wrapper.py       ← Appels subprocess à la CLI AMC
amc_project.py       ← CRUD projets (create_new, import_existing, list_projects)
amc_database.py      ← Lecture SQLite (capture, scoring, association, layout)
```

## Soumettre une contribution

1. Créer une branche depuis `master` : `git checkout -b feat/ma-fonctionnalite`
2. Écrire les tests correspondants
3. Vérifier que tous les tests passent : `pytest tests/ -m "not slow"`
4. Pousser et ouvrir une Pull Request vers `master`

### Checklist PR

- [ ] Les tests passent localement (`pytest tests/ -m "not slow"`)
- [ ] Les nouveaux comportements sont testés
- [ ] La syntaxe est valide (`python -m py_compile app.py`)
- [ ] Le README est à jour si nécessaire
