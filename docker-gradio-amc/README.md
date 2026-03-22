# Gradio-AMC

Interface web pour [Auto Multiple Choice](https://www.auto-multiple-choice.net/) (AMC), tournant dans un conteneur Docker.

AMC ne fonctionne que sous Linux. Gradio-AMC le fait tourner dans Docker et expose une interface web accessible depuis n'importe quel OS — y compris Windows et macOS.

## Fonctionnalités

- **Mode Standard** — workflow guidé en 6 étapes avec barre de progression
- **Mode Avancé** — 8 onglets pour un contrôle complet
- Édition du source LaTeX des QCM
- Génération des sujets PDF avec visualisation intégrée
- Import et analyse des copies scannées (OMR)
- Vérification et correction manuelle case par case
- Association des copies aux étudiants
- Notation automatique avec corrigé-type
- Export des résultats (CSV, ODS, XLSX)
- Gestion multi-projets avec import/export ZIP

## Prérequis

- Un OS (Linux, macOS, Windows)
- Internet (pour l'installation initiale)

Docker et Docker Compose sont installés automatiquement par le [script d'installation](./install.sh) si nécessaire.

## Installation rapide

```bash
chmod +x install.sh
./install.sh
```

Le script :
1. Détecte l'OS (Debian/Ubuntu, Fedora, Arch, macOS)
2. Installe Docker et Docker Compose si absents
3. Ajoute l'utilisateur courant au groupe `docker` (Linux)
4. Construit l'image Docker
5. Démarre le conteneur

L'interface est ensuite accessible sur **http://localhost:7860**.

## Démarrage manuel

Si Docker est déjà installé :

```bash
docker compose up -d        # démarrer en arrière-plan
docker compose down         # arrêter
docker compose logs -f      # voir les logs en temps réel
```

<!-- AUTO-GENERATED -->
## Structure du projet

| Fichier | Description |
|---------|-------------|
| `app.py` | Interface Gradio — 8 onglets + mode Standard |
| `standard_mode.py` | Mode Standard (workflow guidé 6 étapes) |
| `amc_wrapper.py` | Wrapper subprocess pour la CLI AMC |
| `amc_project.py` | Gestion des projets AMC (CRUD, ZIP import/export) |
| `amc_database.py` | Lecture des bases SQLite AMC (capture, scoring, association) |
| `Dockerfile` | Image Ubuntu 22.04 + AMC + TeXLive + Gradio |
| `docker-compose.yml` | Orchestration Docker (port 7860, volume `/projects`) |
| `install.sh` | Script d'installation automatique multi-OS |
| `requirements.txt` | Dépendances Python runtime |
| `requirements-test.txt` | Dépendances Python pour les tests |
| `pytest.ini` | Configuration pytest (markers `slow`, `docker`) |

<!-- END AUTO-GENERATED -->

## Données

Les projets sont stockés dans `projects/` (monté comme volume Docker à `/projects`). Ce dossier est ignoré par Git — vos données restent locales.

<!-- AUTO-GENERATED -->
## Variables d'environnement

| Variable | Requis | Défaut | Description |
|----------|--------|--------|-------------|
| `AMC_PROJECTS_DIR` | Non | `/projects` | Chemin du répertoire de base des projets dans le conteneur |

<!-- END AUTO-GENERATED -->

## Tests

<!-- AUTO-GENERATED -->
### Lancer les tests

```bash
# Installer les dépendances de test
pip install -r requirements.txt -r requirements-test.txt

# Tous les tests (hors Docker)
pytest tests/ -m "not slow"

# Avec rapport de couverture
pytest tests/ -m "not slow" --cov=. --cov-report=term

# Tests d'intégration Docker (nécessite un démon Docker actif)
pytest tests/ -m "slow and docker"
```

### Fichiers de tests

| Fichier | Couverture |
|---------|------------|
| `tests/test_app.py` | Fonctions backend de l'interface Gradio (8 onglets) |
| `tests/test_gradio_ui.py` | Structure UI : composants, câblage événements, modes |
| `tests/test_standard_mode.py` | Mode Standard : navigation, progression, wrappers |
| `tests/test_amc_wrapper.py` | Wrapper CLI AMC (subprocess mocking) |
| `tests/test_amc_database.py` | Lecture des bases SQLite AMC |
| `tests/test_amc_project.py` | Gestion des projets AMC |
| `tests/test_docker.py` | Validité Dockerfile, docker-compose.yml, requirements |
| `tests/test_docker_integration.py` | Intégration Docker complète (`@pytest.mark.slow`) |
| `tests/test_verification_integration.py` | Workflow de vérification bout-en-bout |

### Markers pytest

| Marker | Usage |
|--------|-------|
| `slow` | Tests lents (intégration Docker) — exclus par défaut en CI |
| `docker` | Tests nécessitant un démon Docker actif |

<!-- END AUTO-GENERATED -->

## CI/CD

<!-- AUTO-GENERATED -->
Le pipeline GitHub Actions (`.github/workflows/ci.yml`) s'exécute à chaque push sur `master` :

| Job | Python | Description |
|-----|--------|-------------|
| `lint` | 3.11 | Vérification syntaxe des 5 modules |
| `test` | 3.10 | Tests unitaires (`pytest -m "not slow"`) |
| `test` | 3.11 | Tests unitaires + rapport de couverture |
| `test` | 3.12 | Tests unitaires |
| `build-docker` | — | Build Docker avec cache Buildx (master uniquement) |

Artifacts disponibles après chaque run : rapports JUnit par version Python + couverture XML.
<!-- END AUTO-GENERATED -->

## Licence

GPL v2+ — voir les en-têtes des fichiers source.
