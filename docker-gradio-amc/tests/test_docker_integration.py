"""Tests d'intégration Docker — nécessitent un démon Docker actif.

Ces tests sont marqués `slow` et `docker`.
Pour les exécuter : pytest -m "slow and docker"
Pour les ignorer  : pytest -m "not slow"
"""

import subprocess
import time
import shutil
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent

# Ignorer ces tests si Docker n'est pas disponible
docker_available = shutil.which("docker") is not None
pytestmark = [
    pytest.mark.slow,
    pytest.mark.docker,
    pytest.mark.skipif(
        not docker_available,
        reason="Docker non disponible sur cette machine",
    ),
]

IMAGE_TAG = "amc-gradio-test"
CONTAINER_NAME = "amc-gradio-test-run"
HOST_PORT = 7862  # port test (éviter collision avec 7860)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(scope="module")
def docker_image():
    """Construit l'image Docker de test."""
    result = subprocess.run(
        ["docker", "build", "-t", IMAGE_TAG, "."],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        pytest.fail(
            f"Échec du build Docker :\n{result.stdout}\n{result.stderr}"
        )
    yield IMAGE_TAG
    # Nettoyage
    subprocess.run(["docker", "rmi", "-f", IMAGE_TAG], capture_output=True)


@pytest.fixture
def running_container(docker_image):
    """Démarre un conteneur et le supprime après le test."""
    subprocess.run(
        ["docker", "rm", "-f", CONTAINER_NAME],
        capture_output=True,
    )
    result = subprocess.run(
        [
            "docker", "run", "-d",
            "--name", CONTAINER_NAME,
            "-p", f"{HOST_PORT}:7860",
            docker_image,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        pytest.fail(f"Impossible de démarrer le conteneur : {result.stderr}")
    # Attendre que Gradio soit prêt
    time.sleep(8)
    yield CONTAINER_NAME
    subprocess.run(["docker", "rm", "-f", CONTAINER_NAME], capture_output=True)


# ============================================================
# TestDockerBuild
# ============================================================

class TestDockerBuild:
    def test_image_builds_successfully(self, docker_image):
        """L'image Docker doit se construire sans erreur."""
        result = subprocess.run(
            ["docker", "image", "inspect", docker_image],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, \
            f"Image {docker_image} introuvable après build"

    def test_image_exposes_7860(self, docker_image):
        """L'image doit déclarer le port 7860 dans ses métadonnées."""
        import json
        result = subprocess.run(
            ["docker", "image", "inspect", docker_image],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        metadata = json.loads(result.stdout)
        exposed_ports = (
            metadata[0].get("Config", {}).get("ExposedPorts", {})
        )
        assert "7860/tcp" in exposed_ports, \
            f"Port 7860/tcp non exposé dans les métadonnées : {exposed_ports}"

    def test_image_has_workdir_app(self, docker_image):
        """WORKDIR /app doit être défini dans l'image."""
        import json
        result = subprocess.run(
            ["docker", "image", "inspect", docker_image],
            capture_output=True,
            text=True,
        )
        metadata = json.loads(result.stdout)
        workdir = metadata[0].get("Config", {}).get("WorkingDir", "")
        assert workdir == "/app", f"WorkingDir incorrect : {workdir}"


# ============================================================
# TestDockerRuntime
# ============================================================

class TestDockerRuntime:
    def test_container_starts(self, running_container):
        """Le conteneur doit démarrer et rester actif."""
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", running_container],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "true" in result.stdout.lower(), \
            f"Conteneur non actif : {result.stdout}"

    def test_gradio_responds_on_port(self, running_container):
        """Gradio doit répondre sur le port mappé."""
        try:
            import urllib.request
            url = f"http://localhost:{HOST_PORT}/"
            with urllib.request.urlopen(url, timeout=10) as resp:
                assert resp.status == 200, f"Status HTTP : {resp.status}"
        except Exception as e:
            pytest.fail(f"Gradio ne répond pas sur le port {HOST_PORT} : {e}")

    def test_projects_dir_exists_in_container(self, running_container):
        """Le répertoire /projects doit exister dans le conteneur."""
        result = subprocess.run(
            ["docker", "exec", running_container,
             "test", "-d", "/projects"],
            capture_output=True,
        )
        assert result.returncode == 0, "/projects absent du conteneur"

    def test_app_py_exists_in_container(self, running_container):
        """app.py doit être présent dans /app."""
        result = subprocess.run(
            ["docker", "exec", running_container,
             "test", "-f", "/app/app.py"],
            capture_output=True,
        )
        assert result.returncode == 0, "/app/app.py absent du conteneur"

    def test_amc_command_available(self, running_container):
        """La commande `auto-multiple-choice` doit être disponible."""
        result = subprocess.run(
            ["docker", "exec", running_container,
             "which", "auto-multiple-choice"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, \
            f"auto-multiple-choice introuvable dans le conteneur : {result.stderr}"

    def test_python3_available(self, running_container):
        """python3 doit être disponible."""
        result = subprocess.run(
            ["docker", "exec", running_container,
             "python3", "--version"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_gradio_importable(self, running_container):
        """gradio doit être importable depuis le conteneur."""
        result = subprocess.run(
            ["docker", "exec", running_container,
             "python3", "-c", "import gradio; print(gradio.__version__)"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, \
            f"gradio non importable : {result.stderr}"


# ============================================================
# TestDockerVolume
# ============================================================

class TestDockerVolume:
    def test_volume_mount_persists_files(self, docker_image, tmp_path):
        """Un fichier créé via volume doit être accessible dans le conteneur."""
        container = "amc-volume-test"
        test_file = tmp_path / "test_persistence.txt"
        test_file.write_text("persistence ok")

        subprocess.run(["docker", "rm", "-f", container], capture_output=True)
        result = subprocess.run(
            [
                "docker", "run", "--rm",
                "--name", container,
                "-v", f"{tmp_path}:/projects",
                docker_image,
                "cat", "/projects/test_persistence.txt",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Erreur volume : {result.stderr}"
        assert "persistence ok" in result.stdout
