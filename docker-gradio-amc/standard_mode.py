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

"""Mode Standard (workflow guidé) pour l'interface Gradio AMC."""

import json
import logging
import os

import gradio as gr

from amc_project import AMCProject

logger = logging.getLogger(__name__)


# ============================================================
# Constantes et valeurs par défaut
# ============================================================

STD_N_PROCS = 4
STD_THRESHOLD = 0.5
STD_GRAIN = 0.5
STD_ARRONDI = "n"
STD_SEUIL = 0.5
STD_LIST_KEY = "ID"
STD_NOTES_ID = "id"

NUM_STEPS = 6
STEP_LABELS = [
    "1. Projet & Source",
    "2. Compilation",
    "3. Scans",
    "4. Analyse & Vérification",
    "5. Association & Notation",
    "6. Export",
]


# ============================================================
# Barre de progression
# ============================================================

def compute_progress(project_path):
    """Calcule les statuts des 6 étapes à partir de l'état du projet.

    Returns:
        Liste de 6 booléens indiquant si chaque étape est complétée.
    """
    if not project_path:
        return [False] * NUM_STEPS
    try:
        proj = AMCProject(project_path)
        status = proj.get_status()
    except Exception:
        return [False] * NUM_STEPS

    return [
        status.get("source", False),
        status.get("compiled", False),
        status.get("scans", False),
        status.get("analysed", False),
        status.get("associated", False) and status.get("graded", False),
        status.get("exported", False),
    ]


def _render_progress(steps_done):
    """Génère le HTML de la barre de progression.

    Args:
        steps_done: Liste de 6 booléens.

    Returns:
        Chaîne HTML.
    """
    items = []
    for i, (label, done) in enumerate(zip(STEP_LABELS, steps_done)):
        icon = "&#10004;" if done else "&#9675;"
        color = "#22c55e" if done else "#9ca3af"
        bg = "#dcfce7" if done else "#f3f4f6"
        items.append(
            f'<div style="display:flex;flex-direction:column;align-items:center;'
            f'min-width:100px;flex:1">'
            f'<div style="width:32px;height:32px;border-radius:50%;'
            f'background:{bg};color:{color};display:flex;align-items:center;'
            f'justify-content:center;font-size:18px;font-weight:bold;'
            f'border:2px solid {color}">{icon}</div>'
            f'<div style="font-size:11px;margin-top:4px;text-align:center;'
            f'color:{color};font-weight:{"600" if done else "400"}">'
            f'{label}</div></div>'
        )
        if i < NUM_STEPS - 1:
            bar_color = "#22c55e" if done else "#d1d5db"
            items.append(
                f'<div style="flex:1;height:3px;background:{bar_color};'
                f'align-self:center;margin-top:-14px;min-width:20px"></div>'
            )

    html = (
        '<div style="display:flex;align-items:flex-start;'
        'justify-content:center;gap:0;padding:16px 8px;'
        'background:#fff;border-radius:8px;border:1px solid #e5e7eb;'
        'margin-bottom:16px">'
        + "".join(items)
        + '</div>'
    )
    return html


def update_progress_html(project_path):
    """Retourne le HTML de la barre de progression mise à jour."""
    steps = compute_progress(project_path)
    return _render_progress(steps)


# ============================================================
# Navigation
# ============================================================

def navigate_step(current_step, direction, project_path):
    """Calcule le nouvel index d'étape et retourne les mises à jour UI.

    Args:
        current_step: Index courant (0..5).
        direction: "next" ou "prev".
        project_path: Chemin du projet (pour la progression).

    Returns:
        Tuple (new_step, *6 gr.update(visible=...), progress_html,
               prev_interactive, next_interactive).
    """
    if direction == "next":
        new_step = min(current_step + 1, NUM_STEPS - 1)
    else:
        new_step = max(current_step - 1, 0)

    visibilities = [gr.update(visible=(i == new_step)) for i in range(NUM_STEPS)]
    progress_html = update_progress_html(project_path)
    prev_interactive = new_step > 0
    next_interactive = new_step < NUM_STEPS - 1

    return (new_step, *visibilities, progress_html,
            gr.update(interactive=prev_interactive),
            gr.update(interactive=next_interactive))


# ============================================================
# Wrappers mode standard
# ============================================================

def std_analyse_scans(project_path):
    """Analyse les scans avec les paramètres par défaut du mode standard."""
    import app as app_module
    return app_module.analyse_scans(
        project_path, STD_N_PROCS, STD_THRESHOLD, False
    )


def std_calculate_grades(project_path, notemax, postcorrect, pc_copy):
    """Calcule les notes avec les paramètres simplifiés du mode standard."""
    import app as app_module
    return app_module.calculate_grades(
        project_path, notemax, STD_GRAIN, STD_ARRONDI, STD_SEUIL,
        postcorrect, pc_copy,
    )


def std_associate_students(project_path):
    """Association automatique avec les paramètres par défaut."""
    import app as app_module
    return app_module.associate_students(
        project_path, STD_LIST_KEY, STD_NOTES_ID
    )


def std_create_project(project_path, name):
    """Crée un projet et remappe les sorties pour l'UI standard (6 sorties).

    Returns:
        (project_path, msg, source_content, images_group_visible,
         project_list_update, status_json)
    """
    import app as app_module
    result = app_module.create_project(project_path, name)
    # create_project returns:
    #   0: project_path, 1: msg, 2: status_json, 3: project_list_update,
    #   4: source_content, 5: images_group, 6: pdf_viewer_html,
    #   7: pdf_path, 8: scan_list_text, 9: results_df, 10: questions_df
    return (
        result[0],   # project_path
        result[1],   # msg
        result[4],   # source_content
        result[5],   # images_group visible
        result[3],   # project_list update
        result[2],   # status_json
    )


def std_open_project(project_path, name):
    """Ouvre un projet et remappe les sorties pour l'UI standard (6 sorties).

    Returns:
        (project_path, msg, source_content, images_group_visible,
         pdf_viewer_html, scan_list_text)
    """
    import app as app_module
    result = app_module.open_project(project_path, name)
    # open_project returns:
    #   0: project_path, 1: msg, 2: status_json,
    #   3: source_content, 4: images_group, 5: pdf_viewer_html,
    #   6: pdf_path, 7: scan_list_text, 8: results_df, 9: questions_df
    return (
        result[0],   # project_path
        result[1],   # msg
        result[3],   # source_content
        result[4],   # images_group visible
        result[5],   # pdf_viewer_html
        result[7],   # scan_list_text
    )


# ============================================================
# UI du mode standard
# ============================================================

def build_standard_ui(projects_base):
    """Construit l'UI wizard 6 étapes du mode standard.

    Args:
        projects_base: Chemin du répertoire de base des projets.

    Returns:
        Dict de composants Gradio à câbler dans app.py.
    """
    with gr.Column(visible=True) as std_container:
        std_progress = gr.HTML(value=_render_progress([False] * NUM_STEPS))
        std_step_state = gr.State(0)

        # --- Étape 1 : Projet & Source ---
        with gr.Column(visible=True) as std_step1:
            gr.Markdown("## Étape 1 : Projet & Source")
            with gr.Row():
                with gr.Column():
                    std_new_name = gr.Textbox(
                        label="Nom du nouveau projet"
                    )
                    std_btn_create = gr.Button("Créer le projet")
                with gr.Column():
                    std_project_list = gr.Dropdown(
                        label="Projets existants",
                        choices=AMCProject.list_projects(projects_base),
                        interactive=True,
                    )
                    with gr.Row():
                        std_btn_open = gr.Button("Ouvrir")
                        std_btn_refresh = gr.Button("Rafraîchir")
            std_msg_project = gr.Textbox(
                label="Message", interactive=False
            )
            std_source_upload = gr.File(
                label="Upload fichier .tex",
                file_types=[".tex"],
            )
            std_btn_upload_src = gr.Button("Importer .tex")
            std_source_editor = gr.Code(
                label="Éditeur source LaTeX",
                language=None,
                lines=15,
            )
            with gr.Group(visible=False) as std_images_group:
                gr.Markdown(
                    "### Images manquantes\n"
                    "Le fichier LaTeX référence des images absentes. "
                    "Importez-les ci-dessous."
                )
                std_images_upload = gr.File(
                    label="Images (PNG, JPG, PDF, EPS)",
                    file_count="multiple",
                    file_types=[".png", ".jpg", ".jpeg", ".pdf",
                                ".eps", ".svg"],
                )
                std_btn_upload_img = gr.Button("Importer les images")
            std_msg_src = gr.Textbox(
                label="Message source", interactive=False
            )

        # --- Étape 2 : Compilation ---
        with gr.Column(visible=False) as std_step2:
            gr.Markdown("## Étape 2 : Compilation")
            with gr.Row():
                std_n_copies = gr.Number(
                    label="Nombre de copies", value=30, precision=0
                )
                std_btn_compile = gr.Button(
                    "Compiler", variant="primary"
                )
            std_compile_log = gr.Textbox(
                label="Log de compilation",
                lines=15,
                interactive=False,
            )
            std_pdf_viewer = gr.HTML(label="Aperçu du PDF")
            std_pdf_output = gr.File(label="Télécharger le PDF")

        # --- Étape 3 : Scans ---
        with gr.Column(visible=False) as std_step3:
            gr.Markdown("## Étape 3 : Scans")
            std_scan_upload = gr.File(
                label="Upload scans étudiants (PDF, PNG, JPG)",
                file_count="multiple",
                file_types=[".pdf", ".png", ".jpg", ".jpeg", ".tif",
                            ".tiff"],
            )
            std_correction_upload = gr.File(
                label="Scan du corrigé enseignant (optionnel)",
                file_types=[".pdf", ".png", ".jpg", ".jpeg", ".tif",
                            ".tiff"],
            )
            std_btn_import_scans = gr.Button(
                "Importer les scans", variant="primary"
            )
            std_import_log = gr.Textbox(
                label="Log d'import", lines=10, interactive=False
            )
            std_scan_list = gr.Textbox(
                label="Scans importés", lines=5, interactive=False
            )

        # --- Étape 4 : Analyse & Vérification ---
        with gr.Column(visible=False) as std_step4:
            gr.Markdown("## Étape 4 : Analyse & Vérification")
            std_btn_analyse = gr.Button("Analyser les scans", variant="primary")
            std_analyse_log = gr.Textbox(
                label="Log d'analyse", lines=15, interactive=False
            )
            std_analyse_stats = gr.Code(
                label="Statistiques", language="json"
            )
            gr.Markdown("### Vérification des cases")
            with gr.Row(equal_height=True):
                with gr.Column():
                    std_page_selector = gr.Dropdown(
                        label="Page scannée",
                        choices=[],
                        interactive=True,
                    )
                    with gr.Row():
                        std_btn_load_page = gr.Button("Charger la page")
                        std_btn_refresh_pages = gr.Button("Rafraîchir la liste")
                with gr.Column():
                    std_code_search = gr.Textbox(
                        label="Rechercher par code",
                        placeholder="ex: 1234",
                    )
                    std_btn_search = gr.Button("Rechercher")
            with gr.Row(equal_height=True):
                with gr.Column():
                    std_scan_image = gr.Image(
                        label="Scan annoté", interactive=False,
                    )
                with gr.Column():
                    std_question_selector = gr.Dropdown(
                        label="Question",
                        choices=[],
                        interactive=True,
                    )
                    std_answer_selector = gr.Dropdown(
                        label="Case",
                        choices=[],
                        interactive=True,
                    )
                    with gr.Row():
                        std_btn_cocher = gr.Button("Cocher")
                        std_btn_decocher = gr.Button("Décocher")
            std_verif_info = gr.Textbox(
                label="Information", interactive=False
            )
            std_boxes_table = gr.Dataframe(
                label="Cases de la page",
            )

        # --- Étape 5 : Association & Notation ---
        with gr.Column(visible=False) as std_step5:
            gr.Markdown("## Étape 5 : Association & Notation")
            gr.Markdown("### Liste étudiants")
            std_student_upload = gr.File(
                label="Upload liste étudiants (CSV)",
                file_types=[".csv"],
            )
            std_btn_upload_students = gr.Button("Importer la liste")
            std_msg_students = gr.Textbox(
                label="Message", interactive=False
            )
            std_btn_associate = gr.Button(
                "Associer automatiquement", variant="primary"
            )
            std_assoc_log = gr.Textbox(
                label="Log d'association", lines=10, interactive=False
            )
            std_assoc_stats = gr.Code(
                label="Résultats association", language="json"
            )
            gr.Markdown("### Notation")
            with gr.Row():
                std_notemax = gr.Number(label="Note max", value=20)
            std_postcorrect_check = gr.Checkbox(
                label="Mode postcorrect",
                value=False,
                info="Activez si vous utilisez des copies photocopiées "
                     "avec un corrigé scanné.",
            )
            with gr.Row():
                std_btn_detect = gr.Button("Détecter le corrigé")
                std_postcorrect_copy = gr.Number(
                    label="N° copie corrigé",
                    precision=0,
                )
            std_detect_msg = gr.Textbox(
                label="Détection", interactive=False
            )
            std_btn_grade = gr.Button(
                "Calculer les notes", variant="primary"
            )
            std_grade_log = gr.Textbox(
                label="Log de notation", lines=10, interactive=False
            )
            std_results_table = gr.Dataframe(
                label="Notes par étudiant"
            )
            std_questions_table = gr.Dataframe(
                label="Statistiques par question"
            )

        # --- Étape 6 : Export ---
        with gr.Column(visible=False) as std_step6:
            gr.Markdown("## Étape 6 : Export")
            std_export_fmt = gr.Dropdown(
                label="Format d'export",
                choices=["CSV", "ODS", "XLSX"],
                value="CSV",
            )
            std_btn_export = gr.Button("Exporter", variant="primary")
            std_export_log = gr.Textbox(
                label="Log d'export", lines=5, interactive=False
            )
            std_export_file = gr.File(label="Fichier exporté")

        # --- Navigation ---
        with gr.Row():
            std_btn_prev = gr.Button(
                "Précédent", interactive=False
            )
            std_btn_next = gr.Button("Suivant")

    steps = [std_step1, std_step2, std_step3, std_step4, std_step5, std_step6]

    return {
        "container": std_container,
        "progress": std_progress,
        "step_state": std_step_state,
        "steps": steps,
        # Navigation
        "btn_prev": std_btn_prev,
        "btn_next": std_btn_next,
        # Step 1 — Projet & Source
        "new_name": std_new_name,
        "btn_create": std_btn_create,
        "project_list": std_project_list,
        "btn_open": std_btn_open,
        "btn_refresh": std_btn_refresh,
        "msg_project": std_msg_project,
        "source_upload": std_source_upload,
        "btn_upload_src": std_btn_upload_src,
        "source_editor": std_source_editor,
        "images_group": std_images_group,
        "images_upload": std_images_upload,
        "btn_upload_img": std_btn_upload_img,
        "msg_src": std_msg_src,
        # Step 2 — Compilation
        "n_copies": std_n_copies,
        "btn_compile": std_btn_compile,
        "compile_log": std_compile_log,
        "pdf_viewer": std_pdf_viewer,
        "pdf_output": std_pdf_output,
        # Step 3 — Scans
        "scan_upload": std_scan_upload,
        "correction_upload": std_correction_upload,
        "btn_import_scans": std_btn_import_scans,
        "import_log": std_import_log,
        "scan_list": std_scan_list,
        # Step 4 — Analyse & Vérification
        "btn_analyse": std_btn_analyse,
        "analyse_log": std_analyse_log,
        "analyse_stats": std_analyse_stats,
        "page_selector": std_page_selector,
        "btn_load_page": std_btn_load_page,
        "btn_refresh_pages": std_btn_refresh_pages,
        "code_search": std_code_search,
        "btn_search": std_btn_search,
        "scan_image": std_scan_image,
        "question_selector": std_question_selector,
        "answer_selector": std_answer_selector,
        "btn_cocher": std_btn_cocher,
        "btn_decocher": std_btn_decocher,
        "verif_info": std_verif_info,
        "boxes_table": std_boxes_table,
        # Step 5 — Association & Notation
        "student_upload": std_student_upload,
        "btn_upload_students": std_btn_upload_students,
        "msg_students": std_msg_students,
        "btn_associate": std_btn_associate,
        "assoc_log": std_assoc_log,
        "assoc_stats": std_assoc_stats,
        "notemax": std_notemax,
        "postcorrect_check": std_postcorrect_check,
        "btn_detect": std_btn_detect,
        "postcorrect_copy": std_postcorrect_copy,
        "detect_msg": std_detect_msg,
        "btn_grade": std_btn_grade,
        "grade_log": std_grade_log,
        "results_table": std_results_table,
        "questions_table": std_questions_table,
        # Step 6 — Export
        "export_fmt": std_export_fmt,
        "btn_export": std_btn_export,
        "export_log": std_export_log,
        "export_file": std_export_file,
    }
