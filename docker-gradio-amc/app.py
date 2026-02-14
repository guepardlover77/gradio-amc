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

"""Interface Gradio pour Auto-Multiple-Choice."""

import base64
import json
import logging
import os
import re
import shutil

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import gradio as gr
import pandas as pd

from amc_wrapper import AMCCommandRunner
from amc_project import AMCProject
from amc_database import AMCDatabase

PROJECTS_BASE = os.environ.get("AMC_PROJECTS_DIR", "/projects")

runner = AMCCommandRunner()

# ---------- État global ----------

current_project = {"path": None}


def _project():
    """Retourne l'AMCProject courant ou None."""
    if current_project["path"]:
        return AMCProject(current_project["path"])
    return None


def _db():
    """Retourne l'AMCDatabase du projet courant ou None."""
    if current_project["path"]:
        data_dir = os.path.join(current_project["path"], "data")
        return AMCDatabase(data_dir)
    return None


def _format_log(rc, stdout, stderr):
    """Formate la sortie d'une commande AMC pour l'affichage."""
    parts = []
    if stdout:
        parts.append(stdout)
    if stderr:
        parts.append(f"[STDERR]\n{stderr}")
    status = "OK" if rc == 0 else f"ERREUR (code {rc})"
    parts.append(f"\n--- {status} ---")
    return "\n".join(parts)


def _generate_pdf_viewer(pdf_path):
    """Génère le HTML pour afficher un PDF via iframe base64."""
    if not pdf_path or not os.path.exists(pdf_path):
        return ""
    try:
        with open(pdf_path, "rb") as f:
            pdf_data = base64.b64encode(f.read()).decode()
        html = f'''
        <div style="width: 100%; height: 800px;">
            <iframe
                src="data:application/pdf;base64,{pdf_data}"
                width="100%"
                height="100%"
                style="border: none;">
            </iframe>
        </div>
        '''
        return html
    except Exception as e:
        logger.error("Error generating PDF viewer: %s", e)
        return f"<p>Erreur lors du chargement du PDF : {e}</p>"


# ============================================================
# Onglet 1 — Projet
# ============================================================

def _load_project_data(proj):
    """Charge toutes les données existantes d'un projet pour peupler l'UI.

    Returns:
        Tuple (source_content, images_group_visible, pdf_viewer_html,
               pdf_path, scan_list_text, results_df, questions_df).
    """
    # Source LaTeX
    source_content = proj.get_source_content() or ""
    missing_images = _check_missing_images(proj) if source_content else []

    # PDF compilé
    pdf_path = proj.get_pdf_path()
    pdf_viewer_html = _generate_pdf_viewer(pdf_path)

    # Scans importés
    scans = proj.get_scans()
    scan_list_text = "\n".join(scans) if scans else "Aucun scan."

    # Notes (si la notation a été faite)
    results_df = None
    questions_df = None
    data_dir = os.path.join(proj.project_dir, "data")
    if os.path.isdir(data_dir):
        db = AMCDatabase(data_dir)
        results_df = db.get_scoring_results()
        questions_df = db.get_question_stats()
        if results_df is not None and results_df.empty:
            results_df = None
        if questions_df is not None and questions_df.empty:
            questions_df = None

    return (
        source_content,
        gr.update(visible=bool(missing_images)),
        pdf_viewer_html,
        pdf_path,
        scan_list_text,
        results_df,
        questions_df,
    )


def _empty_project_data():
    """Retourne des valeurs vides pour tous les champs projet."""
    return ("", gr.update(visible=False), "", None, "Aucun scan.", None, None)


def create_project(name):
    if not name or not name.strip():
        return ("Veuillez entrer un nom de projet.", "",
                gr.update(choices=[]), *_empty_project_data())
    name = name.strip()
    try:
        proj = AMCProject.create_new(PROJECTS_BASE, name)
        current_project["path"] = proj.project_dir
        status = proj.get_status()
        projects = AMCProject.list_projects(PROJECTS_BASE)
        return (
            f"Projet '{name}' créé avec succès.",
            json.dumps(status, indent=2),
            gr.update(choices=projects, value=name),
            *_empty_project_data(),
        )
    except FileExistsError:
        return (f"Le projet '{name}' existe déjà.", "",
                gr.update(choices=[]), *_empty_project_data())


def open_project(name):
    if not name:
        return ("Sélectionnez un projet.", "", *_empty_project_data())
    path = os.path.join(PROJECTS_BASE, name)
    if not os.path.isdir(path):
        return (f"Projet '{name}' introuvable.", "", *_empty_project_data())
    current_project["path"] = path
    proj = AMCProject(path)
    status = proj.get_status()
    return (
        f"Projet '{name}' ouvert.",
        json.dumps(status, indent=2),
        *_load_project_data(proj),
    )


def import_project(name, zip_file):
    if not name or not name.strip():
        return ("Veuillez entrer un nom de projet.", "",
                gr.update(choices=[]), *_empty_project_data())
    if zip_file is None:
        return ("Veuillez sélectionner une archive ZIP.", "",
                gr.update(choices=[]), *_empty_project_data())
    name = name.strip()
    try:
        proj = AMCProject.import_existing(PROJECTS_BASE, name, zip_file)
        current_project["path"] = proj.project_dir
        status = proj.get_status()
        projects = AMCProject.list_projects(PROJECTS_BASE)
        return (
            f"Projet '{name}' importé avec succès.",
            json.dumps(status, indent=2),
            gr.update(choices=projects, value=name),
            *_load_project_data(proj),
        )
    except FileExistsError:
        return (f"Le projet '{name}' existe déjà.", "",
                gr.update(choices=[]), *_empty_project_data())
    except Exception as e:
        return (f"Erreur lors de l'import : {e}", "",
                gr.update(choices=[]), *_empty_project_data())


def refresh_projects():
    projects = AMCProject.list_projects(PROJECTS_BASE)
    return gr.update(choices=projects)


# ============================================================
# Onglet 2 — Préparation
# ============================================================

def _detect_images(tex_content):
    """Extrait les noms de fichiers images depuis un source LaTeX."""
    # \includegraphics[...]{filename} — avec ou sans extension
    return re.findall(
        r'\\includegraphics\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}',
        tex_content,
    )


def _check_missing_images(proj):
    """Retourne la liste des images référencées mais absentes du projet."""
    content = proj.get_source_content()
    if not content:
        return []
    images = _detect_images(content)
    missing = []
    for img in images:
        # LaTeX cherche avec et sans extension
        path = os.path.join(proj.project_dir, img)
        if os.path.exists(path):
            continue
        # Essayer les extensions courantes
        found = False
        for ext in (".png", ".jpg", ".jpeg", ".pdf", ".eps"):
            if os.path.exists(path + ext):
                found = True
                break
        if not found:
            missing.append(img)
    return missing


def upload_source(file):
    proj = _project()
    if not proj:
        return "Aucun projet ouvert.", None, gr.update()
    if file is None:
        return "Aucun fichier sélectionné.", None, gr.update()
    proj.save_source(uploaded_file=file)
    content = proj.get_source_content()
    missing = _check_missing_images(proj)
    msg = "Fichier source importé."
    if missing:
        msg += f" Images manquantes : {', '.join(missing)}"
    return msg, content, gr.update(visible=bool(missing))


def upload_images(files):
    proj = _project()
    if not proj:
        return "Aucun projet ouvert.", gr.update()
    if not files:
        return "Aucun fichier sélectionné.", gr.update()
    imported = []
    for f in files:
        basename = os.path.basename(f)
        dest = os.path.join(proj.project_dir, basename)
        shutil.copy2(f, dest)
        imported.append(basename)
    missing = _check_missing_images(proj)
    msg = f"Images importées : {', '.join(imported)}"
    if missing:
        msg += f"\nEncore manquantes : {', '.join(missing)}"
    return msg, gr.update(visible=bool(missing))


def save_source_editor(content):
    proj = _project()
    if not proj:
        return "Aucun projet ouvert."
    proj.save_source(content=content)
    return "Source sauvegardée."


def compile_document(n_copies):
    logger.info("compile_document called with n_copies=%s", n_copies)
    proj = _project()
    if not proj:
        return "Aucun projet ouvert.", None, ""
    source = proj.get_source_path()
    if not source:
        return "Aucun fichier source .tex trouvé.", None, ""
    n = int(n_copies) if n_copies else 30
    logger.info("Compiling project=%s source=%s n=%d", proj.project_dir, source, n)

    # Compiler le sujet (mode s = subject + layout)
    rc1, out1, err1 = runner.prepare_document(
        proj.project_dir, source, n, mode="s"
    )
    log = "=== Compilation sujet ===\n" + _format_log(rc1, out1, err1)

    if rc1 != 0:
        # AMC renvoie rc!=0 même pour des warnings LaTeX non-fatals
        # (ex: image manquante). On continue si le PDF a été produit.
        pdf_path = proj.get_pdf_path()
        if not pdf_path:
            log += "\n\nCompilation échouée, étapes suivantes ignorées."
            return log, None, ""
        log += "\n\n⚠ Compilation avec warnings (voir log ci-dessus)."

    # Calculer le layout (meptex : lit calage.xy → peuple layout.sqlite)
    rc_mep, out_mep, err_mep = runner.compute_layout(proj.project_dir)
    log += "\n\n=== Détection du layout ===\n" + _format_log(
        rc_mep, out_mep, err_mep
    )

    if rc_mep != 0:
        log += "\n\nDétection du layout échouée, extraction du barème ignorée."
        pdf_path = proj.get_pdf_path()
        return log, pdf_path, _generate_pdf_viewer(pdf_path)

    # Extraire le barème (mode b = scoring)
    rc2, out2, err2 = runner.prepare_document(
        proj.project_dir, source, n, mode="b"
    )
    log += "\n\n=== Extraction barème ===\n" + _format_log(rc2, out2, err2)

    pdf_path = proj.get_pdf_path()
    logger.info("compile_document done, pdf=%s", pdf_path)
    pdf_viewer_html = _generate_pdf_viewer(pdf_path)
    return log, pdf_path, pdf_viewer_html


def import_calage(xy_file):
    """Importe un fichier calage .xy existant et re-calcule le layout."""
    proj = _project()
    if not proj:
        return "Aucun projet ouvert."
    if xy_file is None:
        return "Aucun fichier sélectionné."

    import shutil
    build_dir = os.path.join(proj.project_dir, "_build")
    os.makedirs(build_dir, exist_ok=True)
    dest = os.path.join(build_dir, "DOC-calage.xy")
    shutil.copy2(xy_file, dest)

    rc, out, err = runner.compute_layout(proj.project_dir, dest)
    return _format_log(rc, out, err)


# ============================================================
# Onglet 3 — Scans
# ============================================================

def import_scans(files, correction_file, correction_state):
    proj = _project()
    if not proj:
        return "Aucun projet ouvert.", "", correction_state
    if not files and not correction_file:
        return "Aucun fichier sélectionné.", "", correction_state

    all_files = list(files) if files else []
    new_correction_name = correction_state or ""

    if correction_file is not None:
        all_files.append(correction_file)
        # Mémoriser le basename sans extension du corrigé
        basename = os.path.basename(correction_file)
        new_correction_name = os.path.splitext(basename)[0]

    rc, out, err = runner.import_scans(proj.project_dir, all_files)
    scans = proj.get_scans()
    scan_list = "\n".join(scans) if scans else "Aucun scan."
    return _format_log(rc, out, err), scan_list, new_correction_name


def clear_scans():
    proj = _project()
    if not proj:
        return "Aucun projet ouvert.", ""
    scans_dir = os.path.join(proj.project_dir, "scans")
    count = 0
    if os.path.isdir(scans_dir):
        for f in os.listdir(scans_dir):
            os.remove(os.path.join(scans_dir, f))
            count += 1
    return f"{count} fichier(s) supprimé(s) du dossier scans/.", "Aucun scan."


# ============================================================
# Onglet 4 — Analyse
# ============================================================

def analyse_scans(n_procs, threshold, multiple):
    proj = _project()
    if not proj:
        return "Aucun projet ouvert.", ""
    n = int(n_procs) if n_procs else 4
    thresh = float(threshold) if threshold else 0.15

    rc, out, err = runner.analyse_scans(
        proj.project_dir, n, thresh, multiple=bool(multiple)
    )
    log = _format_log(rc, out, err)

    db = _db()
    stats = ""
    if db:
        capture = db.get_capture_stats()
        layout = db.get_layout_info()
        stats = json.dumps(
            {"capture": capture, "layout": layout}, indent=2
        )
    return log, stats


# ============================================================
# Onglet 5 — Association
# ============================================================

def upload_student_list(file):
    proj = _project()
    if not proj:
        return "Aucun projet ouvert."
    if file is None:
        return "Aucun fichier sélectionné."
    proj.save_student_list(file)
    return "Liste étudiants importée."


def associate_students(list_key, notes_id):
    proj = _project()
    if not proj:
        return "Aucun projet ouvert.", ""
    student_list = proj.get_student_list_path()
    if not student_list:
        return "Aucune liste d'étudiants importée.", ""

    key = list_key.strip() if list_key else "ID"
    nid = notes_id.strip() if notes_id else "id"

    rc, out, err = runner.auto_associate(
        proj.project_dir, student_list, key, nid
    )
    log = _format_log(rc, out, err)

    db = _db()
    stats = ""
    if db:
        assoc = db.get_association_stats()
        stats = json.dumps(assoc, indent=2)
    return log, stats


# ============================================================
# Onglet 6 — Notation
# ============================================================

def detect_correction_copy(correction_state):
    """Détecte le numéro de copie du corrigé à partir du nom de fichier mémorisé."""
    db = _db()
    if not db:
        return "Aucun projet ouvert.", None
    if not correction_state:
        return "Aucun corrigé importé. Importez-le dans l'onglet Scans.", None
    result = db.find_correction_copy(correction_state)
    if result is None:
        return (
            f"Corrigé '{correction_state}' non trouvé dans les captures. "
            "Vérifiez que l'analyse a été lancée.",
            None,
        )
    student, copy = result
    return f"Corrigé détecté : student={student}, copy={copy}", copy


def calculate_grades(notemax, grain, arrondi, seuil, postcorrect,
                     postcorrect_copy):
    proj = _project()
    if not proj:
        return "Aucun projet ouvert.", None, None
    nmax = float(notemax) if notemax else 20
    g = float(grain) if grain else 0.5
    s = float(seuil) if seuil else 0.15
    a = arrondi if arrondi else "n"

    pc_student = None
    pc_copy = None
    if postcorrect and postcorrect_copy is not None:
        pc_student = 1
        pc_copy = int(postcorrect_copy)

    rc, out, err = runner.calculate_grades(
        proj.project_dir, seuil=s, grain=g, arrondi=a, notemax=nmax,
        postcorrect_student=pc_student, postcorrect_copy=pc_copy,
    )
    log = _format_log(rc, out, err)

    db = _db()
    results_df = None
    questions_df = None
    if db:
        results_df = db.get_scoring_results()
        questions_df = db.get_question_stats()
    return log, results_df, questions_df


# ============================================================
# Onglet 7 — Export
# ============================================================

def export_results(fmt):
    proj = _project()
    if not proj:
        return "Aucun projet ouvert.", None

    if fmt == "XLSX":
        return _export_xlsx(proj)

    # Noms exacts des modules Perl AMC (sensibles à la casse)
    amc_modules = {"CSV": "CSV", "ODS": "ods"}
    module_name = amc_modules.get(fmt, "CSV")
    ext = "ods" if fmt == "ODS" else "csv"
    output = os.path.join(proj.project_dir, "exports", f"results.{ext}")
    student_list = proj.get_student_list_path()

    rc, out, err = runner.export_results(
        proj.project_dir, output, module=module_name,
        student_list=student_list
    )
    log = _format_log(rc, out, err)

    if rc == 0 and os.path.exists(output):
        return log, output
    return log, None


def _export_xlsx(proj):
    """Exporte les résultats au format XLSX depuis les bases SQLite."""
    db = _db()
    if not db:
        return "Bases de données introuvables.", None

    results_df = db.get_scoring_results()
    questions_df = db.get_question_stats()

    if results_df is None or results_df.empty:
        return "Aucun résultat de notation disponible. Lancez d'abord la notation.", None

    exports_dir = os.path.join(proj.project_dir, "exports")
    os.makedirs(exports_dir, exist_ok=True)
    output = os.path.join(exports_dir, "results.xlsx")

    try:
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            results_df.to_excel(writer, sheet_name="Notes", index=False)
            if questions_df is not None and not questions_df.empty:
                questions_df.to_excel(
                    writer, sheet_name="Questions", index=False
                )
        return "Export XLSX réussi.", output
    except Exception as e:
        logger.error("Erreur export XLSX : %s", e)
        return f"Erreur lors de l'export XLSX : {e}", None


# ============================================================
# Interface Gradio
# ============================================================

def build_ui():
    with gr.Blocks(title="AMC - Auto Multiple Choice") as app:
        gr.Markdown("# Auto-Multiple-Choice — Interface Web")

        # --- Onglet 1 : Projet ---
        with gr.Tab("1. Projet"):
            with gr.Row():
                with gr.Column():
                    new_name = gr.Textbox(
                        label="Nom du nouveau projet"
                    )
                    btn_create = gr.Button("Créer le projet")
                with gr.Column():
                    project_list = gr.Dropdown(
                        label="Projets existants",
                        choices=AMCProject.list_projects(PROJECTS_BASE),
                        interactive=True,
                    )
                    with gr.Row():
                        btn_open = gr.Button("Ouvrir")
                        btn_refresh = gr.Button("Rafraîchir")

            gr.Markdown("### Importer un projet AMC existant")
            gr.Markdown(
                "Uploadez une archive ZIP d'un projet AMC existant "
                "(contenant le dossier `data/` avec les bases SQLite). "
                "Ceci est nécessaire si les scans proviennent d'une "
                "compilation précédente."
            )
            with gr.Row():
                import_name = gr.Textbox(
                    label="Nom du projet importé"
                )
                import_zip = gr.File(
                    label="Archive ZIP du projet AMC",
                    file_types=[".zip"],
                )
                btn_import_proj = gr.Button(
                    "Importer le projet", variant="secondary"
                )

            msg_project = gr.Textbox(label="Message", interactive=False)
            status_json = gr.Code(
                label="Statut du projet", language="json"
            )

            # Click handlers enregistrés après définition de tous les onglets

        # --- Onglet 2 : Préparation ---
        with gr.Tab("2. Préparation"):
            with gr.Row():
                source_upload = gr.File(
                    label="Upload fichier .tex",
                    file_types=[".tex"],
                )
                btn_upload_src = gr.Button("Importer .tex")
            source_editor = gr.Code(
                label="Éditeur source LaTeX",
                language=None,
                lines=20,
            )
            with gr.Group(visible=False) as images_group:
                gr.Markdown(
                    "### Images manquantes\n"
                    "Le fichier LaTeX référence des images absentes "
                    "du projet. Importez-les ci-dessous."
                )
                images_upload = gr.File(
                    label="Images (PNG, JPG, PDF, EPS)",
                    file_count="multiple",
                    file_types=[".png", ".jpg", ".jpeg", ".pdf",
                                ".eps", ".svg"],
                )
                btn_upload_img = gr.Button("Importer les images")
            msg_src = gr.Textbox(
                label="Message", interactive=False
            )
            btn_save_src = gr.Button("Sauvegarder la source")
            with gr.Row():
                n_copies = gr.Number(
                    label="Nombre de copies", value=30, precision=0
                )
                btn_compile = gr.Button(
                    "Compiler", variant="primary"
                )
            compile_log = gr.Textbox(
                label="Log de compilation",
                lines=15,
                interactive=False,
            )
            pdf_viewer = gr.HTML(label="Aperçu du PDF")
            pdf_output = gr.File(label="Télécharger le PDF")

            btn_upload_src.click(
                upload_source,
                inputs=[source_upload],
                outputs=[msg_src, source_editor, images_group],
            )
            btn_upload_img.click(
                upload_images,
                inputs=[images_upload],
                outputs=[msg_src, images_group],
            )
            btn_save_src.click(
                save_source_editor,
                inputs=[source_editor],
                outputs=[msg_src],
            )
            btn_compile.click(
                compile_document,
                inputs=[n_copies],
                outputs=[compile_log, pdf_output, pdf_viewer],
            )

            gr.Markdown("### Importer un fichier calage (.xy)")
            gr.Markdown(
                "Si vous avez un projet AMC existant dont les scans "
                "proviennent d'une compilation précédente, importez ici "
                "le fichier `.xy` original pour recalculer le layout."
            )
            with gr.Row():
                xy_upload = gr.File(
                    label="Fichier calage .xy",
                    file_types=[".xy"],
                )
                btn_import_xy = gr.Button("Importer et recalculer le layout")
            xy_log = gr.Textbox(
                label="Log meptex", lines=5, interactive=False
            )
            btn_import_xy.click(
                import_calage,
                inputs=[xy_upload],
                outputs=[xy_log],
            )

        # --- Onglet 3 : Scans ---
        correction_state = gr.State("")
        with gr.Tab("3. Scans"):
            scan_upload = gr.File(
                label="Upload scans étudiants (PDF, PNG, JPG)",
                file_count="multiple",
                file_types=[".pdf", ".png", ".jpg", ".jpeg", ".tif",
                            ".tiff"],
            )
            correction_upload = gr.File(
                label="Scan du corrigé enseignant (optionnel)",
                file_types=[".pdf", ".png", ".jpg", ".jpeg", ".tif",
                            ".tiff"],
            )
            with gr.Row():
                btn_import = gr.Button(
                    "Importer les scans", variant="primary"
                )
                btn_clear_scans = gr.Button(
                    "Effacer tous les scans", variant="stop"
                )
            import_log = gr.Textbox(
                label="Log d'import", lines=10, interactive=False
            )
            scan_list = gr.Textbox(
                label="Scans importés", lines=5, interactive=False
            )

            btn_import.click(
                import_scans,
                inputs=[scan_upload, correction_upload, correction_state],
                outputs=[import_log, scan_list, correction_state],
            )
            btn_clear_scans.click(
                clear_scans,
                outputs=[import_log, scan_list],
            )

        # --- Onglet 4 : Analyse ---
        with gr.Tab("4. Analyse"):
            with gr.Row():
                n_procs = gr.Number(
                    label="Processus parallèles", value=4, precision=0
                )
                threshold = gr.Number(
                    label="Seuil de détection", value=0.15
                )
            photocopy = gr.Checkbox(
                label="Copies photocopiées",
                value=False,
                info="Cochez si certaines feuilles ont été photocopiées avant distribution",
            )
            btn_analyse = gr.Button("Analyser", variant="primary")
            analyse_log = gr.Textbox(
                label="Log d'analyse", lines=15, interactive=False
            )
            analyse_stats = gr.Code(
                label="Statistiques", language="json"
            )

            btn_analyse.click(
                analyse_scans,
                inputs=[n_procs, threshold, photocopy],
                outputs=[analyse_log, analyse_stats],
            )

        # --- Onglet 5 : Association ---
        with gr.Tab("5. Association"):
            student_upload = gr.File(
                label="Upload liste étudiants (CSV)",
                file_types=[".csv"],
            )
            btn_upload_students = gr.Button("Importer la liste")
            with gr.Row():
                list_key = gr.Textbox(
                    label="Colonne clé (liste)", value="ID"
                )
                notes_id = gr.Textbox(
                    label="Identifiant notes", value="id"
                )
            btn_associate = gr.Button("Associer", variant="primary")
            assoc_log = gr.Textbox(
                label="Log d'association", lines=10, interactive=False
            )
            assoc_stats = gr.Code(
                label="Résultats association", language="json"
            )
            msg_students = gr.Textbox(
                label="Message", interactive=False
            )

            btn_upload_students.click(
                upload_student_list,
                inputs=[student_upload],
                outputs=[msg_students],
            )
            btn_associate.click(
                associate_students,
                inputs=[list_key, notes_id],
                outputs=[assoc_log, assoc_stats],
            )

        # --- Onglet 6 : Notation ---
        with gr.Tab("6. Notation"):
            with gr.Row():
                notemax = gr.Number(label="Note max", value=20)
                grain = gr.Number(label="Grain", value=0.5)
                arrondi = gr.Dropdown(
                    label="Arrondi",
                    choices=["n", "i", "s"],
                    value="n",
                )
                seuil = gr.Number(label="Seuil", value=0.15)
            gr.Markdown("### Postcorrect (photocopie)")
            postcorrect_check = gr.Checkbox(
                label="Mode postcorrect",
                value=False,
                info="Activez si vous utilisez des copies photocopiées "
                     "avec un corrigé scanné. Le barème sera déduit "
                     "de la copie corrigée.",
            )
            with gr.Row():
                btn_detect = gr.Button("Détecter le corrigé")
                postcorrect_copy = gr.Number(
                    label="N° copie corrigé",
                    precision=0,
                    info="Numéro de copie du corrigé (détecté ou saisi manuellement)",
                )
            detect_msg = gr.Textbox(
                label="Détection", interactive=False
            )
            btn_detect.click(
                detect_correction_copy,
                inputs=[correction_state],
                outputs=[detect_msg, postcorrect_copy],
            )
            btn_grade = gr.Button("Calculer les notes", variant="primary")
            grade_log = gr.Textbox(
                label="Log de notation", lines=10, interactive=False
            )
            results_table = gr.Dataframe(
                label="Notes par étudiant"
            )
            questions_table = gr.Dataframe(
                label="Statistiques par question"
            )

            btn_grade.click(
                calculate_grades,
                inputs=[notemax, grain, arrondi, seuil, postcorrect_check,
                        postcorrect_copy],
                outputs=[grade_log, results_table, questions_table],
            )

        # --- Onglet 7 : Export ---
        with gr.Tab("7. Export"):
            export_fmt = gr.Dropdown(
                label="Format d'export",
                choices=["CSV", "ODS", "XLSX"],
                value="CSV",
            )
            btn_export = gr.Button("Exporter", variant="primary")
            export_log = gr.Textbox(
                label="Log d'export", lines=5, interactive=False
            )
            export_file = gr.File(label="Fichier exporté")

            btn_export.click(
                export_results,
                inputs=[export_fmt],
                outputs=[export_log, export_file],
            )

        # ============================================================
        # Enregistrement des handlers Projet (après tous les onglets,
        # pour pouvoir cibler des composants définis dans d'autres tabs)
        # ============================================================

        project_data_outputs = [
            source_editor, images_group, pdf_viewer, pdf_output,
            scan_list, results_table, questions_table,
        ]

        btn_create.click(
            create_project,
            inputs=[new_name],
            outputs=[msg_project, status_json, project_list]
                    + project_data_outputs,
        )
        btn_open.click(
            open_project,
            inputs=[project_list],
            outputs=[msg_project, status_json] + project_data_outputs,
        )
        btn_refresh.click(
            refresh_projects, outputs=[project_list]
        )
        btn_import_proj.click(
            import_project,
            inputs=[import_name, import_zip],
            outputs=[msg_project, status_json, project_list]
                    + project_data_outputs,
        )

    return app


if __name__ == "__main__":
    app = build_ui()
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        allowed_paths=[PROJECTS_BASE],
    )
