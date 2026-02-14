# Gradio-AMC

Interface web pour [Auto Multiple Choice](https://www.auto-multiple-choice.net/) (AMC), tournant dans un conteneur Docker.

Normalement AMC ça tourne pas sur Windows mais seulement sur Linux (et macos je crois ?). Mais il suffit de le faire tourner dans Docker qui utilise Linux pour ses container et de créer une interface pour discuter avec la CLI AMC en backend dans Docker !
Pour cela on utilise Gradio qui est plutôt cool pour créer des interfaces rapides et épurées mais en gardant plein de fonctionnalités.

Chaque champ à remplir correspond à des arguments à mettre dans la CLI AMC et chaque bouton correspond à une option pour intégrer les arguments précédemment remplis et lancer la commande.

## Fonctionnalites

Il manque encore plein de fonctionnalités très sympa d'AMC mais c'est à venir ;)
Pour l'instant il y a les bases, _id est_ :

- Edition du source LaTeX des QCM
- Generation des sujets PDF (et visualisation)
- Upload et analyse des copies scannées
- Correction et notation automatiques
- Export des resultats (CSV, ODS, XLSX : nouveau !)
- Association des copies
- Gestion de plusieurs projets

## Prerequis

- Un OS
- Internet (pour l'installation initiale)

Docker et Docker Compose sont installés automatiquement par le [script d'installation](./install.sh) si nécessaire.

## Installation rapide

```bash
chmod +x install.sh
./install.sh
```

Le script :
1. Installe Docker et Docker Compose s'ils ne sont pas présents
2. Ajoute l'utilisateur courant au groupe `docker`
3. Construit l'image Docker
4. Démarre le contener

## Demarrage manuel

Si Docker est deja installé :

```bash
docker compose up -d
```

L'interface est accessible sur [http://localhost:7860](http://localhost:7860).

## Structure

| Fichier | Description |
|---------|-------------|
| `app.py` | Interface Gradio principale |
| `amc_wrapper.py` | Appels au CLI AMC |
| `amc_project.py` | Gestion des projets AMC |
| `amc_database.py` | Lecture des bases SQLite AMC |
| `Dockerfile` | Image Ubuntu 22.04 + AMC + TeXLive + Gradio |
| `docker-compose.yml` | Orchestration du contener |

## Données

Les projets sont stockés dans le dossier `projects/` (monté comme volume Docker). Ce dossier est ignoré par Git.

## Licence

GPL v2+ — voir les en-tetes des fichiers source.
