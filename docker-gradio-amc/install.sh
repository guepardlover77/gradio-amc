#!/usr/bin/env bash
# Copyright (C) 2026 Matheo Milley-Arjalies <cam137@proton.me>
# GPL v2+

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

cd "$(dirname "$0")"

# ---------- Install Docker ----------
install_docker() {
    if command -v docker &>/dev/null; then
        info "Docker est deja installe ($(docker --version))."
        return
    fi

    info "Installation de Docker..."

    case "$OS_LIKE" in
        *debian*|*ubuntu*)
            sudo apt-get update
            sudo apt-get install -y ca-certificates curl gnupg
            sudo install -m 0755 -d /etc/apt/keyrings
            curl -fsSL https://download.docker.com/linux/"$OS_ID"/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
            sudo chmod a+r /etc/apt/keyrings/docker.gpg
            echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/$OS_ID $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
                | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
            sudo apt-get update
            sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
            ;;
        *fedora*|*rhel*|*centos*)
            sudo dnf -y install dnf-plugins-core
            sudo dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo
            sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
            sudo systemctl enable --now docker
            ;;
        *arch*)
            sudo pacman -Sy --noconfirm docker docker-compose
            sudo systemctl enable --now docker
            ;;
        *macos*)
            if command -v brew &>/dev/null; then
                brew install --cask docker
                info "Docker Desktop installe. Veuillez le lancer depuis les Applications avant de continuer."
                read -rp "Appuyez sur Entree une fois Docker Desktop demarre..."
            else
                error "Installez Homebrew (https://brew.sh) ou Docker Desktop manuellement."
            fi
            ;;
        *)
            error "Distribution non supportee pour l'installation automatique de Docker. Installez Docker manuellement : https://docs.docker.com/engine/install/"
            ;;
    esac

    info "Docker installe avec succes."
}

# ---------- Docker group (Linux only) ----------
setup_docker_group() {
    [ "$OS_ID" = "macos" ] && return

    if ! groups "$USER" | grep -q '\bdocker\b'; then
        info "Ajout de $USER au groupe docker..."
        sudo usermod -aG docker "$USER"
        warn "Vous devrez vous reconnecter (ou lancer 'newgrp docker') pour que le groupe prenne effet."
        NEED_NEWGRP=1
    fi
}

# ---------- Docker Compose check ----------
check_compose() {
    if docker compose version &>/dev/null; then
        return
    elif command -v docker-compose &>/dev/null; then
        return
    else
        error "Docker Compose introuvable. Installez-le : https://docs.docker.com/compose/install/"
    fi
}

# ---------- Build & start ----------
build_and_start() {
    info "Construction de l'image Docker (cela peut prendre quelques minutes)..."
    if [ "${NEED_NEWGRP:-0}" = "1" ]; then
        sudo docker compose build
        sudo docker compose up -d
    else
        docker compose build
        docker compose up -d
    fi

    info "Conteneur demarre."
    echo ""
    info "L'interface est accessible sur : http://localhost:7860"
}

# ---------- Main ----------
main() {
    echo "======================================="
    echo "  Installation de Gradio-AMC"
    echo "======================================="
    echo ""

    detect_os
    info "Systeme detecte : $OS_ID"

    install_docker
    setup_docker_group
    check_compose
    build_and_start

    echo ""
    info "Installation terminee."
}

main
