# Copyright (C) 2026 Mathéo Milley-Arjaliès <cam137@proton.me>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
# MA 02110-1301, USA.

"""Gestion des projets AMC."""

import os
import re
import shutil
import sqlite3
import zipfile


SUBDIRS = ["data", "scans", "cr", "exports", "_build"]


class AMCProject:
    """Représente un projet AMC avec son arborescence de fichiers."""

    def __init__(self, project_dir):
        self.project_dir = project_dir

    @staticmethod
    def create_new(base_dir, name):
        """Crée un nouveau projet avec l'arborescence standard.

        Args:
            base_dir: Répertoire de base contenant tous les projets.
            name: Nom du projet.

        Returns:
            Instance AMCProject pour le nouveau projet.
        """
        project_dir = os.path.join(base_dir, name)
        if os.path.exists(project_dir):
            raise FileExistsError(f"Le projet '{name}' existe déjà")

        for subdir in SUBDIRS:
            os.makedirs(os.path.join(project_dir, subdir), exist_ok=True)

        return AMCProject(project_dir)

    @staticmethod
    def import_existing(base_dir, name, zip_path):
        """Importe un projet AMC existant depuis une archive ZIP.

        L'archive peut contenir un répertoire racine ou directement les
        sous-dossiers (data/, scans/, cr/, etc.).  Le répertoire data/ avec
        ses bases SQLite est indispensable pour que le layout corresponde
        aux scans imprimés.

        Args:
            base_dir: Répertoire de base contenant tous les projets.
            name: Nom du projet.
            zip_path: Chemin vers l'archive ZIP du projet AMC.

        Returns:
            Instance AMCProject pour le projet importé.
        """
        project_dir = os.path.join(base_dir, name)
        if os.path.exists(project_dir):
            raise FileExistsError(f"Le projet '{name}' existe déjà")

        os.makedirs(project_dir, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zf:
            # Detect if archive has a single root directory
            top_dirs = {n.split("/")[0] for n in zf.namelist() if "/" in n}
            names = zf.namelist()
            # Check if all entries share a common prefix directory
            prefix = ""
            if top_dirs and len(top_dirs) == 1:
                candidate = top_dirs.pop() + "/"
                if all(n.startswith(candidate) or n == candidate.rstrip("/")
                       for n in names):
                    prefix = candidate

            for member in names:
                if member.endswith("/"):
                    continue
                # Strip the root directory prefix if present
                rel = member[len(prefix):] if prefix else member
                if not rel:
                    continue
                dest = os.path.join(project_dir, rel)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with zf.open(member) as src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst)

        # Ensure standard subdirectories exist
        for subdir in SUBDIRS:
            os.makedirs(os.path.join(project_dir, subdir), exist_ok=True)

        return AMCProject(project_dir)

    @staticmethod
    def list_projects(base_dir):
        """Liste les projets existants dans le répertoire de base.

        Returns:
            Liste de noms de projets.
        """
        if not os.path.isdir(base_dir):
            return []
        projects = []
        for entry in sorted(os.listdir(base_dir)):
            path = os.path.join(base_dir, entry)
            if os.path.isdir(path) and os.path.isdir(
                os.path.join(path, "data")
            ):
                projects.append(entry)
        return projects

    def get_status(self):
        """Vérifie l'état du projet : quelles étapes sont faites.

        Returns:
            Dict avec les clés : source, compiled, scans, analysed,
            associated, graded, exported.
        """
        status = {
            "source": False,
            "compiled": False,
            "scans": False,
            "analysed": False,
            "associated": False,
            "graded": False,
            "exported": False,
        }

        # Source .tex présent ?
        source_path = self._find_source()
        status["source"] = source_path is not None

        # PDFs compilés ?
        build_dir = os.path.join(self.project_dir, "_build")
        if os.path.isdir(build_dir):
            pdfs = [f for f in os.listdir(build_dir) if f.endswith(".pdf")]
            status["compiled"] = len(pdfs) > 0

        # Scans importés ?
        scans_dir = os.path.join(self.project_dir, "scans")
        if os.path.isdir(scans_dir):
            images = [
                f for f in os.listdir(scans_dir)
                if f.lower().endswith(
                    (".jpg", ".jpeg", ".png", ".tif", ".tiff")
                )
            ]
            status["scans"] = len(images) > 0

        # Check SQLite databases for actual content, not just existence
        data_dir = os.path.join(self.project_dir, "data")
        if os.path.isdir(data_dir):
            status["compiled"] = status["compiled"] and self._db_has_rows(
                data_dir, "layout.sqlite", "layout_page"
            )
            status["analysed"] = self._db_has_rows(
                data_dir, "capture.sqlite", "capture_page"
            )
            status["associated"] = self._db_has_rows(
                data_dir, "association.sqlite", "association_association"
            )
            status["graded"] = self._db_has_rows(
                data_dir, "scoring.sqlite", "scoring_mark"
            )

        # Exports présents ?
        exports_dir = os.path.join(self.project_dir, "exports")
        if os.path.isdir(exports_dir):
            exports = os.listdir(exports_dir)
            status["exported"] = len(exports) > 0

        return status

    def save_source(self, content=None, uploaded_file=None):
        """Sauvegarde le fichier source .tex.

        Args:
            content: Contenu texte du fichier .tex.
            uploaded_file: Chemin d'un fichier uploadé à copier.

        Returns:
            Chemin du fichier source sauvegardé.
        """
        dest = os.path.join(self.project_dir, "source.tex")
        if uploaded_file:
            shutil.copy2(uploaded_file, dest)
        elif content is not None:
            with open(dest, "w", encoding="utf-8") as f:
                f.write(content)
        return dest

    def save_student_list(self, uploaded_file):
        """Sauvegarde le fichier liste d'étudiants.

        Args:
            uploaded_file: Chemin du fichier CSV uploadé.

        Returns:
            Chemin du fichier sauvegardé.
        """
        dest = os.path.join(self.project_dir, "students.csv")
        shutil.copy2(uploaded_file, dest)
        return dest

    def get_source_path(self):
        """Retourne le chemin du fichier source s'il existe."""
        path = self._find_source()
        return path

    def get_source_content(self):
        """Retourne le contenu du fichier source s'il existe."""
        path = self._find_source()
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    def get_student_list_path(self):
        """Retourne le chemin du fichier liste étudiants s'il existe."""
        path = os.path.join(self.project_dir, "students.csv")
        return path if os.path.exists(path) else None

    def get_scans(self):
        """Liste les fichiers scannés importés.

        Returns:
            Liste de noms de fichiers dans scans/.
        """
        scans_dir = os.path.join(self.project_dir, "scans")
        if not os.path.isdir(scans_dir):
            return []
        return sorted(
            f for f in os.listdir(scans_dir)
            if f.lower().endswith(
                (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".pdf")
            )
        )

    def get_pdf_path(self):
        """Retourne le chemin du PDF sujet compilé s'il existe."""
        build_dir = os.path.join(self.project_dir, "_build")
        # 1. Emplacement normal avec notre convention de préfixe
        sujet = os.path.join(build_dir, "DOC-sujet.pdf")
        if os.path.exists(sujet):
            return sujet
        # 2. Fallback: tout PDF dans _build/
        if os.path.isdir(build_dir):
            for f in os.listdir(build_dir):
                if f.endswith(".pdf"):
                    return os.path.join(build_dir, f)
        # 3. Fallback: amc-compiled.pdf à la racine du projet
        #    (AMC ne renomme pas le PDF quand la compilation a des warnings)
        compiled = os.path.join(self.project_dir, "amc-compiled.pdf")
        if os.path.exists(compiled):
            return compiled
        return None

    @staticmethod
    def _db_has_rows(data_dir, db_name, table_name):
        """Vérifie qu'une table SQLite contient des données."""
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table_name):
            return False
        path = os.path.join(data_dir, db_name)
        if not os.path.exists(path):
            return False
        try:
            conn = sqlite3.connect(path)
            cur = conn.cursor()
            cur.execute(f'SELECT COUNT(*) FROM "{table_name}"')
            count = cur.fetchone()[0]
            conn.close()
            return count > 0
        except (sqlite3.OperationalError, sqlite3.DatabaseError):
            return False

    def _find_source(self):
        """Cherche le fichier source .tex dans le projet."""
        path = os.path.join(self.project_dir, "source.tex")
        if os.path.exists(path):
            return path
        # Chercher tout .tex à la racine du projet
        for f in os.listdir(self.project_dir):
            if f.endswith(".tex"):
                return os.path.join(self.project_dir, f)
        return None
