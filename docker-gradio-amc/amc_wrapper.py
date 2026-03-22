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

"""Wrapper subprocess pour les commandes AMC CLI."""

import subprocess
import os


class AMCCommandRunner:
    """Exécute les commandes auto-multiple-choice via subprocess."""

    AMC_BIN = "auto-multiple-choice"
    DEFAULT_TIMEOUT = 600  # 10 minutes

    def __init__(self):
        pass

    def _run(self, args, cwd=None, timeout=None):
        """Exécute une commande AMC et retourne (returncode, stdout, stderr).

        La sortie est capturée ligne par ligne pour permettre un suivi
        en temps réel côté appelant.
        """
        timeout = timeout or self.DEFAULT_TIMEOUT
        cmd = [self.AMC_BIN] + args
        cmd_line = " ".join(cmd)
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
                text=True,
            )
            stdout, stderr = proc.communicate(timeout=timeout)
            # Prefix with the executed command for debugging
            header = f"[CMD] {cmd_line}\n[CWD] {cwd}\n\n"
            return proc.returncode, header + stdout, stderr
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return -2, "", f"Timeout après {timeout}s : {cmd_line}"
        except FileNotFoundError:
            return -1, "", f"Commande introuvable : {self.AMC_BIN}\n[CMD] {cmd_line}"

    def prepare_document(self, project_dir, source, n_copies, mode="s"):
        """Compile le document LaTeX.

        Args:
            project_dir: Répertoire du projet.
            source: Chemin du fichier .tex source.
            n_copies: Nombre de copies à générer.
            mode: 's' pour sujet, 'b' pour barème.
        """
        data_dir = os.path.join(project_dir, "data")
        build_dir = os.path.join(project_dir, "_build")
        os.makedirs(data_dir, exist_ok=True)
        os.makedirs(build_dir, exist_ok=True)

        # AMC concatenates prefix directly with filenames (e.g.
        # prefix + "sujet.pdf"), so it must end with a path separator.
        prefix = os.path.join(build_dir, "DOC-")

        args = [
            "prepare",
            "--mode", mode,
            "--data", data_dir,
            "--with", "pdflatex",
            "--prefix", prefix,
            "--n-copies", str(n_copies),
            "--latex-stdout",
            source,
        ]

        return self._run(args, cwd=project_dir, timeout=300)

    def compute_layout(self, project_dir, calage_path=None):
        """Lit le fichier calage .xy et peuple la base layout.sqlite.

        Cette étape est indispensable entre prepare --mode s et analyse :
        elle transforme le fichier DOC-calage.xy en données de layout
        (positions des cases sur chaque page).

        Args:
            project_dir: Répertoire du projet.
            calage_path: Chemin vers le fichier .xy (optionnel,
                         par défaut _build/DOC-calage.xy).
        """
        data_dir = os.path.join(project_dir, "data")
        if calage_path is None:
            build_dir = os.path.join(project_dir, "_build")
            calage_path = os.path.join(build_dir, "DOC-calage.xy")

        if not os.path.exists(calage_path):
            return 1, "", f"Fichier calage introuvable : {calage_path}"

        args = [
            "meptex",
            "--src", calage_path,
            "--data", data_dir,
        ]
        return self._run(args, cwd=project_dir, timeout=60)

    def import_scans(self, project_dir, scan_files):
        """Importe les fichiers scannés dans le projet.

        Args:
            project_dir: Répertoire du projet.
            scan_files: Liste de chemins vers les fichiers scan.
        """
        scans_dir = os.path.join(project_dir, "scans")
        os.makedirs(scans_dir, exist_ok=True)

        results = []
        for scan_file in scan_files:
            args = [
                "getimages",
                "--copy-to", scans_dir,
                "--vector-density", "300",
                scan_file,
            ]
            rc, out, err = self._run(args, cwd=project_dir, timeout=120)
            results.append((os.path.basename(scan_file), rc, out, err))

        # Résumé par fichier
        summary_lines = []
        for name, rc, out, err in results:
            status = "OK" if rc == 0 else f"ERREUR (code {rc})"
            summary_lines.append(f"  {name} : {status}")
        summary = "Résumé :\n" + "\n".join(summary_lines)

        all_ok = all(r[1] == 0 for r in results)
        combined_out = "\n".join(r[2] for r in results if r[2])
        combined_out += "\n\n" + summary
        combined_err = "\n".join(r[3] for r in results if r[3])
        return 0 if all_ok else 1, combined_out, combined_err

    def analyse_scans(self, project_dir, n_procs=4, threshold=0.15,
                       multiple=False):
        """Lance l'analyse OMR des scans.

        Args:
            project_dir: Répertoire du projet.
            n_procs: Nombre de processus parallèles.
            threshold: Seuil de détection des cases cochées.
            multiple: Si True, ajoute --multiple (copies photocopiées).
        """
        data_dir = os.path.join(project_dir, "data")
        cr_dir = os.path.join(project_dir, "cr")
        scans_dir = os.path.join(project_dir, "scans")
        os.makedirs(cr_dir, exist_ok=True)

        # Collect all image files from scans directory
        scan_images = []
        if os.path.isdir(scans_dir):
            for f in sorted(os.listdir(scans_dir)):
                if f.lower().endswith((".jpg", ".jpeg", ".png", ".tif", ".tiff")):
                    scan_images.append(os.path.join(scans_dir, f))

        if not scan_images:
            return 1, "", "Aucune image trouvée dans le répertoire scans/"

        args = [
            "analyse",
            "--data", data_dir,
            "--cr", cr_dir,
            "--n-procs", str(n_procs),
            "--prop", str(threshold),
        ]
        if multiple:
            args += ["--multiple"]
        args += scan_images

        return self._run(args, cwd=project_dir, timeout=600)

    def auto_associate(self, project_dir, student_list, list_key="ID",
                       notes_id="id"):
        """Association automatique étudiants/copies.

        Args:
            project_dir: Répertoire du projet.
            student_list: Chemin vers le fichier CSV des étudiants.
            list_key: Colonne clé dans le fichier CSV.
            notes_id: Identifiant pour les notes.
        """
        data_dir = os.path.join(project_dir, "data")
        args = [
            "association-auto",
            "--data", data_dir,
            "--liste", student_list,
            "--liste-key", list_key,
            "--notes-id", notes_id,
        ]
        return self._run(args, cwd=project_dir, timeout=60)

    def calculate_grades(self, project_dir, seuil=0.15, grain=0.5,
                         arrondi="n", notemax=20, notemin=0,
                         postcorrect_student=None, postcorrect_copy=None):
        """Calcule les notes.

        Args:
            project_dir: Répertoire du projet.
            seuil: Seuil de détection.
            grain: Granularité de la note.
            arrondi: Type d'arrondi ('n'=normal, 'i'=inférieur, 's'=supérieur).
            notemax: Note maximale.
            notemin: Note minimale.
            postcorrect_student: Numéro étudiant de la copie corrigée.
            postcorrect_copy: Numéro de copie de la copie corrigée.
        """
        data_dir = os.path.join(project_dir, "data")
        args = [
            "note",
            "--data", data_dir,
            "--seuil", str(seuil),
            "--grain", str(grain),
            "--arrondi", arrondi,
            "--notemax", str(notemax),
            "--notemin", str(notemin),
        ]
        if postcorrect_student is not None and postcorrect_copy is not None:
            args += [
                "--postcorrect-student", str(int(postcorrect_student)),
                "--postcorrect-copy", str(int(postcorrect_copy)),
            ]
        return self._run(args, cwd=project_dir, timeout=120)

    def export_results(self, project_dir, output_file, module="CSV",
                       student_list=None):
        """Exporte les résultats.

        Args:
            project_dir: Répertoire du projet.
            output_file: Chemin du fichier de sortie.
            module: Format d'export ('CSV' ou 'ODS').
            student_list: Chemin vers le fichier CSV des étudiants (optionnel).
        """
        data_dir = os.path.join(project_dir, "data")
        exports_dir = os.path.dirname(output_file)
        if exports_dir:
            os.makedirs(exports_dir, exist_ok=True)

        args = [
            "export",
            "--module", module,
            "--data", data_dir,
            "--output", output_file,
        ]
        if student_list:
            args += ["--fich-noms", student_list]

        return self._run(args, cwd=project_dir, timeout=120)
