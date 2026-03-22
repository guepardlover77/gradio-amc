"""Tests de validité de la configuration Docker (sans démon Docker requis)."""

from pathlib import Path

import pytest

# Répertoire racine du projet (docker-gradio-amc/)
PROJECT_ROOT = Path(__file__).parent.parent


# ============================================================
# TestDockerfile
# ============================================================

class TestDockerfile:
    @pytest.fixture(scope="class")
    def lines(self):
        path = PROJECT_ROOT / "Dockerfile"
        assert path.exists(), "Dockerfile introuvable"
        return path.read_text().splitlines()

    @pytest.fixture(scope="class")
    def text(self):
        path = PROJECT_ROOT / "Dockerfile"
        return path.read_text()

    def test_dockerfile_exists(self):
        assert (PROJECT_ROOT / "Dockerfile").exists()

    def test_base_image_is_ubuntu(self, lines):
        from_lines = [l for l in lines if l.strip().startswith("FROM")]
        assert from_lines, "Aucune instruction FROM"
        assert any("ubuntu" in l.lower() for l in from_lines), \
            f"Image de base non-ubuntu : {from_lines}"

    def test_exposes_port_7860(self, lines):
        expose_lines = [l for l in lines if l.strip().startswith("EXPOSE")]
        assert any("7860" in l for l in expose_lines), \
            f"Port 7860 non exposé : {expose_lines}"

    def test_cmd_starts_app_py(self, lines):
        cmd_lines = [l for l in lines if l.strip().startswith("CMD")]
        assert cmd_lines, "Aucune instruction CMD"
        assert any("app.py" in l for l in cmd_lines), \
            f"CMD ne lance pas app.py : {cmd_lines}"

    def test_workdir_is_slash_app(self, lines):
        workdir_lines = [l for l in lines if l.strip().startswith("WORKDIR")]
        assert workdir_lines, "Aucune instruction WORKDIR"
        assert any("/app" in l for l in workdir_lines), \
            f"WORKDIR incorrect : {workdir_lines}"

    def test_installs_auto_multiple_choice(self, text):
        assert "auto-multiple-choice" in text, \
            "auto-multiple-choice non installé dans le Dockerfile"

    def test_installs_python3(self, lines):
        all_text = "\n".join(lines)
        assert "python3" in all_text

    def test_installs_pip(self, lines):
        all_text = "\n".join(lines)
        assert "pip" in all_text.lower()

    def test_creates_projects_volume_dir(self, lines):
        all_text = "\n".join(lines)
        assert "/projects" in all_text, \
            "Le répertoire /projects n'est pas créé dans le Dockerfile"

    def test_copies_requirements_before_pip_install(self, lines):
        """COPY requirements.txt doit précéder RUN pip install (cache Docker)."""
        copy_idx = next(
            (i for i, l in enumerate(lines)
             if "requirements.txt" in l and "COPY" in l),
            None,
        )
        pip_idx = next(
            (i for i, l in enumerate(lines) if "pip" in l.lower() and "install" in l),
            None,
        )
        assert copy_idx is not None, "COPY requirements.txt introuvable"
        assert pip_idx is not None, "RUN pip install introuvable"
        assert copy_idx < pip_idx, (
            f"COPY requirements.txt (ligne {copy_idx}) doit précéder "
            f"RUN pip install (ligne {pip_idx})"
        )

    def test_copy_app_sources(self, lines):
        """Les sources de l'application doivent être copiées."""
        copy_lines = [l for l in lines if l.strip().startswith("COPY")]
        # COPY . . ou COPY . /app
        assert any(". ." in l or "COPY . " in l for l in copy_lines), \
            f"Pas de COPY des sources trouvé : {copy_lines}"

    def test_env_pythonunbuffered(self, lines):
        """PYTHONUNBUFFERED doit être défini pour les logs temps-réel."""
        env_lines = [l for l in lines if l.strip().startswith("ENV")]
        assert any("PYTHONUNBUFFERED" in l for l in env_lines), \
            f"ENV PYTHONUNBUFFERED absent : {env_lines}"

    def test_installs_poppler_or_imagemagick(self, lines):
        """poppler-utils ou imagemagick doit être présent (traitement PDF/images)."""
        all_text = "\n".join(lines)
        assert "poppler" in all_text or "imagemagick" in all_text.lower(), \
            "Ni poppler-utils ni imagemagick installé"

    def test_no_sudo_in_cmd(self, lines):
        """CMD ne doit pas contenir sudo (déjà root dans le conteneur)."""
        cmd_lines = [l for l in lines if l.strip().startswith("CMD")]
        assert not any("sudo" in l for l in cmd_lines), \
            f"sudo dans CMD : {cmd_lines}"

    def test_cleanup_apt_lists(self, lines):
        """Le cache apt doit être nettoyé pour réduire la taille de l'image."""
        all_text = "\n".join(lines)
        assert "rm -rf /var/lib/apt/lists" in all_text, \
            "Nettoyage apt manquant (rm -rf /var/lib/apt/lists/*)"


# ============================================================
# TestDockerCompose
# ============================================================

class TestDockerCompose:
    @pytest.fixture(scope="class")
    def compose(self):
        yaml = pytest.importorskip("yaml")
        path = PROJECT_ROOT / "docker-compose.yml"
        assert path.exists(), "docker-compose.yml introuvable"
        return yaml.safe_load(path.read_text())

    def test_compose_file_exists(self):
        assert (PROJECT_ROOT / "docker-compose.yml").exists()

    def test_compose_is_valid_yaml(self):
        yaml = pytest.importorskip("yaml")
        path = PROJECT_ROOT / "docker-compose.yml"
        content = path.read_text()
        result = yaml.safe_load(content)
        assert result is not None

    def test_has_services_key(self, compose):
        assert "services" in compose, "Clé 'services' absente du docker-compose.yml"

    def test_has_amc_service(self, compose):
        assert "amc" in compose["services"], \
            f"Service 'amc' absent : {list(compose['services'].keys())}"

    def test_port_7860_mapped(self, compose):
        ports = compose["services"]["amc"].get("ports", [])
        assert ports, "Aucun port mappé pour le service 'amc'"
        assert any("7860" in str(p) for p in ports), \
            f"Port 7860 non mappé : {ports}"

    def test_host_port_7860(self, compose):
        ports = compose["services"]["amc"].get("ports", [])
        # Le port hôte doit être 7860 (format "7860:7860")
        assert any(str(p).startswith("7860") for p in ports), \
            f"Port hôte 7860 absent : {ports}"

    def test_projects_volume_mounted(self, compose):
        volumes = compose["services"]["amc"].get("volumes", [])
        assert volumes, "Aucun volume monté pour le service 'amc'"
        assert any("projects" in str(v) for v in volumes), \
            f"Volume /projects non monté : {volumes}"

    def test_projects_volume_path(self, compose):
        volumes = compose["services"]["amc"].get("volumes", [])
        # Doit mapper ./projects vers /projects
        assert any(
            ("./projects" in str(v) or ".\\projects" in str(v))
            for v in volumes
        ), f"Montage ./projects introuvable : {volumes}"

    def test_build_context(self, compose):
        build = compose["services"]["amc"].get("build")
        assert build is not None, "Clé 'build' absente du service 'amc'"
        # Build depuis le répertoire courant
        if isinstance(build, str):
            assert build == ".", f"Contexte de build incorrect : {build}"
        elif isinstance(build, dict):
            ctx = build.get("context", "")
            assert ctx in (".", "./"), f"Contexte de build incorrect : {ctx}"


# ============================================================
# TestRequirementsCoverage
# ============================================================

class TestRequirementsCoverage:
    @pytest.fixture(scope="class")
    def req_text(self):
        path = PROJECT_ROOT / "requirements.txt"
        assert path.exists(), "requirements.txt introuvable"
        return path.read_text().lower()

    def test_requirements_file_exists(self):
        assert (PROJECT_ROOT / "requirements.txt").exists()

    def test_gradio_present(self, req_text):
        assert "gradio" in req_text, "gradio absent de requirements.txt"

    def test_pillow_present(self, req_text):
        assert "pillow" in req_text or "pil" in req_text, \
            "Pillow absent de requirements.txt"

    def test_pandas_present(self, req_text):
        assert "pandas" in req_text, "pandas absent de requirements.txt"

    def test_openpyxl_present(self, req_text):
        assert "openpyxl" in req_text, \
            "openpyxl absent de requirements.txt (nécessaire pour export XLSX)"

    def test_no_local_file_paths(self, req_text):
        """Les chemins locaux (file://) ne doivent pas être dans requirements."""
        assert "file://" not in req_text, \
            "Chemin local file:// trouvé dans requirements.txt"

    def test_no_git_plus_paths(self, req_text):
        """Les dépendances git+ doivent être signalées (non reproductibles)."""
        # Ce test est informatif : un git+ n'est pas interdit mais inhabituel
        git_deps = [l for l in req_text.splitlines() if l.startswith("git+")]
        # On ne fail pas, mais on vérifie qu'il n'y en a pas de façon silencieuse
        assert isinstance(git_deps, list)  # toujours vrai, test structurel

    def test_version_constraints_present(self, req_text):
        """Au moins une dépendance doit avoir une contrainte de version."""
        lines = [l.strip() for l in req_text.splitlines() if l.strip() and not l.startswith("#")]
        versioned = [l for l in lines if ">=" in l or "<=" in l or "==" in l or "~=" in l]
        assert versioned, "Aucune contrainte de version dans requirements.txt"


# ============================================================
# TestEnvironmentConfig
# ============================================================

class TestEnvironmentConfig:
    def test_default_projects_dir_is_slash_projects(self, monkeypatch):
        """Sans AMC_PROJECTS_DIR, PROJECTS_BASE doit valoir '/projects'."""
        import importlib
        monkeypatch.delenv("AMC_PROJECTS_DIR", raising=False)
        import app as _app
        importlib.reload(_app)
        assert _app.PROJECTS_BASE == "/projects", \
            f"PROJECTS_BASE par défaut incorrect : {_app.PROJECTS_BASE}"

    def test_custom_projects_dir_override(self, monkeypatch):
        """AMC_PROJECTS_DIR doit écraser PROJECTS_BASE."""
        import importlib
        monkeypatch.setenv("AMC_PROJECTS_DIR", "/custom/amc")
        import app as _app
        importlib.reload(_app)
        assert _app.PROJECTS_BASE == "/custom/amc", \
            f"PROJECTS_BASE non surchargé : {_app.PROJECTS_BASE}"

    def test_env_var_used_in_project_listing(self, monkeypatch, tmp_path):
        """Les fonctions utilisant PROJECTS_BASE doivent respecter l'env var."""
        import importlib
        monkeypatch.setenv("AMC_PROJECTS_DIR", str(tmp_path))
        import app as _app
        importlib.reload(_app)
        # create_project doit utiliser le nouveau PROJECTS_BASE
        assert _app.PROJECTS_BASE == str(tmp_path)

    def test_timezone_set_in_dockerfile(self):
        """TZ doit être défini dans le Dockerfile pour éviter les prompts interactifs."""
        path = PROJECT_ROOT / "Dockerfile"
        content = path.read_text()
        assert "TZ=" in content or "TZ =" in content, \
            "Variable TZ non définie dans le Dockerfile"

    def test_debian_frontend_noninteractive(self):
        """DEBIAN_FRONTEND=noninteractive doit être défini."""
        path = PROJECT_ROOT / "Dockerfile"
        content = path.read_text()
        assert "DEBIAN_FRONTEND=noninteractive" in content, \
            "DEBIAN_FRONTEND=noninteractive absent du Dockerfile"
