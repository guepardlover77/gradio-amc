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
import sqlite3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import gradio as gr
import pandas as pd
from PIL import Image, ImageDraw

from amc_wrapper import AMCCommandRunner
from amc_project import AMCProject
from amc_database import AMCDatabase, DEFAULT_CREM_DIGITS, DEFAULT_CREM_ANSWERS
from standard_mode import (
    build_standard_ui, navigate_step, update_progress_html,
    std_analyse_scans, std_calculate_grades, std_associate_students,
    std_create_project, std_open_project,
)

PROJECTS_BASE = os.environ.get("AMC_PROJECTS_DIR", "/projects")

runner = AMCCommandRunner()


# ---------- Helpers ----------

def _project(path):
    """Retourne l'AMCProject courant ou None."""
    if path:
        return AMCProject(path)
    return None


def _db(path):
    """Retourne l'AMCDatabase du projet courant ou None."""
    if path:
        data_dir = os.path.join(path, "data")
        return AMCDatabase(data_dir)
    return None


def _validate_number(value, default, min_val, max_val):
    """Valide et borne une valeur numérique."""
    try:
        n = float(value) if value is not None else default
    except (TypeError, ValueError):
        return default
    if n < min_val:
        return min_val
    if n > max_val:
        return max_val
    return n


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
    except (IOError, OSError) as e:
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


def create_project(project_path, name):
    if not name or not name.strip():
        return (project_path, "Veuillez entrer un nom de projet.", "",
                gr.update(choices=[]), *_empty_project_data())
    name = name.strip()
    try:
        proj = AMCProject.create_new(PROJECTS_BASE, name)
        new_path = proj.project_dir
        status = proj.get_status()
        projects = AMCProject.list_projects(PROJECTS_BASE)
        return (
            new_path,
            f"Projet '{name}' créé avec succès.",
            json.dumps(status, indent=2),
            gr.update(choices=projects, value=name),
            *_empty_project_data(),
        )
    except FileExistsError:
        return (project_path, f"Le projet '{name}' existe déjà.", "",
                gr.update(choices=[]), *_empty_project_data())


def open_project(project_path, name):
    if not name:
        return (project_path, "Sélectionnez un projet.", "",
                *_empty_project_data())
    path = os.path.join(PROJECTS_BASE, name)
    if not os.path.isdir(path):
        return (project_path, f"Projet '{name}' introuvable.", "",
                *_empty_project_data())
    proj = AMCProject(path)
    status = proj.get_status()
    return (
        path,
        f"Projet '{name}' ouvert.",
        json.dumps(status, indent=2),
        *_load_project_data(proj),
    )


def import_project(project_path, name, zip_file):
    if not name or not name.strip():
        return (project_path, "Veuillez entrer un nom de projet.", "",
                gr.update(choices=[]), *_empty_project_data())
    if zip_file is None:
        return (project_path, "Veuillez sélectionner une archive ZIP.", "",
                gr.update(choices=[]), *_empty_project_data())
    name = name.strip()
    try:
        proj = AMCProject.import_existing(PROJECTS_BASE, name, zip_file)
        new_path = proj.project_dir
        status = proj.get_status()
        projects = AMCProject.list_projects(PROJECTS_BASE)
        return (
            new_path,
            f"Projet '{name}' importé avec succès.",
            json.dumps(status, indent=2),
            gr.update(choices=projects, value=name),
            *_load_project_data(proj),
        )
    except FileExistsError:
        return (project_path, f"Le projet '{name}' existe déjà.", "",
                gr.update(choices=[]), *_empty_project_data())
    except (OSError, ValueError) as e:
        return (project_path, f"Erreur lors de l'import : {e}", "",
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


def upload_source(project_path, file):
    proj = _project(project_path)
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


def upload_images(project_path, files):
    proj = _project(project_path)
    if not proj:
        return "Aucun projet ouvert.", gr.update()
    if not files:
        return "Aucun fichier sélectionné.", gr.update()
    imported = []
    overwritten = []
    for f in files:
        basename = os.path.basename(f)
        dest = os.path.join(proj.project_dir, basename)
        if os.path.exists(dest):
            overwritten.append(basename)
        shutil.copy2(f, dest)
        imported.append(basename)
    missing = _check_missing_images(proj)
    msg = f"Images importées : {', '.join(imported)}"
    if overwritten:
        msg += f"\nFichiers écrasés : {', '.join(overwritten)}"
    if missing:
        msg += f"\nEncore manquantes : {', '.join(missing)}"
    return msg, gr.update(visible=bool(missing))


def save_source_editor(project_path, content):
    proj = _project(project_path)
    if not proj:
        return "Aucun projet ouvert."
    proj.save_source(content=content)
    return "Source sauvegardée."


def compile_document(project_path, n_copies):
    logger.info("compile_document called with n_copies=%s", n_copies)
    proj = _project(project_path)
    if not proj:
        return "Aucun projet ouvert.", None, ""
    source = proj.get_source_path()
    if not source:
        return "Aucun fichier source .tex trouvé.", None, ""
    n = int(_validate_number(n_copies, 30, 1, 500))
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


def import_calage(project_path, xy_file):
    """Importe un fichier calage .xy existant et re-calcule le layout."""
    proj = _project(project_path)
    if not proj:
        return "Aucun projet ouvert."
    if xy_file is None:
        return "Aucun fichier sélectionné."

    build_dir = os.path.join(proj.project_dir, "_build")
    os.makedirs(build_dir, exist_ok=True)
    dest = os.path.join(build_dir, "DOC-calage.xy")
    existed = os.path.exists(dest)
    shutil.copy2(xy_file, dest)

    rc, out, err = runner.compute_layout(proj.project_dir, dest)
    log = _format_log(rc, out, err)
    if existed:
        log = "⚠ Fichier calage.xy existant écrasé.\n" + log
    return log


# ============================================================
# Onglet 3 — Scans
# ============================================================

def import_scans(project_path, files, correction_file, correction_state):
    proj = _project(project_path)
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


def clear_scans(project_path):
    proj = _project(project_path)
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

def analyse_scans(project_path, n_procs, threshold, multiple):
    proj = _project(project_path)
    if not proj:
        return "Aucun projet ouvert.", ""
    n = int(_validate_number(n_procs, 4, 1, 32))
    thresh = _validate_number(threshold, 0.5, 0.01, 0.99)

    rc, out, err = runner.analyse_scans(
        proj.project_dir, n, thresh, multiple=bool(multiple)
    )
    log = _format_log(rc, out, err)

    db = _db(project_path)
    stats = ""
    if db:
        capture = db.get_capture_stats()
        layout = db.get_layout_info()
        stats = json.dumps(
            {"capture": capture, "layout": layout}, indent=2
        )
    return log, stats


# ============================================================
# Onglet 5 — Vérification
# ============================================================

def _box_is_ticked(box, seuil=0.5):
    """Détermine si une case est cochée (manual prioritaire, sinon black/total)."""
    manual = box["manual"]
    if manual is not None and manual >= 0:
        return manual == 1
    total = box["total"] or 1
    black = box["black"] or 0
    return (black / total) > seuil


def render_annotated_scan(scan_path, boxes):
    """Dessine des rectangles colorés sur le scan pour chaque case réponse."""
    img = Image.open(scan_path).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")
    for box in boxes:
        is_ticked = _box_is_ticked(box)
        fill = (0, 200, 0, 80) if is_ticked else (200, 0, 0, 80)
        border = (0, 200, 0, 255) if is_ticked else (200, 0, 0, 255)
        has_manual = box["manual"] is not None and box["manual"] >= 0
        width = 4 if has_manual else 2
        coords = [box["x1"], box["y1"], box["x2"], box["y2"]]
        draw.rectangle(coords, fill=fill, outline=border, width=width)
    img = Image.alpha_composite(img, overlay)
    return img.convert("RGB")


def _boxes_to_dataframe(boxes):
    """Convertit les boxes en DataFrame pour affichage."""
    rows = []
    for box in boxes:
        total = box["total"] or 1
        black = box["black"] or 0
        pct = round(100 * black / total, 1)
        is_ticked = _box_is_ticked(box)
        manual = box["manual"]
        if manual is not None and manual >= 0:
            etat = "Coché (manuel)" if manual == 1 else "Non-coché (manuel)"
        else:
            etat = "Coché (auto)" if is_ticked else "Non-coché (auto)"
        rows.append({
            "Question": box["question"],
            "Réponse": box["answer"],
            "Noircissement %": pct,
            "État": etat,
        })
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["Question", "Réponse", "Noircissement %", "État"]
    )


def load_verification_pages(project_path):
    """Remplit le dropdown avec les pages scannées disponibles.

    Le label inclut le code à 4 chiffres quand il est disponible :
    ``[1234] Copie 5 — Page 1`` sinon ``Copie 5 — Page 1``.
    Le format interne reste parsable par ``_parse_page_selection()``.
    """
    db = _db(project_path)
    if not db:
        logger.warning("load_verification_pages: aucun projet ouvert")
        return gr.update(choices=[], value=None)
    pages = db.get_captured_pages()
    logger.info("load_verification_pages: %d page(s) trouvée(s)", len(pages))
    if not pages:
        return gr.update(choices=[], value=None)
    codes = db.get_crem_codes()
    choices = []
    for p in pages:
        code = codes.get((p["student"], p["copy"]))
        if code:
            label = (
                f"[{code}] Étudiant {p['student']} - "
                f"Page {p['page']} (copie {p['copy']})"
            )
        else:
            label = (
                f"Étudiant {p['student']} - "
                f"Page {p['page']} (copie {p['copy']})"
            )
        choices.append(label)
    first = choices[0] if choices else None
    return gr.update(choices=choices, value=first)


def _parse_page_selection(sel):
    """Parse le label dropdown → (student, page, copy).

    Formats acceptés :
    - ``Étudiant X - Page Y (copie Z)``
    - ``[CODE] Étudiant X - Page Y (copie Z)``
    """
    if not sel:
        return None, None, None
    m = re.match(
        r"(?:\[[^\]]*\]\s*)?Étudiant\s+(\d+)\s*-\s*Page\s+(\d+)\s*\(copie\s+(\d+)\)",
        sel,
    )
    if not m:
        return None, None, None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def search_by_code(project_path, code_query):
    """Recherche exacte par code CREM et charge directement la page trouvée.

    Returns:
        Tuple (page_selector_update, image, info, dataframe,
               question_dd_update, answer_dd_update).
    """
    empty = (gr.update(), None, "", None,
             gr.update(choices=[], value=None),
             gr.update(choices=[], value=None))
    if not code_query or not code_query.strip():
        return (load_verification_pages(project_path), None, "", None,
                gr.update(choices=[], value=None),
                gr.update(choices=[], value=None))
    db = _db(project_path)
    if not db:
        return (gr.update(choices=[], value=None),
                None, "Aucun projet ouvert.", None,
                gr.update(choices=[], value=None),
                gr.update(choices=[], value=None))
    pages = db.get_captured_pages()
    if not pages:
        return (gr.update(choices=[], value=None),
                None, "Aucune page scannée.", None,
                gr.update(choices=[], value=None),
                gr.update(choices=[], value=None))
    codes = db.get_crem_codes()
    query = code_query.strip()

    # Recherche exacte
    choices = []
    for p in pages:
        code = codes.get((p["student"], p["copy"]))
        if code and code == query:
            label = (
                f"[{code}] Étudiant {p['student']} - "
                f"Page {p['page']} (copie {p['copy']})"
            )
            choices.append(label)

    if not choices:
        return (gr.update(choices=[], value=None),
                None, f"Aucune copie avec le code '{query}'.", None,
                gr.update(choices=[], value=None),
                gr.update(choices=[], value=None))

    first = choices[0]
    # Charger directement la première page trouvée
    img, info, df, qdd, add = load_page_image(project_path, first)
    return (gr.update(choices=choices, value=first), img, info, df, qdd, add)


def _is_crem_question(question_id, answer_count):
    """Détermine si une question est un chiffre du code CREM."""
    return question_id <= DEFAULT_CREM_DIGITS and answer_count == DEFAULT_CREM_ANSWERS


def _build_question_choices(boxes):
    """Construit les choix du dropdown de questions à partir des boxes.

    Returns:
        Liste de labels : "Code [1]", "Code [2]", ..., "Q5", "Q6", ...
    """
    questions = {}
    for box in boxes:
        q = box["question"]
        questions.setdefault(q, 0)
        questions[q] += 1

    choices = []
    for q in sorted(questions):
        if _is_crem_question(q, questions[q]):
            choices.append(f"Code [{q}]")
        else:
            choices.append(f"Q{q}")
    return choices


def _build_answer_choices(boxes, question_id):
    """Construit les choix du dropdown de cases pour une question donnée."""
    choices = []
    for box in boxes:
        if box["question"] != question_id:
            continue
        is_ticked = _box_is_ticked(box)
        manual = box["manual"]
        if manual is not None and manual >= 0:
            etat = "Coché (manuel)" if manual == 1 else "Non-coché (manuel)"
        else:
            etat = "Coché (auto)" if is_ticked else "Non-coché (auto)"
        choices.append(f"{box['answer']} - {etat}")
    return choices


def _parse_question_choice(choice):
    """Parse un label de question → question_id.

    Formats: "Code [1]" → 1, "Q5" → 5.
    """
    if not choice:
        return None
    m = re.match(r"Code\s*\[(\d+)\]", choice)
    if m:
        return int(m.group(1))
    m = re.match(r"Q(\d+)$", choice)
    if m:
        return int(m.group(1))
    return None


def _parse_answer_choice(choice):
    """Parse un label de case → answer_id.

    Format: "3 - Coché (auto)" → 3.
    """
    if not choice:
        return None
    m = re.match(r"(\d+)\s*-\s", choice)
    if m:
        return int(m.group(1))
    return None


def _empty_page_result():
    return (None, "", None,
            gr.update(choices=[], value=None),
            gr.update(choices=[], value=None))


def load_page_image(project_path, page_selection):
    """Charge le scan annoté (image PIL) et le tableau des cases."""
    db = _db(project_path)
    if not db:
        logger.warning("load_page_image: aucun projet ouvert")
        return (None, "Aucun projet ouvert.", None,
                gr.update(choices=[], value=None),
                gr.update(choices=[], value=None))
    student, page, copy = _parse_page_selection(page_selection)
    if student is None:
        logger.warning("load_page_image: sélection invalide %r", page_selection)
        return (None, "Sélectionnez une page.", None,
                gr.update(choices=[], value=None),
                gr.update(choices=[], value=None))
    logger.info(
        "load_page_image: student=%s page=%s copy=%s", student, page, copy
    )
    try:
        scan_path = db.get_scan_path(student, page, copy)
        logger.info("load_page_image: scan_path=%s", scan_path)
        if not scan_path or not os.path.exists(scan_path):
            return (None, f"Scan introuvable : {scan_path}", None,
                    gr.update(choices=[], value=None),
                    gr.update(choices=[], value=None))
        boxes = db.get_page_boxes(student, page, copy)
        logger.info("load_page_image: %d case(s) trouvée(s)", len(boxes))
        if not boxes:
            return (None, "Aucune case détectée sur cette page.", None,
                    gr.update(choices=[], value=None),
                    gr.update(choices=[], value=None))
        img = render_annotated_scan(scan_path, boxes)
        df = _boxes_to_dataframe(boxes)
        q_choices = _build_question_choices(boxes)
        first_q = q_choices[0] if q_choices else None
        first_qid = _parse_question_choice(first_q)
        a_choices = _build_answer_choices(boxes, first_qid) if first_qid else []
        first_a = a_choices[0] if a_choices else None
        return (img, f"{len(boxes)} case(s) affichée(s).", df,
                gr.update(choices=q_choices, value=first_q),
                gr.update(choices=a_choices, value=first_a))
    except (sqlite3.OperationalError, OSError) as e:
        logger.exception("load_page_image: erreur")
        return (None, f"Erreur : {e}", None,
                gr.update(choices=[], value=None),
                gr.update(choices=[], value=None))


def select_question(project_path, page_selection, question_choice):
    """Peuple le dropdown des cases quand on sélectionne une question."""
    db = _db(project_path)
    if not db:
        return gr.update(choices=[], value=None)
    student, page, copy = _parse_page_selection(page_selection)
    if student is None:
        return gr.update(choices=[], value=None)
    question_id = _parse_question_choice(question_choice)
    if question_id is None:
        return gr.update(choices=[], value=None)
    try:
        boxes = db.get_page_boxes(student, page, copy)
        a_choices = _build_answer_choices(boxes, question_id)
        first = a_choices[0] if a_choices else None
        return gr.update(choices=a_choices, value=first)
    except (sqlite3.OperationalError, KeyError) as e:
        logger.exception("select_question: erreur")
        return gr.update(choices=[], value=None)


def toggle_box_manual(project_path, page_selection, question_choice,
                      answer_choice, action):
    """Coche ou décoche manuellement une case sélectionnée.

    Args:
        project_path: Chemin du projet courant.
        page_selection: Label de la page sélectionnée.
        question_choice: Label du dropdown question (ex: "Code [1]" ou "Q5").
        answer_choice: Label du dropdown case (ex: "3 - Coché (auto)").
        action: "cocher" ou "decocher".

    Returns:
        Tuple (image, info, dataframe, question_dd_update, answer_dd_update).
    """
    db = _db(project_path)
    if not db:
        return None, "Aucun projet ouvert.", None, gr.update(), gr.update()
    student, page, copy = _parse_page_selection(page_selection)
    if student is None:
        return None, "Aucune page sélectionnée.", None, gr.update(), gr.update()
    question = _parse_question_choice(question_choice)
    answer = _parse_answer_choice(answer_choice)
    if question is None or answer is None:
        return None, "Sélectionnez une question et une case.", None, gr.update(), gr.update()

    manual_value = 1 if action == "cocher" else 0

    try:
        boxes = db.get_page_boxes(student, page, copy)
        target = next(
            (b for b in boxes if b["question"] == question and b["answer"] == answer),
            None,
        )
        if not target:
            return None, f"Case Q{question}-{answer} introuvable.", None, gr.update(), gr.update()

        db.set_zone_manual(target["zoneid"], manual_value)

        # Recharger
        scan_path = db.get_scan_path(student, page, copy)
        boxes = db.get_page_boxes(student, page, copy)
        img = render_annotated_scan(scan_path, boxes)
        df = _boxes_to_dataframe(boxes)
        q_choices = _build_question_choices(boxes)
        a_choices = _build_answer_choices(boxes, question)
        state_str = "coché" if manual_value == 1 else "non-coché"
        info = f"Question {question}, réponse {answer} : → {state_str} (manuel)"
        new_a_label = next((c for c in a_choices if c.startswith(f"{answer} - ")), None)
        return (img, info, df,
                gr.update(choices=q_choices, value=question_choice),
                gr.update(choices=a_choices, value=new_a_label))
    except (sqlite3.OperationalError, OSError) as e:
        logger.exception("toggle_box_manual: erreur")
        return None, f"Erreur : {e}", None, gr.update(), gr.update()


# ============================================================
# Onglet 6 — Association
# ============================================================

def upload_student_list(project_path, file):
    proj = _project(project_path)
    if not proj:
        return "Aucun projet ouvert."
    if file is None:
        return "Aucun fichier sélectionné."
    proj.save_student_list(file)
    return "Liste étudiants importée."


def associate_students(project_path, list_key, notes_id):
    proj = _project(project_path)
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

    db = _db(project_path)
    stats = ""
    if db:
        assoc = db.get_association_stats()
        stats = json.dumps(assoc, indent=2)
    return log, stats


# ============================================================
# Onglet 7 — Notation
# ============================================================

def detect_correction_copy(project_path, correction_state):
    """Détecte le numéro de copie du corrigé à partir du nom de fichier mémorisé."""
    db = _db(project_path)
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


def calculate_grades(project_path, notemax, grain, arrondi, seuil,
                     postcorrect, postcorrect_copy):
    proj = _project(project_path)
    if not proj:
        return "Aucun projet ouvert.", None, None
    nmax = _validate_number(notemax, 20, 0.1, 1000)
    g = _validate_number(grain, 0.5, 0.01, 100)
    s = _validate_number(seuil, 0.5, 0.01, 0.99)
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

    db = _db(project_path)
    results_df = None
    questions_df = None
    if db:
        results_df = db.get_scoring_results()
        questions_df = db.get_question_stats()
    return log, results_df, questions_df


# ============================================================
# Onglet 8 — Export
# ============================================================

def export_results(project_path, fmt):
    proj = _project(project_path)
    if not proj:
        return "Aucun projet ouvert.", None

    if fmt == "XLSX":
        return _export_xlsx(proj, project_path)

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


def _export_xlsx(proj, project_path):
    """Exporte les résultats au format XLSX depuis les bases SQLite."""
    db = _db(project_path)
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
    except (IOError, OSError) as e:
        logger.error("Erreur export XLSX : %s", e)
        return f"Erreur lors de l'export XLSX : {e}", None


# ============================================================
# Interface Gradio
# ============================================================

def build_ui():
    with gr.Blocks(title="AMC - Auto Multiple Choice") as app:
        gr.Markdown("# Auto-Multiple-Choice — Interface Web")

        project_state = gr.State(None)
        correction_state = gr.State("")

        mode_toggle = gr.Radio(
            choices=["Standard", "Avancé"],
            value="Standard",
            label="Mode",
            interactive=True,
        )

        # ============================================================
        # Mode Standard (workflow guidé)
        # ============================================================
        std = build_standard_ui(PROJECTS_BASE)

        # ============================================================
        # Mode Avancé (8 onglets)
        # ============================================================
        with gr.Column(visible=False) as advanced_container:

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

                msg_project = gr.Textbox(
                    label="Message", interactive=False
                )
                status_json = gr.Code(
                    label="Statut du projet", language="json"
                )

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
                    inputs=[project_state, source_upload],
                    outputs=[msg_src, source_editor, images_group],
                )
                btn_upload_img.click(
                    upload_images,
                    inputs=[project_state, images_upload],
                    outputs=[msg_src, images_group],
                )
                btn_save_src.click(
                    save_source_editor,
                    inputs=[project_state, source_editor],
                    outputs=[msg_src],
                )
                btn_compile.click(
                    compile_document,
                    inputs=[project_state, n_copies],
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
                    btn_import_xy = gr.Button(
                        "Importer et recalculer le layout"
                    )
                xy_log = gr.Textbox(
                    label="Log meptex", lines=5, interactive=False
                )
                btn_import_xy.click(
                    import_calage,
                    inputs=[project_state, xy_upload],
                    outputs=[xy_log],
                )

            # --- Onglet 3 : Scans ---
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
                    inputs=[project_state, scan_upload, correction_upload,
                            correction_state],
                    outputs=[import_log, scan_list, correction_state],
                )
                btn_clear_scans.click(
                    clear_scans,
                    inputs=[project_state],
                    outputs=[import_log, scan_list],
                )

            # --- Onglet 4 : Analyse ---
            with gr.Tab("4. Analyse"):
                with gr.Row():
                    n_procs = gr.Number(
                        label="Processus parallèles", value=4, precision=0
                    )
                    threshold = gr.Number(
                        label="Seuil de détection", value=0.5
                    )
                photocopy = gr.Checkbox(
                    label="Copies photocopiées",
                    value=False,
                    info="Cochez si certaines feuilles ont été photocopiées "
                         "avant distribution",
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
                    inputs=[project_state, n_procs, threshold, photocopy],
                    outputs=[analyse_log, analyse_stats],
                )

            # --- Onglet 5 : Vérification ---
            with gr.Tab("5. Vérification"):
                with gr.Row(equal_height=True):
                    with gr.Column():
                        page_selector = gr.Dropdown(
                            label="Page scannée",
                            choices=[],
                            interactive=True,
                        )
                        with gr.Row():
                            btn_load_page = gr.Button("Charger la page")
                            btn_refresh_pages = gr.Button(
                                "Rafraîchir la liste"
                            )
                    with gr.Column():
                        code_search = gr.Textbox(
                            label="Rechercher par code",
                            placeholder="ex: 1234",
                        )
                        btn_search = gr.Button("Rechercher")
                with gr.Row(equal_height=True):
                    with gr.Column():
                        scan_image = gr.Image(
                            label="Scan annoté", interactive=False,
                        )
                    with gr.Column():
                        question_selector = gr.Dropdown(
                            label="Question",
                            choices=[],
                            interactive=True,
                        )
                        answer_selector = gr.Dropdown(
                            label="Case",
                            choices=[],
                            interactive=True,
                        )
                        with gr.Row():
                            btn_cocher = gr.Button("Cocher")
                            btn_decocher = gr.Button("Décocher")
                verif_info = gr.Textbox(
                    label="Information", interactive=False
                )
                boxes_table = gr.Dataframe(
                    label="Cases de la page",
                )

                verif_outputs = [scan_image, verif_info, boxes_table,
                                 question_selector, answer_selector]

                btn_refresh_pages.click(
                    load_verification_pages,
                    inputs=[project_state],
                    outputs=[page_selector],
                )
                btn_load_page.click(
                    load_page_image,
                    inputs=[project_state, page_selector],
                    outputs=verif_outputs,
                )
                question_selector.change(
                    select_question,
                    inputs=[project_state, page_selector,
                            question_selector],
                    outputs=[answer_selector],
                )
                search_outputs = [page_selector] + verif_outputs

                btn_search.click(
                    search_by_code,
                    inputs=[project_state, code_search],
                    outputs=search_outputs,
                )
                code_search.submit(
                    search_by_code,
                    inputs=[project_state, code_search],
                    outputs=search_outputs,
                )
                btn_cocher.click(
                    lambda pp, ps, qc, ac: toggle_box_manual(
                        pp, ps, qc, ac, "cocher"
                    ),
                    inputs=[project_state, page_selector,
                            question_selector, answer_selector],
                    outputs=verif_outputs,
                )
                btn_decocher.click(
                    lambda pp, ps, qc, ac: toggle_box_manual(
                        pp, ps, qc, ac, "decocher"
                    ),
                    inputs=[project_state, page_selector,
                            question_selector, answer_selector],
                    outputs=verif_outputs,
                )

            # --- Onglet 6 : Association ---
            with gr.Tab("6. Association"):
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
                    inputs=[project_state, student_upload],
                    outputs=[msg_students],
                )
                btn_associate.click(
                    associate_students,
                    inputs=[project_state, list_key, notes_id],
                    outputs=[assoc_log, assoc_stats],
                )

            # --- Onglet 7 : Notation ---
            with gr.Tab("7. Notation"):
                with gr.Row():
                    notemax = gr.Number(label="Note max", value=20)
                    grain = gr.Number(label="Grain", value=0.5)
                    arrondi = gr.Dropdown(
                        label="Arrondi",
                        choices=["n", "i", "s"],
                        value="n",
                    )
                    seuil = gr.Number(label="Seuil", value=0.5)
                gr.Markdown("### Postcorrect (photocopie)")
                postcorrect_check = gr.Checkbox(
                    label="Mode postcorrect",
                    value=False,
                    info="Activez si vous utilisez des copies "
                         "photocopiées avec un corrigé scanné. Le barème "
                         "sera déduit de la copie corrigée.",
                )
                with gr.Row():
                    btn_detect = gr.Button("Détecter le corrigé")
                    postcorrect_copy = gr.Number(
                        label="N° copie corrigé",
                        precision=0,
                        info="Numéro de copie du corrigé (détecté ou "
                             "saisi manuellement)",
                    )
                detect_msg = gr.Textbox(
                    label="Détection", interactive=False
                )
                btn_detect.click(
                    detect_correction_copy,
                    inputs=[project_state, correction_state],
                    outputs=[detect_msg, postcorrect_copy],
                )
                btn_grade = gr.Button(
                    "Calculer les notes", variant="primary"
                )
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
                    inputs=[project_state, notemax, grain, arrondi, seuil,
                            postcorrect_check, postcorrect_copy],
                    outputs=[grade_log, results_table, questions_table],
                )

            # --- Onglet 8 : Export ---
            with gr.Tab("8. Export"):
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
                    inputs=[project_state, export_fmt],
                    outputs=[export_log, export_file],
                )

        # ============================================================
        # Handlers Projet mode avancé
        # ============================================================

        project_data_outputs = [
            source_editor, images_group, pdf_viewer, pdf_output,
            scan_list, results_table, questions_table,
        ]

        btn_create.click(
            create_project,
            inputs=[project_state, new_name],
            outputs=[project_state, msg_project, status_json, project_list]
                    + project_data_outputs,
        )
        btn_open.click(
            open_project,
            inputs=[project_state, project_list],
            outputs=[project_state, msg_project, status_json]
                    + project_data_outputs,
        )
        btn_refresh.click(
            refresh_projects, outputs=[project_list]
        )
        btn_import_proj.click(
            import_project,
            inputs=[project_state, import_name, import_zip],
            outputs=[project_state, msg_project, status_json, project_list]
                    + project_data_outputs,
        )

        # ============================================================
        # Switch de mode
        # ============================================================

        def switch_mode(mode, pp):
            std_visible = mode == "Standard"
            adv_visible = mode == "Avancé"
            outputs = [
                gr.update(visible=std_visible),
                gr.update(visible=adv_visible),
            ]
            if std_visible and pp:
                outputs.append(update_progress_html(pp))
            else:
                outputs.append(gr.update())
            return outputs

        mode_toggle.change(
            switch_mode,
            inputs=[mode_toggle, project_state],
            outputs=[std["container"], advanced_container,
                     std["progress"]],
        )

        # ============================================================
        # Handlers mode standard
        # ============================================================

        # -- Navigation --
        std["btn_prev"].click(
            lambda step, pp: navigate_step(step, "prev", pp),
            inputs=[std["step_state"], project_state],
            outputs=[std["step_state"]] + std["steps"]
                    + [std["progress"], std["btn_prev"],
                       std["btn_next"]],
        )
        std["btn_next"].click(
            lambda step, pp: navigate_step(step, "next", pp),
            inputs=[std["step_state"], project_state],
            outputs=[std["step_state"]] + std["steps"]
                    + [std["progress"], std["btn_prev"],
                       std["btn_next"]],
        )

        # -- Étape 1 : Projet & Source --
        std_project_outputs = [
            project_state, std["msg_project"], std["source_editor"],
            std["images_group"], std["project_list"], std["progress"],
        ]

        def _std_create_then_progress(pp, name):
            result = std_create_project(pp, name)
            progress = update_progress_html(result[0])
            return result[:5] + (progress,)

        def _std_open_then_progress(pp, name):
            result = std_open_project(pp, name)
            progress = update_progress_html(result[0])
            return result[:5] + (progress,)

        std["btn_create"].click(
            _std_create_then_progress,
            inputs=[project_state, std["new_name"]],
            outputs=std_project_outputs,
        )
        std["btn_open"].click(
            _std_open_then_progress,
            inputs=[project_state, std["project_list"]],
            outputs=std_project_outputs,
        )
        std["btn_refresh"].click(
            refresh_projects, outputs=[std["project_list"]]
        )
        std["btn_upload_src"].click(
            upload_source,
            inputs=[project_state, std["source_upload"]],
            outputs=[std["msg_src"], std["source_editor"],
                     std["images_group"]],
        ).then(
            update_progress_html,
            inputs=[project_state],
            outputs=[std["progress"]],
        )
        std["btn_upload_img"].click(
            upload_images,
            inputs=[project_state, std["images_upload"]],
            outputs=[std["msg_src"], std["images_group"]],
        )

        # -- Étape 2 : Compilation --
        std["btn_compile"].click(
            compile_document,
            inputs=[project_state, std["n_copies"]],
            outputs=[std["compile_log"], std["pdf_output"],
                     std["pdf_viewer"]],
        ).then(
            update_progress_html,
            inputs=[project_state],
            outputs=[std["progress"]],
        )

        # -- Étape 3 : Scans --
        std["btn_import_scans"].click(
            import_scans,
            inputs=[project_state, std["scan_upload"],
                    std["correction_upload"], correction_state],
            outputs=[std["import_log"], std["scan_list"],
                     correction_state],
        ).then(
            update_progress_html,
            inputs=[project_state],
            outputs=[std["progress"]],
        )

        # -- Étape 4 : Analyse & Vérification --
        std["btn_analyse"].click(
            std_analyse_scans,
            inputs=[project_state],
            outputs=[std["analyse_log"], std["analyse_stats"]],
        ).then(
            update_progress_html,
            inputs=[project_state],
            outputs=[std["progress"]],
        )

        std_verif_outputs = [
            std["scan_image"], std["verif_info"], std["boxes_table"],
            std["question_selector"], std["answer_selector"],
        ]

        std["btn_refresh_pages"].click(
            load_verification_pages,
            inputs=[project_state],
            outputs=[std["page_selector"]],
        )
        std["btn_load_page"].click(
            load_page_image,
            inputs=[project_state, std["page_selector"]],
            outputs=std_verif_outputs,
        )
        std["question_selector"].change(
            select_question,
            inputs=[project_state, std["page_selector"],
                    std["question_selector"]],
            outputs=[std["answer_selector"]],
        )
        std_search_outputs = [std["page_selector"]] + std_verif_outputs
        std["btn_search"].click(
            search_by_code,
            inputs=[project_state, std["code_search"]],
            outputs=std_search_outputs,
        )
        std["code_search"].submit(
            search_by_code,
            inputs=[project_state, std["code_search"]],
            outputs=std_search_outputs,
        )
        std["btn_cocher"].click(
            lambda pp, ps, qc, ac: toggle_box_manual(
                pp, ps, qc, ac, "cocher"
            ),
            inputs=[project_state, std["page_selector"],
                    std["question_selector"], std["answer_selector"]],
            outputs=std_verif_outputs,
        )
        std["btn_decocher"].click(
            lambda pp, ps, qc, ac: toggle_box_manual(
                pp, ps, qc, ac, "decocher"
            ),
            inputs=[project_state, std["page_selector"],
                    std["question_selector"], std["answer_selector"]],
            outputs=std_verif_outputs,
        )

        # -- Étape 5 : Association & Notation --
        std["btn_upload_students"].click(
            upload_student_list,
            inputs=[project_state, std["student_upload"]],
            outputs=[std["msg_students"]],
        )
        std["btn_associate"].click(
            std_associate_students,
            inputs=[project_state],
            outputs=[std["assoc_log"], std["assoc_stats"]],
        ).then(
            update_progress_html,
            inputs=[project_state],
            outputs=[std["progress"]],
        )
        std["btn_detect"].click(
            detect_correction_copy,
            inputs=[project_state, correction_state],
            outputs=[std["detect_msg"], std["postcorrect_copy"]],
        )
        std["btn_grade"].click(
            std_calculate_grades,
            inputs=[project_state, std["notemax"],
                    std["postcorrect_check"], std["postcorrect_copy"]],
            outputs=[std["grade_log"], std["results_table"],
                     std["questions_table"]],
        ).then(
            update_progress_html,
            inputs=[project_state],
            outputs=[std["progress"]],
        )

        # -- Étape 6 : Export --
        std["btn_export"].click(
            export_results,
            inputs=[project_state, std["export_fmt"]],
            outputs=[std["export_log"], std["export_file"]],
        ).then(
            update_progress_html,
            inputs=[project_state],
            outputs=[std["progress"]],
        )

    return app


if __name__ == "__main__":
    app = build_ui()
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        allowed_paths=[PROJECTS_BASE],
    )
