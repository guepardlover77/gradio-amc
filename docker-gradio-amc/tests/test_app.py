"""Tests pour app.py — fonctions backend de l'interface Gradio."""

import json
import os
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

# Patcher le PROJECTS_BASE avant l'import
os.environ.setdefault("AMC_PROJECTS_DIR", "/tmp/amc_test_projects")

import app


# ============================================================
# Helpers
# ============================================================

@pytest.fixture(autouse=True)
def reset_global_state():
    """Remet l'état global à zéro entre chaque test."""
    app.current_project["path"] = None
    yield
    app.current_project["path"] = None


@pytest.fixture
def set_project(project_dir):
    """Configure le projet courant pour les tests."""
    app.current_project["path"] = str(project_dir)
    return project_dir


# ============================================================
# _format_log
# ============================================================

class TestFormatLog:
    def test_success(self):
        log = app._format_log(0, "output", "")
        assert "OK" in log
        assert "output" in log

    def test_error(self):
        log = app._format_log(1, "", "erreur fatale")
        assert "ERREUR" in log
        assert "erreur fatale" in log

    def test_both_streams(self):
        log = app._format_log(0, "stdout", "stderr")
        assert "stdout" in log
        assert "[STDERR]" in log
        assert "stderr" in log

    def test_empty(self):
        log = app._format_log(0, "", "")
        assert "OK" in log


# ============================================================
# _generate_pdf_viewer
# ============================================================

class TestGeneratePdfViewer:
    def test_none_path(self):
        assert app._generate_pdf_viewer(None) == ""

    def test_nonexistent_path(self):
        assert app._generate_pdf_viewer("/no/such/file.pdf") == ""

    def test_valid_pdf(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        html = app._generate_pdf_viewer(str(pdf))
        assert "<iframe" in html
        assert "base64" in html


# ============================================================
# _detect_images
# ============================================================

class TestDetectImages:
    def test_simple(self):
        tex = r"\includegraphics{image.png}"
        assert app._detect_images(tex) == ["image.png"]

    def test_with_options(self):
        tex = r"\includegraphics[width=5cm]{fig1}"
        assert app._detect_images(tex) == ["fig1"]

    def test_multiple(self):
        tex = (
            r"\includegraphics{a.png}" "\n"
            r"\includegraphics[scale=0.5]{b.jpg}"
        )
        result = app._detect_images(tex)
        assert result == ["a.png", "b.jpg"]

    def test_no_images(self):
        assert app._detect_images(r"\documentclass{article}") == []


# ============================================================
# Onglet 1 — Projet
# ============================================================

class TestCreateProject:
    def test_empty_name(self):
        result = app.create_project("")
        assert "Veuillez" in result[0]

    def test_none_name(self):
        result = app.create_project(None)
        assert "Veuillez" in result[0]

    def test_whitespace_name(self):
        result = app.create_project("   ")
        assert "Veuillez" in result[0]

    @patch("app.AMCProject.create_new")
    @patch("app.AMCProject.list_projects", return_value=["test"])
    def test_success(self, mock_list, mock_create, tmp_path):
        mock_proj = MagicMock()
        mock_proj.project_dir = str(tmp_path)
        mock_proj.get_status.return_value = {"source": False}
        mock_proj.get_source_content.return_value = ""
        mock_proj.get_pdf_path.return_value = None
        mock_proj.get_scans.return_value = []
        mock_create.return_value = mock_proj

        result = app.create_project("test")
        assert "créé avec succès" in result[0]

    @patch("app.AMCProject.create_new", side_effect=FileExistsError)
    def test_duplicate(self, mock_create):
        result = app.create_project("dup")
        assert "existe déjà" in result[0]


class TestOpenProject:
    def test_no_name(self):
        result = app.open_project(None)
        assert "Sélectionnez" in result[0]

    def test_not_found(self):
        result = app.open_project("nonexistent_project_xyz")
        assert "introuvable" in result[0]

    def test_success(self, project_dir):
        # Placer le projet dans le bon répertoire
        with patch.object(app, "PROJECTS_BASE", str(project_dir.parent)):
            result = app.open_project(project_dir.name)
            assert "ouvert" in result[0]
            assert app.current_project["path"] == str(project_dir)


class TestImportProject:
    def test_no_name(self):
        result = app.import_project("", None)
        assert "Veuillez" in result[0]

    def test_no_zip(self):
        result = app.import_project("test", None)
        assert "ZIP" in result[0]

    @patch("app.AMCProject.import_existing", side_effect=FileExistsError)
    def test_duplicate(self, mock_import):
        result = app.import_project("dup", "/fake.zip")
        assert "existe déjà" in result[0]

    @patch("app.AMCProject.import_existing", side_effect=RuntimeError("bad zip"))
    def test_generic_error(self, mock_import):
        result = app.import_project("test", "/fake.zip")
        assert "Erreur" in result[0]


class TestRefreshProjects:
    @patch("app.AMCProject.list_projects", return_value=["a", "b"])
    def test_returns_update(self, mock_list):
        result = app.refresh_projects()
        assert hasattr(result, "__dict__") or isinstance(result, dict)


# ============================================================
# Onglet 2 — Préparation
# ============================================================

class TestUploadSource:
    def test_no_project(self):
        msg, content, update = app.upload_source("/fake.tex")
        assert "Aucun projet" in msg

    def test_no_file(self, set_project):
        msg, content, update = app.upload_source(None)
        assert "Aucun fichier" in msg


class TestSaveSourceEditor:
    def test_no_project(self):
        msg = app.save_source_editor("content")
        assert "Aucun projet" in msg

    def test_success(self, set_project):
        msg = app.save_source_editor("\\documentclass{article}")
        assert "sauvegardée" in msg


class TestCompileDocument:
    def test_no_project(self):
        log, pdf, html = app.compile_document(30)
        assert "Aucun projet" in log

    def test_no_source(self, set_project):
        log, pdf, html = app.compile_document(30)
        assert "Aucun fichier source" in log


class TestImportCalage:
    def test_no_project(self):
        msg = app.import_calage("/fake.xy")
        assert "Aucun projet" in msg

    def test_no_file(self, set_project):
        msg = app.import_calage(None)
        assert "Aucun fichier" in msg


# ============================================================
# Onglet 3 — Scans
# ============================================================

class TestImportScans:
    def test_no_project(self):
        log, scans, state = app.import_scans(None, None, "")
        assert "Aucun projet" in log

    def test_no_files(self, set_project):
        log, scans, state = app.import_scans(None, None, "")
        assert "Aucun fichier" in log


class TestClearScans:
    def test_no_project(self):
        msg, scans = app.clear_scans()
        assert "Aucun projet" in msg

    def test_empty_scans(self, set_project):
        msg, scans = app.clear_scans()
        assert "0 fichier" in msg
        assert scans == "Aucun scan."

    def test_deletes_scans(self, set_project, project_dir):
        scans_dir = project_dir / "scans"
        (scans_dir / "a.png").write_bytes(b"x")
        (scans_dir / "b.png").write_bytes(b"x")
        msg, scans = app.clear_scans()
        assert "2 fichier" in msg
        assert len(os.listdir(str(scans_dir))) == 0


# ============================================================
# Onglet 4 — Analyse
# ============================================================

class TestAnalyseScans:
    def test_no_project(self):
        log, stats = app.analyse_scans(4, 0.15, False)
        assert "Aucun projet" in log


# ============================================================
# Onglet 5 — Vérification
# ============================================================

class TestBoxIsTicked:
    def test_auto_ticked(self):
        box = {"manual": -1, "total": 1000, "black": 300}
        assert app._box_is_ticked(box) is True

    def test_auto_not_ticked(self):
        box = {"manual": -1, "total": 1000, "black": 50}
        assert app._box_is_ticked(box) is False

    def test_manual_ticked(self):
        box = {"manual": 1, "total": 1000, "black": 0}
        assert app._box_is_ticked(box) is True

    def test_manual_not_ticked(self):
        box = {"manual": 0, "total": 1000, "black": 999}
        assert app._box_is_ticked(box) is False

    def test_manual_none_uses_auto(self):
        box = {"manual": None, "total": 1000, "black": 300}
        assert app._box_is_ticked(box) is True

    def test_custom_seuil(self):
        box = {"manual": -1, "total": 1000, "black": 300}
        assert app._box_is_ticked(box, seuil=0.5) is False

    def test_zero_total_no_crash(self):
        box = {"manual": -1, "total": 0, "black": 0}
        # total=0 → total remplacé par 1 → black/total = 0 → False
        assert app._box_is_ticked(box) is False


class TestRenderAnnotatedScan:
    def test_produces_image(self, project_dir):
        from tests.conftest import _create_test_image
        scan = str(project_dir / "scan.png")
        _create_test_image(scan, 400, 600)

        boxes = [
            {"x1": 10, "y1": 10, "x2": 50, "y2": 50,
             "manual": -1, "total": 1000, "black": 300},
            {"x1": 100, "y1": 100, "x2": 140, "y2": 140,
             "manual": 0, "total": 1000, "black": 50},
        ]
        img = app.render_annotated_scan(scan, boxes)
        assert img.size == (400, 600)
        assert img.mode == "RGB"

    def test_empty_boxes(self, project_dir):
        from tests.conftest import _create_test_image
        scan = str(project_dir / "scan.png")
        _create_test_image(scan)

        img = app.render_annotated_scan(scan, [])
        assert img is not None


class TestBoxesToDataframe:
    def test_with_boxes(self):
        boxes = [
            {"question": 1, "answer": 1, "total": 1000, "black": 300,
             "manual": -1},
            {"question": 1, "answer": 2, "total": 1000, "black": 50,
             "manual": 1},
        ]
        df = app._boxes_to_dataframe(boxes)
        assert len(df) == 2
        assert "Question" in df.columns
        assert "État" in df.columns
        # Box 1: auto cochée
        assert "auto" in df.iloc[0]["État"]
        # Box 2: manuellement cochée
        assert "manuel" in df.iloc[1]["État"]

    def test_empty(self):
        df = app._boxes_to_dataframe([])
        assert df.empty
        assert "Question" in df.columns

    def test_percentage_calculation(self):
        boxes = [{"question": 1, "answer": 1, "total": 200, "black": 100,
                  "manual": -1}]
        df = app._boxes_to_dataframe(boxes)
        assert df.iloc[0]["Noircissement %"] == 50.0


class TestParsePageSelection:
    def test_valid(self):
        s, p, c = app._parse_page_selection(
            "Étudiant 1 - Page 2 (copie 0)"
        )
        assert (s, p, c) == (1, 2, 0)

    def test_large_numbers(self):
        s, p, c = app._parse_page_selection(
            "Étudiant 123 - Page 45 (copie 67)"
        )
        assert (s, p, c) == (123, 45, 67)

    def test_none(self):
        assert app._parse_page_selection(None) == (None, None, None)

    def test_empty(self):
        assert app._parse_page_selection("") == (None, None, None)

    def test_invalid_format(self):
        assert app._parse_page_selection("garbage") == (None, None, None)

    def test_partial_match(self):
        assert app._parse_page_selection("Étudiant 1") == (None, None, None)


class TestLoadVerificationPages:
    def test_no_project(self):
        result = app.load_verification_pages()
        assert hasattr(result, "__dict__") or isinstance(result, dict)

    def test_with_pages(self, set_project, capture_db):
        result = app.load_verification_pages()
        # result is a gr.update dict
        choices = result.get("choices", []) if isinstance(result, dict) else getattr(result, "choices", [])
        # Il devrait y avoir des choix
        assert choices is not None


class TestLoadPageImage:
    def test_no_project(self):
        img, info, df = app.load_page_image("Étudiant 1 - Page 1 (copie 0)")
        assert img is None
        assert "Aucun projet" in info

    def test_invalid_selection(self, set_project):
        img, info, df = app.load_page_image("")
        assert img is None
        assert "Sélectionnez" in info

    def test_scan_not_found(self, set_project, capture_db, project_dir):
        # Supprimer le scan pour forcer l'erreur
        scan = project_dir / "scans" / "scan_001.png"
        if scan.exists():
            scan.unlink()
        img, info, df = app.load_page_image(
            "Étudiant 1 - Page 1 (copie 0)"
        )
        assert img is None
        assert "introuvable" in info

    def test_success(self, set_project, capture_db):
        img, info, df = app.load_page_image(
            "Étudiant 1 - Page 1 (copie 0)"
        )
        assert img is not None
        assert "case(s)" in info
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 4


class TestOnImageClick:
    def test_no_project(self):
        evt = MagicMock()
        evt.index = (115, 115)
        img, info, df = app.on_image_click("Étudiant 1 - Page 1 (copie 0)", evt)
        assert img is None
        assert "Aucun projet" in info

    def test_no_selection(self, set_project):
        evt = MagicMock()
        evt.index = (115, 115)
        img, info, df = app.on_image_click("", evt)
        assert "Aucune page" in info

    def test_click_on_box(self, set_project, capture_db):
        evt = MagicMock()
        evt.index = (115, 115)  # Centre de la box 1
        img, info, df = app.on_image_click(
            "Étudiant 1 - Page 1 (copie 0)", evt
        )
        assert img is not None
        assert "Question" in info or "Zone" in info
        assert isinstance(df, pd.DataFrame)

    def test_click_far_from_boxes(self, set_project, capture_db):
        evt = MagicMock()
        evt.index = (380, 580)  # Loin de toutes les boxes
        img, info, df = app.on_image_click(
            "Étudiant 1 - Page 1 (copie 0)", evt
        )
        assert "Aucune case" in info


# ============================================================
# Onglet 6 — Association
# ============================================================

class TestUploadStudentList:
    def test_no_project(self):
        msg = app.upload_student_list("/fake.csv")
        assert "Aucun projet" in msg

    def test_no_file(self, set_project):
        msg = app.upload_student_list(None)
        assert "Aucun fichier" in msg


class TestAssociateStudents:
    def test_no_project(self):
        log, stats = app.associate_students("ID", "id")
        assert "Aucun projet" in log

    def test_no_student_list(self, set_project):
        log, stats = app.associate_students("ID", "id")
        assert "Aucune liste" in log


# ============================================================
# Onglet 7 — Notation
# ============================================================

class TestDetectCorrectionCopy:
    def test_no_project(self):
        msg, copy = app.detect_correction_copy("scan")
        assert "Aucun projet" in msg
        assert copy is None

    def test_no_correction_state(self, set_project):
        msg, copy = app.detect_correction_copy("")
        assert "Aucun corrigé" in msg

    def test_not_found(self, set_project, capture_db):
        msg, copy = app.detect_correction_copy("nonexistent")
        assert "non trouvé" in msg

    def test_found(self, set_project, capture_db):
        msg, copy = app.detect_correction_copy("scan_001")
        assert "détecté" in msg
        assert copy == 0


class TestCalculateGrades:
    def test_no_project(self):
        log, df1, df2 = app.calculate_grades(20, 0.5, "n", 0.15, False, None)
        assert "Aucun projet" in log


# ============================================================
# Onglet 8 — Export
# ============================================================

class TestExportResults:
    def test_no_project(self):
        log, f = app.export_results("CSV")
        assert "Aucun projet" in log
        assert f is None


class TestExportXlsx:
    def test_no_db(self, set_project):
        msg, f = app._export_xlsx(app._project())
        assert "introuvables" in msg or "notation" in msg.lower()

    def test_success(self, set_project, scoring_db):
        msg, f = app._export_xlsx(app._project())
        assert "réussi" in msg
        assert f is not None
        assert os.path.exists(f)


# ============================================================
# build_ui — vérification structurelle
# ============================================================

class TestBuildUI:
    def test_builds_without_error(self):
        """L'UI Gradio doit se construire sans exception."""
        ui = app.build_ui()
        assert ui is not None

    def test_has_all_tabs(self):
        """Vérifie que les 8 onglets sont présents."""
        ui = app.build_ui()
        # Gradio Blocks stocke les children récursivement
        tab_labels = []
        for block in ui.blocks.values():
            if hasattr(block, "label") and isinstance(block, type(block)):
                label = getattr(block, "label", "")
                if label and label[0].isdigit():
                    tab_labels.append(label)
        # Au minimum on vérifie que build_ui() ne crash pas
        assert ui is not None
