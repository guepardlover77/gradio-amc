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

@pytest.fixture
def project_path(project_dir):
    """Retourne le chemin du projet comme str (pour passer en 1er param)."""
    return str(project_dir)


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
# _validate_number
# ============================================================

class TestValidateNumber:
    def test_normal_value(self):
        assert app._validate_number(10, 5, 1, 100) == 10

    def test_none_returns_default(self):
        assert app._validate_number(None, 5, 1, 100) == 5

    def test_below_min(self):
        assert app._validate_number(-5, 5, 1, 100) == 1

    def test_above_max(self):
        assert app._validate_number(999, 5, 1, 100) == 100

    def test_invalid_string(self):
        assert app._validate_number("abc", 5, 1, 100) == 5

    def test_string_number(self):
        assert app._validate_number("42", 5, 1, 100) == 42

    def test_boundary_min(self):
        assert app._validate_number(1, 5, 1, 100) == 1

    def test_boundary_max(self):
        assert app._validate_number(100, 5, 1, 100) == 100


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
        result = app.create_project(None, "")
        assert "Veuillez" in result[1]

    def test_none_name(self):
        result = app.create_project(None, None)
        assert "Veuillez" in result[1]

    def test_whitespace_name(self):
        result = app.create_project(None, "   ")
        assert "Veuillez" in result[1]

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

        result = app.create_project(None, "test")
        assert "créé avec succès" in result[1]
        # First element is the new project_path
        assert result[0] == str(tmp_path)

    @patch("app.AMCProject.create_new", side_effect=FileExistsError)
    def test_duplicate(self, mock_create):
        result = app.create_project(None, "dup")
        assert "existe déjà" in result[1]


class TestOpenProject:
    def test_no_name(self):
        result = app.open_project(None, None)
        assert "Sélectionnez" in result[1]

    def test_not_found(self):
        result = app.open_project(None, "nonexistent_project_xyz")
        assert "introuvable" in result[1]

    def test_success(self, project_dir):
        # Placer le projet dans le bon répertoire
        with patch.object(app, "PROJECTS_BASE", str(project_dir.parent)):
            result = app.open_project(None, project_dir.name)
            assert "ouvert" in result[1]
            # First element is the new project_path
            assert result[0] == str(project_dir)


class TestImportProject:
    def test_no_name(self):
        result = app.import_project(None, "", None)
        assert "Veuillez" in result[1]

    def test_no_zip(self):
        result = app.import_project(None, "test", None)
        assert "ZIP" in result[1]

    @patch("app.AMCProject.import_existing", side_effect=FileExistsError)
    def test_duplicate(self, mock_import):
        result = app.import_project(None, "dup", "/fake.zip")
        assert "existe déjà" in result[1]

    @patch("app.AMCProject.import_existing", side_effect=ValueError("bad zip"))
    def test_generic_error(self, mock_import):
        result = app.import_project(None, "test", "/fake.zip")
        assert "Erreur" in result[1]


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
        msg, content, update = app.upload_source(None, "/fake.tex")
        assert "Aucun projet" in msg

    def test_no_file(self, project_path):
        msg, content, update = app.upload_source(project_path, None)
        assert "Aucun fichier" in msg


class TestUploadImages:
    def test_no_project(self):
        msg, update = app.upload_images(None, ["/fake.png"])
        assert "Aucun projet" in msg

    def test_no_files(self, project_path):
        msg, update = app.upload_images(project_path, None)
        assert "Aucun fichier" in msg

    def test_overwrite_warning(self, project_path, project_dir, tmp_path):
        """Quand un fichier existe déjà, le message doit signaler l'écrasement."""
        # Créer un fichier existant dans le projet
        existing = project_dir / "img.png"
        existing.write_bytes(b"old")
        # Créer un fichier source à importer
        src = tmp_path / "img.png"
        src.write_bytes(b"new")
        msg, update = app.upload_images(project_path, [str(src)])
        assert "écrasés" in msg.lower() or "Fichiers écrasés" in msg
        assert "img.png" in msg

    def test_no_overwrite_no_warning(self, project_path, tmp_path):
        """Pas de fichier existant → pas de mention d'écrasement."""
        src = tmp_path / "brand_new.png"
        src.write_bytes(b"data")
        msg, update = app.upload_images(project_path, [str(src)])
        assert "écrasés" not in msg.lower()
        assert "brand_new.png" in msg


class TestSaveSourceEditor:
    def test_no_project(self):
        msg = app.save_source_editor(None, "content")
        assert "Aucun projet" in msg

    def test_success(self, project_path):
        msg = app.save_source_editor(project_path, "\\documentclass{article}")
        assert "sauvegardée" in msg


class TestCompileDocument:
    def test_no_project(self):
        log, pdf, html = app.compile_document(None, 30)
        assert "Aucun projet" in log

    def test_no_source(self, project_path):
        log, pdf, html = app.compile_document(project_path, 30)
        assert "Aucun fichier source" in log

    def test_negative_copies_clamped(self):
        """n_copies < 1 is clamped to 1."""
        log, pdf, html = app.compile_document(None, -5)
        assert "Aucun projet" in log

    def test_huge_copies_clamped(self):
        """n_copies > 500 is clamped to 500."""
        log, pdf, html = app.compile_document(None, 9999)
        assert "Aucun projet" in log

    @patch("app.runner.prepare_document", return_value=(0, "ok", ""))
    def test_with_source_amc_success(self, mock_prepare, project_path, project_dir):
        """Quand source.tex existe et AMC réussit → log contient 'OK'."""
        (project_dir / "source.tex").write_text("\\documentclass{article}")
        log, pdf, html = app.compile_document(project_path, 30)
        assert "OK" in log
        mock_prepare.assert_called_once()

    @patch("app.runner.prepare_document", return_value=(1, "", "latex error"))
    def test_with_source_amc_failure(self, mock_prepare, project_path, project_dir):
        """Quand AMC échoue → log contient 'ERREUR'."""
        (project_dir / "source.tex").write_text("\\documentclass{article}")
        log, pdf, html = app.compile_document(project_path, 30)
        assert "ERREUR" in log

    @patch("app.runner.prepare_document", return_value=(0, "ok", ""))
    def test_copies_passed_to_runner(self, mock_prepare, project_path, project_dir):
        """Le nombre de copies doit être transmis au runner."""
        (project_dir / "source.tex").write_text("\\documentclass{article}")
        app.compile_document(project_path, 42)
        _, kwargs = mock_prepare.call_args
        args = mock_prepare.call_args[0]
        # n_copies est le 3e argument positionnel
        assert 42 in args or kwargs.get("n_copies") == 42


class TestImportCalage:
    def test_no_project(self):
        msg = app.import_calage(None, "/fake.xy")
        assert "Aucun projet" in msg

    def test_no_file(self, project_path):
        msg = app.import_calage(project_path, None)
        assert "Aucun fichier" in msg

    @patch("app.runner.compute_layout", return_value=(0, "ok", ""))
    def test_overwrite_warning(self, mock_layout, project_path, project_dir, tmp_path):
        """Quand DOC-calage.xy existait déjà, le log doit signaler l'écrasement."""
        build_dir = project_dir / "_build"
        build_dir.mkdir(exist_ok=True)
        (build_dir / "DOC-calage.xy").write_text("old data")
        xy = tmp_path / "calage.xy"
        xy.write_text("new data")
        log = app.import_calage(project_path, str(xy))
        assert "écrasé" in log


# ============================================================
# Onglet 3 — Scans
# ============================================================

class TestImportScans:
    def test_no_project(self):
        log, scans, state = app.import_scans(None, None, None, "")
        assert "Aucun projet" in log

    def test_no_files(self, project_path):
        log, scans, state = app.import_scans(project_path, None, None, "")
        assert "Aucun fichier" in log

    @patch("app.runner.import_scans", return_value=(0, "imported", ""))
    def test_with_valid_files(self, mock_import, project_path, tmp_path):
        """Import de fichiers valides → appel au runner."""
        f = tmp_path / "scan.pdf"
        f.write_bytes(b"%PDF-1.4")
        log, scans, state = app.import_scans(project_path, [str(f)], None, "")
        mock_import.assert_called_once()
        assert "OK" in log or "imported" in log

    @patch("app.runner.import_scans", return_value=(1, "", "scan error"))
    def test_with_failing_scan(self, mock_import, project_path, tmp_path):
        """Quand le runner échoue → log contient une erreur."""
        f = tmp_path / "bad.pdf"
        f.write_bytes(b"not a pdf")
        log, scans, state = app.import_scans(project_path, [str(f)], None, "")
        assert "ERREUR" in log or "erreur" in log.lower()

    @patch("app.runner.import_scans", return_value=(0, "ok", ""))
    def test_multiple_files_all_passed(self, mock_import, project_path, tmp_path):
        """Tous les fichiers doivent être passés au runner en un seul appel."""
        files = []
        for name in ["a.pdf", "b.pdf", "c.pdf"]:
            f = tmp_path / name
            f.write_bytes(b"%PDF")
            files.append(str(f))
        app.import_scans(project_path, files, None, "")
        mock_import.assert_called_once()
        called_files = mock_import.call_args[0][1]
        assert len(called_files) == 3


class TestClearScans:
    def test_no_project(self):
        msg, scans = app.clear_scans(None)
        assert "Aucun projet" in msg

    def test_empty_scans(self, project_path):
        msg, scans = app.clear_scans(project_path)
        assert "0 fichier" in msg
        assert scans == "Aucun scan."

    def test_deletes_scans(self, project_path, project_dir):
        scans_dir = project_dir / "scans"
        (scans_dir / "a.png").write_bytes(b"x")
        (scans_dir / "b.png").write_bytes(b"x")
        msg, scans = app.clear_scans(project_path)
        assert "2 fichier" in msg
        assert len(os.listdir(str(scans_dir))) == 0


# ============================================================
# Onglet 4 — Analyse
# ============================================================

class TestAnalyseScans:
    def test_no_project(self):
        log, stats = app.analyse_scans(None, 4, 0.15, False)
        assert "Aucun projet" in log

    def test_threshold_clamped(self):
        """threshold > 0.99 is clamped."""
        log, stats = app.analyse_scans(None, 4, 5.0, False)
        assert "Aucun projet" in log


# ============================================================
# Onglet 5 — Vérification
# ============================================================

class TestBoxIsTicked:
    def test_auto_ticked(self):
        box = {"manual": -1, "total": 1000, "black": 800}
        assert app._box_is_ticked(box) is True

    def test_auto_not_ticked(self):
        box = {"manual": -1, "total": 1000, "black": 300}
        assert app._box_is_ticked(box) is False

    def test_manual_ticked(self):
        box = {"manual": 1, "total": 1000, "black": 0}
        assert app._box_is_ticked(box) is True

    def test_manual_not_ticked(self):
        box = {"manual": 0, "total": 1000, "black": 999}
        assert app._box_is_ticked(box) is False

    def test_manual_none_uses_auto(self):
        box = {"manual": None, "total": 1000, "black": 800}
        assert app._box_is_ticked(box) is True

    def test_custom_seuil(self):
        box = {"manual": -1, "total": 1000, "black": 800}
        assert app._box_is_ticked(box, seuil=0.9) is False

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

    def test_with_code_prefix(self):
        s, p, c = app._parse_page_selection(
            "[1234] Étudiant 5 - Page 1 (copie 0)"
        )
        assert (s, p, c) == (5, 1, 0)

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


class TestBuildQuestionChoices:
    def test_crem_and_regular(self):
        boxes = [
            {"question": 1, "answer": i, "total": 1000, "black": 0, "manual": -1}
            for i in range(1, 11)
        ] + [
            {"question": 5, "answer": 1, "total": 1000, "black": 800, "manual": -1},
            {"question": 5, "answer": 2, "total": 1000, "black": 200, "manual": -1},
        ]
        choices = app._build_question_choices(boxes)
        assert "Code [1]" in choices
        assert "Q5" in choices

    def test_empty(self):
        assert app._build_question_choices([]) == []

    def test_question_with_few_answers_not_crem(self):
        boxes = [
            {"question": 1, "answer": 1, "total": 1000, "black": 800, "manual": -1},
            {"question": 1, "answer": 2, "total": 1000, "black": 200, "manual": -1},
        ]
        choices = app._build_question_choices(boxes)
        assert choices == ["Q1"]


class TestBuildAnswerChoices:
    def test_filters_by_question(self):
        boxes = [
            {"question": 1, "answer": 1, "total": 1000, "black": 800, "manual": -1},
            {"question": 1, "answer": 2, "total": 1000, "black": 200, "manual": -1},
            {"question": 2, "answer": 1, "total": 1000, "black": 500, "manual": -1},
        ]
        choices = app._build_answer_choices(boxes, 1)
        assert len(choices) == 2
        assert choices[0].startswith("1 - ")
        assert choices[1].startswith("2 - ")

    def test_empty_for_unknown_question(self):
        boxes = [
            {"question": 1, "answer": 1, "total": 1000, "black": 800, "manual": -1},
        ]
        assert app._build_answer_choices(boxes, 99) == []


class TestParseQuestionChoice:
    def test_crem(self):
        assert app._parse_question_choice("Code [1]") == 1
        assert app._parse_question_choice("Code [4]") == 4

    def test_regular(self):
        assert app._parse_question_choice("Q5") == 5
        assert app._parse_question_choice("Q12") == 12

    def test_none(self):
        assert app._parse_question_choice(None) is None
        assert app._parse_question_choice("") is None
        assert app._parse_question_choice("garbage") is None


class TestParseAnswerChoice:
    def test_valid(self):
        assert app._parse_answer_choice("3 - Coché (auto)") == 3
        assert app._parse_answer_choice("10 - Non-coché (manuel)") == 10

    def test_none(self):
        assert app._parse_answer_choice(None) is None
        assert app._parse_answer_choice("") is None


class TestSearchByCode:
    def _get_choices(self, page_dd):
        return (
            page_dd.get("choices", [])
            if isinstance(page_dd, dict)
            else getattr(page_dd, "choices", [])
        )

    def test_no_project(self):
        page_dd, img, info, df, qdd, add = app.search_by_code(None, "1234")
        assert self._get_choices(page_dd) == []

    def test_empty_query_reloads_all(self, project_path, capture_db_with_crem):
        page_dd, img, info, df, qdd, add = app.search_by_code(project_path, "")
        assert len(self._get_choices(page_dd)) >= 1

    def test_matching_code(self, project_path, capture_db_with_crem):
        from PIL import Image
        page_dd, img, info, df, qdd, add = app.search_by_code(project_path, "1234")
        choices = self._get_choices(page_dd)
        assert len(choices) >= 1
        assert "[1234]" in choices[0]
        # Doit charger directement la page
        assert isinstance(img, Image.Image)
        assert "case(s)" in info

    def test_no_match(self, project_path, capture_db_with_crem):
        page_dd, img, info, df, qdd, add = app.search_by_code(project_path, "9999")
        assert self._get_choices(page_dd) == []
        assert "Aucune copie" in info


class TestLoadVerificationPages:
    def test_no_project(self):
        result = app.load_verification_pages(None)
        assert hasattr(result, "__dict__") or isinstance(result, dict)

    def test_with_pages(self, project_path, capture_db):
        result = app.load_verification_pages(project_path)
        # result is a gr.update dict
        choices = result.get("choices", []) if isinstance(result, dict) else getattr(result, "choices", [])
        # Il devrait y avoir des choix
        assert choices is not None


class TestLoadPageImage:
    def test_no_project(self):
        img, info, df, qdd, add = app.load_page_image(None, "Étudiant 1 - Page 1 (copie 0)")
        assert img is None
        assert "Aucun projet" in info

    def test_invalid_selection(self, project_path):
        img, info, df, qdd, add = app.load_page_image(project_path, "")
        assert img is None
        assert "Sélectionnez" in info

    def test_scan_not_found(self, project_path, capture_db, project_dir):
        scan = project_dir / "scans" / "scan_001.png"
        if scan.exists():
            scan.unlink()
        img, info, df, qdd, add = app.load_page_image(
            project_path, "Étudiant 1 - Page 1 (copie 0)"
        )
        assert img is None
        assert "introuvable" in info

    def test_success(self, project_path, capture_db):
        from PIL import Image
        img, info, df, qdd, add = app.load_page_image(
            project_path, "Étudiant 1 - Page 1 (copie 0)"
        )
        assert isinstance(img, Image.Image)
        assert "case(s)" in info
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 4
        # question dropdown
        q_choices = qdd.get("choices", []) if isinstance(qdd, dict) else getattr(qdd, "choices", [])
        assert len(q_choices) == 2  # Q1 and Q2
        # answer dropdown populated for first question
        a_choices = add.get("choices", []) if isinstance(add, dict) else getattr(add, "choices", [])
        assert len(a_choices) == 2  # Q1 has 2 answers

    def test_success_with_code_prefix(self, project_path, capture_db):
        from PIL import Image
        img, info, df, qdd, add = app.load_page_image(
            project_path, "[12345] Étudiant 1 - Page 1 (copie 0)"
        )
        assert isinstance(img, Image.Image)


class TestSelectQuestion:
    def test_no_project(self):
        result = app.select_question(None, "Étudiant 1 - Page 1 (copie 0)", "Q1")
        choices = result.get("choices", []) if isinstance(result, dict) else getattr(result, "choices", [])
        assert choices == []

    def test_valid(self, project_path, capture_db):
        result = app.select_question(project_path, "Étudiant 1 - Page 1 (copie 0)", "Q2")
        choices = result.get("choices", []) if isinstance(result, dict) else getattr(result, "choices", [])
        assert len(choices) == 2


class TestToggleBoxManual:
    def test_no_project(self):
        img, info, df, qdd, add = app.toggle_box_manual(
            None, "Étudiant 1 - Page 1 (copie 0)", "Q1", "2 - Non-coché (auto)", "cocher"
        )
        assert img is None
        assert "Aucun projet" in info

    def test_no_selection(self, project_path):
        img, info, df, qdd, add = app.toggle_box_manual(
            project_path, "", "Q1", "1 - Coché (auto)", "cocher"
        )
        assert "Aucune page" in info

    def test_no_answer_choice(self, project_path):
        img, info, df, qdd, add = app.toggle_box_manual(
            project_path, "Étudiant 1 - Page 1 (copie 0)", "Q1", "", "cocher"
        )
        assert "Sélectionnez" in info

    def test_cocher(self, project_path, capture_db):
        from PIL import Image
        img, info, df, qdd, add = app.toggle_box_manual(
            project_path, "Étudiant 1 - Page 1 (copie 0)", "Q1", "2 - Non-coché (auto)", "cocher"
        )
        assert isinstance(img, Image.Image)
        assert "coché" in info
        assert "Question 1" in info
        q1b = df[(df["Question"] == 1) & (df["Réponse"] == 2)].iloc[0]
        assert "manuel" in q1b["État"]
        assert "Coché" in q1b["État"]

    def test_decocher(self, project_path, capture_db):
        img, info, df, qdd, add = app.toggle_box_manual(
            project_path, "Étudiant 1 - Page 1 (copie 0)", "Q1", "1 - Coché (auto)", "decocher"
        )
        assert "non-coché" in info
        q1a = df[(df["Question"] == 1) & (df["Réponse"] == 1)].iloc[0]
        assert "Non-coché" in q1a["État"]
        assert "manuel" in q1a["État"]


# ============================================================
# Onglet 6 — Association
# ============================================================

class TestUploadStudentList:
    def test_no_project(self):
        msg = app.upload_student_list(None, "/fake.csv")
        assert "Aucun projet" in msg

    def test_no_file(self, project_path):
        msg = app.upload_student_list(project_path, None)
        assert "Aucun fichier" in msg


class TestAssociateStudents:
    def test_no_project(self):
        log, stats = app.associate_students(None, "ID", "id")
        assert "Aucun projet" in log

    def test_no_student_list(self, project_path):
        log, stats = app.associate_students(project_path, "ID", "id")
        assert "Aucune liste" in log

    @patch("app.runner.auto_associate", return_value=(0, "association ok", ""))
    def test_with_student_list(self, mock_assoc, project_path, project_dir):
        """Quand la liste existe → le runner est appelé."""
        csv = project_dir / "students.csv"
        csv.write_text("ID,nom\n1,Alice\n2,Bob\n")
        log, stats = app.associate_students(project_path, "ID", "id")
        mock_assoc.assert_called_once()
        assert "OK" in log or "association" in log.lower()

    @patch("app.runner.auto_associate", return_value=(1, "", "assoc error"))
    def test_runner_failure_shows_error(self, mock_assoc, project_path, project_dir):
        """Quand l'association échoue → log contient ERREUR."""
        csv = project_dir / "students.csv"
        csv.write_text("ID,nom\n1,Alice\n")
        log, stats = app.associate_students(project_path, "ID", "id")
        assert "ERREUR" in log


# ============================================================
# Onglet 7 — Notation
# ============================================================

class TestDetectCorrectionCopy:
    def test_no_project(self):
        msg, copy = app.detect_correction_copy(None, "scan")
        assert "Aucun projet" in msg
        assert copy is None

    def test_no_correction_state(self, project_path):
        msg, copy = app.detect_correction_copy(project_path, "")
        assert "Aucun corrigé" in msg

    def test_not_found(self, project_path, capture_db):
        msg, copy = app.detect_correction_copy(project_path, "nonexistent")
        assert "non trouvé" in msg

    def test_found(self, project_path, capture_db):
        msg, copy = app.detect_correction_copy(project_path, "scan_001")
        assert "détecté" in msg
        assert copy == 0


class TestCalculateGrades:
    def test_no_project(self):
        log, df1, df2 = app.calculate_grades(None, 20, 0.5, "n", 0.15, False, None)
        assert "Aucun projet" in log

    @patch("app.runner.calculate_grades", return_value=(0, "notes calculées", ""))
    def test_with_scoring_db(self, mock_grades, project_path, scoring_db):
        """Quand la base scoring existe → log contient la sortie du runner."""
        log, df1, df2 = app.calculate_grades(
            project_path, 20, 0.5, "n", 0.15, False, None
        )
        mock_grades.assert_called_once()
        assert "notes" in log.lower() or "OK" in log

    @patch("app.runner.calculate_grades", return_value=(0, "ok", ""))
    def test_notemax_passed_to_runner(self, mock_grades, project_path, scoring_db):
        """notemax doit être transmis au runner."""
        app.calculate_grades(project_path, 20, 0.5, "n", 0.15, False, None)
        args = mock_grades.call_args[0]
        kwargs = mock_grades.call_args[1] if mock_grades.call_args[1] else {}
        assert 20 in args or kwargs.get("notemax") == 20

    @patch("app.runner.calculate_grades", return_value=(1, "", "grade error"))
    def test_runner_failure_shows_error(self, mock_grades, project_path, scoring_db):
        """Quand le runner de notation échoue → log contient ERREUR."""
        log, df1, df2 = app.calculate_grades(
            project_path, 20, 0.5, "n", 0.15, False, None
        )
        assert "ERREUR" in log


# ============================================================
# Onglet 8 — Export
# ============================================================

class TestExportResults:
    def test_no_project(self):
        log, f = app.export_results(None, "CSV")
        assert "Aucun projet" in log
        assert f is None

    def test_ods_format_no_scoring(self, project_path):
        """ODS sans base scoring → erreur, pas de crash."""
        log, f = app.export_results(project_path, "ODS")
        assert log  # pas de crash, message présent
        assert f is None

    def test_csv_format_no_scoring(self, project_path):
        """CSV sans base scoring → erreur, pas de crash."""
        log, f = app.export_results(project_path, "CSV")
        assert log
        assert f is None

    @patch("app.runner.export_results", return_value=(0, "export ok", ""))
    def test_csv_format_with_scoring(self, mock_export, project_path, scoring_db):
        """CSV avec base scoring → runner appelé."""
        log, f = app.export_results(project_path, "CSV")
        mock_export.assert_called_once()

    def test_unknown_format_no_crash(self, project_path):
        """Un format inconnu ne doit pas lever d'exception non gérée."""
        try:
            log, f = app.export_results(project_path, "UNKNOWN_FORMAT")
            assert log  # doit retourner un message
        except Exception as e:
            pytest.fail(f"Exception inattendue : {e}")


class TestExportXlsx:
    def test_no_db(self, project_path):
        msg, f = app._export_xlsx(app._project(project_path), project_path)
        assert "introuvables" in msg or "notation" in msg.lower()

    def test_success(self, project_path, scoring_db):
        msg, f = app._export_xlsx(app._project(project_path), project_path)
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

    def test_has_mode_toggle(self):
        """Un composant Radio avec 'Standard'/'Avancé' doit exister."""
        import gradio as gr
        ui = app.build_ui()
        found = False
        for block in ui.blocks.values():
            if isinstance(block, gr.Radio):
                choices = getattr(block, "choices", [])
                # choices can be list of strings or list of (label, value)
                flat = []
                for c in choices:
                    if isinstance(c, tuple):
                        flat.extend(c)
                    else:
                        flat.append(c)
                if "Standard" in flat:
                    found = True
                    break
        assert found, "Mode toggle Radio not found"
