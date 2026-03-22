# Runbook — Gradio-AMC

Guide opérationnel pour déployer, surveiller et dépanner Gradio-AMC.

## Déploiement

### Installation initiale

```bash
cd docker-gradio-amc
chmod +x install.sh
./install.sh
```

### Mise à jour

```bash
git pull origin master
docker compose build --no-cache
docker compose up -d
```

### Démarrage / arrêt

```bash
docker compose up -d          # démarrer
docker compose stop           # arrêter sans supprimer
docker compose down           # arrêter et supprimer le conteneur
docker compose restart        # redémarrer
```

<!-- AUTO-GENERATED -->
## Configuration

### Ports

| Port hôte | Port conteneur | Service |
|-----------|---------------|---------|
| `7860` | `7860` | Interface Gradio |

### Volumes

| Chemin hôte | Chemin conteneur | Description |
|-------------|-----------------|-------------|
| `./projects` | `/projects` | Données des projets AMC |

### Variables d'environnement

| Variable | Défaut | Description |
|----------|--------|-------------|
| `AMC_PROJECTS_DIR` | `/projects` | Répertoire des projets dans le conteneur |

Pour surcharger, ajouter dans `docker-compose.yml` :
```yaml
services:
  amc:
    environment:
      - AMC_PROJECTS_DIR=/mon/chemin/custom
```

<!-- END AUTO-GENERATED -->

## Vérification de santé

### L'interface répond-elle ?

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:7860
# → 200 si OK
```

### Le conteneur tourne-t-il ?

```bash
docker compose ps
# → "Up" dans la colonne Status
```

### Les logs sont-ils propres ?

```bash
docker compose logs --tail=50
# Pas de "ERROR" ou "Traceback" attendu au démarrage normal
```

## Problèmes fréquents

### Le port 7860 est déjà occupé

```bash
# Identifier le processus
lsof -i :7860          # Linux/macOS
netstat -ano | findstr 7860  # Windows

# Changer le port dans docker-compose.yml
ports:
  - "7861:7860"   # utiliser 7861 à la place
```

### L'image Docker ne se construit pas

```bash
# Nettoyer le cache Docker
docker system prune -f
docker compose build --no-cache
```

### Les projets ont disparu après redémarrage

Vérifier que le volume `./projects` existe et est correctement monté :
```bash
ls -la docker-gradio-amc/projects/
docker compose exec amc ls /projects
```

### AMC échoue lors de la compilation LaTeX

Vérifier que les packages TeXLive sont bien installés dans le conteneur :
```bash
docker compose exec amc dpkg -l | grep texlive
```

### Gradio ne démarre pas (erreur d'import)

```bash
docker compose exec amc python3 -c "import gradio; print(gradio.__version__)"
# Si erreur → reconstruire l'image
docker compose build --no-cache
```

## Sauvegarde

### Sauvegarder les projets

```bash
tar czf backup-amc-$(date +%Y%m%d).tar.gz docker-gradio-amc/projects/
```

### Restaurer

```bash
tar xzf backup-amc-YYYYMMDD.tar.gz -C docker-gradio-amc/
docker compose restart
```

## Rollback

```bash
# Voir les commits récents
git log --oneline -10

# Revenir à un commit précédent
git checkout <commit-sha>
docker compose build
docker compose up -d
```

## CI/CD — GitHub Actions

<!-- AUTO-GENERATED -->
Les runs de pipeline sont visibles sur :
**https://github.com/guepardlover77/gradio-amc/actions**

| Job | Déclencheur | Durée typique |
|-----|-------------|---------------|
| `lint` | Tout push sur master | ~10s |
| `test (3.10/3.11/3.12)` | Tout push sur master | ~1min |
| `build-docker` | Push sur master uniquement | ~7min |

### Artifacts disponibles après chaque run

- `junit-report-py3.10/11/12` — rapports de tests au format JUnit
- `coverage-report` — couverture de code XML (Python 3.11)
<!-- END AUTO-GENERATED -->
