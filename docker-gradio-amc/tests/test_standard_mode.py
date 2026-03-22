"""Tests pour standard_mode.py — Mode Standard (workflow guidé)."""

import os
from unittest.mock import patch, MagicMock

import pytest

os.environ.setdefault("AMC_PROJECTS_DIR", "/tmp/amc_test_projects")

import standard_mode as sm


# ============================================================
# Constantes et valeurs par défaut
# ============================================================

class TestStdDefaults:
    def test_num_steps(self):
        assert sm.NUM_STEPS == 6

    def test_step_labels_count(self):
        assert len(sm.STEP_LABELS) == sm.NUM_STEPS

    def test_step_labels_ordered(self):
        for i, label in enumerate(sm.STEP_LABELS, start=1):
            assert label.startswith(f"{i}.")

    def test_n_procs_valid(self):
        assert 1 <= sm.STD_N_PROCS <= 32

    def test_threshold_valid(self):
        assert 0.01 <= sm.STD_THRESHOLD <= 0.99

    def test_grain_valid(self):
        assert 0.01 <= sm.STD_GRAIN <= 100

    def test_seuil_valid(self):
        assert 0.01 <= sm.STD_SEUIL <= 0.99

    def test_arrondi_valid(self):
        assert sm.STD_ARRONDI in ("n", "i", "s")


# ============================================================
# Barre de progression
# ============================================================

class TestRenderProgress:
    def test_all_false(self):
        html = sm._render_progress([False] * 6)
        assert html.count("&#9675;") == 6
        assert "&#10004;" not in html

    def test_all_true(self):
        html = sm._render_progress([True] * 6)
        assert html.count("&#10004;") == 6
        assert "&#9675;" not in html

    def test_mixed(self):
        html = sm._render_progress([True, True, False, False, False, False])
        assert html.count("&#10004;") == 2
        assert html.count("&#9675;") == 4

    def test_contains_labels(self):
        html = sm._render_progress([False] * 6)
        for label in sm.STEP_LABELS:
            assert label in html

    def test_returns_string(self):
        html = sm._render_progress([False] * 6)
        assert isinstance(html, str)
        assert html.startswith("<div")


class TestComputeProgress:
    def test_none_project(self):
        result = sm.compute_progress(None)
        assert result == [False] * 6

    def test_empty_string_project(self):
        result = sm.compute_progress("")
        assert result == [False] * 6

    def test_nonexistent_project(self):
        result = sm.compute_progress("/nonexistent/path")
        assert result == [False] * 6

    def test_full_project(self, project_dir, all_dbs):
        # Créer un fichier source
        (project_dir / "source.tex").write_text("\\documentclass{article}")
        # Créer un PDF dans _build
        (project_dir / "_build" / "DOC-sujet.pdf").write_bytes(b"%PDF")
        # Créer des scans
        (project_dir / "scans" / "scan.png").write_bytes(b"PNG")
        # Créer un export
        (project_dir / "exports" / "results.csv").write_text("a,b")

        result = sm.compute_progress(str(project_dir))
        assert result[0] is True   # source
        assert result[1] is True   # compiled (PDF + layout db)
        assert result[2] is True   # scans
        assert result[5] is True   # exported

    def test_source_only(self, project_dir):
        (project_dir / "source.tex").write_text("\\documentclass{article}")
        result = sm.compute_progress(str(project_dir))
        assert result[0] is True
        assert result[1] is False
        assert result[2] is False


class TestUpdateProgressHtml:
    def test_returns_html(self):
        html = sm.update_progress_html(None)
        assert isinstance(html, str)
        assert "<div" in html


# ============================================================
# Navigation
# ============================================================

class TestNavigateStep:
    def test_next_from_zero(self):
        result = sm.navigate_step(0, "next", None)
        new_step = result[0]
        assert new_step == 1
        # step 1 visible, others not
        for i in range(6):
            vis = result[1 + i]
            expected = (i == 1)
            assert vis["visible"] == expected, f"step {i}"

    def test_prev_from_zero(self):
        result = sm.navigate_step(0, "prev", None)
        assert result[0] == 0  # clamped

    def test_next_from_last(self):
        result = sm.navigate_step(5, "next", None)
        assert result[0] == 5  # clamped

    def test_prev_from_last(self):
        result = sm.navigate_step(5, "prev", None)
        assert result[0] == 4

    def test_returns_correct_count(self):
        result = sm.navigate_step(3, "next", None)
        # new_step + 6 visibilities + progress_html + prev_update + next_update
        assert len(result) == 10

    def test_prev_button_disabled_at_start(self):
        result = sm.navigate_step(1, "prev", None)
        assert result[0] == 0
        prev_update = result[8]
        assert prev_update["interactive"] is False

    def test_next_button_disabled_at_end(self):
        result = sm.navigate_step(4, "next", None)
        assert result[0] == 5
        next_update = result[9]
        assert next_update["interactive"] is False

    def test_both_buttons_enabled_in_middle(self):
        result = sm.navigate_step(2, "next", None)
        assert result[0] == 3
        prev_update = result[8]
        next_update = result[9]
        assert prev_update["interactive"] is True
        assert next_update["interactive"] is True

    def test_progress_html_included(self):
        result = sm.navigate_step(0, "next", None)
        progress_html = result[7]
        assert isinstance(progress_html, str)
        assert "<div" in progress_html


# ============================================================
# Wrappers mode standard
# ============================================================

class TestStdAnalyseScans:
    @patch("app.analyse_scans", return_value=("log", "stats"))
    def test_calls_with_defaults(self, mock_analyse):
        result = sm.std_analyse_scans("/some/path")
        mock_analyse.assert_called_once_with(
            "/some/path", sm.STD_N_PROCS, sm.STD_THRESHOLD, False
        )
        assert result == ("log", "stats")


class TestStdCalculateGrades:
    @patch("app.calculate_grades", return_value=("log", None, None))
    def test_calls_with_defaults(self, mock_grades):
        result = sm.std_calculate_grades("/path", 20, False, None)
        mock_grades.assert_called_once_with(
            "/path", 20, sm.STD_GRAIN, sm.STD_ARRONDI, sm.STD_SEUIL,
            False, None,
        )
        assert result == ("log", None, None)


class TestStdAssociateStudents:
    @patch("app.associate_students", return_value=("log", "stats"))
    def test_calls_with_defaults(self, mock_assoc):
        result = sm.std_associate_students("/path")
        mock_assoc.assert_called_once_with(
            "/path", sm.STD_LIST_KEY, sm.STD_NOTES_ID
        )
        assert result == ("log", "stats")


class TestStdCreateProject:
    @patch("app.create_project")
    def test_remaps_outputs(self, mock_create):
        import gradio as gr
        mock_create.return_value = (
            "/new/path",           # 0: project_path
            "Projet créé",         # 1: msg
            '{"source": false}',   # 2: status_json
            gr.update(choices=["p"]),  # 3: project_list
            "tex content",         # 4: source_content
            gr.update(visible=False),  # 5: images_group
            "<html>",              # 6: pdf_viewer_html
            None,                  # 7: pdf_path
            "Aucun scan.",         # 8: scan_list
            None,                  # 9: results_df
            None,                  # 10: questions_df
        )
        result = sm.std_create_project(None, "test")
        assert result[0] == "/new/path"
        assert result[1] == "Projet créé"
        assert result[2] == "tex content"
        assert len(result) == 6


class TestStdOpenProject:
    @patch("app.open_project")
    def test_remaps_outputs(self, mock_open):
        import gradio as gr
        mock_open.return_value = (
            "/proj/path",          # 0: project_path
            "Projet ouvert",       # 1: msg
            '{"source": true}',    # 2: status_json
            "tex content",         # 3: source_content
            gr.update(visible=False),  # 4: images_group
            "<iframe>",            # 5: pdf_viewer_html
            "/proj/_build/DOC-sujet.pdf",  # 6: pdf_path
            "scan1.png",           # 7: scan_list
            None,                  # 8: results_df
            None,                  # 9: questions_df
        )
        result = sm.std_open_project(None, "test")
        assert result[0] == "/proj/path"
        assert result[1] == "Projet ouvert"
        assert result[2] == "tex content"
        assert result[5] == "scan1.png"
        assert len(result) == 6


# ============================================================
# Construction de l'UI mode standard
# ============================================================

class TestBuildStandardUI:
    @pytest.fixture(scope="class")
    def std_dict(self):
        """Construit l'UI standard dans un contexte Blocks."""
        import gradio as gr
        with gr.Blocks():
            result = sm.build_standard_ui("/tmp/amc_test_projects")
        return result

    def test_returns_dict(self, std_dict):
        assert isinstance(std_dict, dict)

    def test_has_container_key(self, std_dict):
        assert "container" in std_dict

    def test_has_step_state(self, std_dict):
        assert "step_state" in std_dict

    def test_has_progress_component(self, std_dict):
        assert "progress" in std_dict

    def test_has_steps_list(self, std_dict):
        assert "steps" in std_dict
        assert isinstance(std_dict["steps"], list)
        assert len(std_dict["steps"]) == sm.NUM_STEPS

    def test_has_navigation_buttons(self, std_dict):
        assert "btn_prev" in std_dict
        assert "btn_next" in std_dict

    def test_has_project_buttons(self, std_dict):
        assert "btn_create" in std_dict
        assert "btn_open" in std_dict

    def test_has_source_components(self, std_dict):
        assert "source_editor" in std_dict
        assert "btn_upload_src" in std_dict

    def test_has_scan_components(self, std_dict):
        assert "btn_import_scans" in std_dict

    def test_has_analyse_button(self, std_dict):
        assert "btn_analyse" in std_dict

    def test_has_grade_button(self, std_dict):
        assert "btn_grade" in std_dict


# ============================================================
# navigate_step — couverture complète de toutes les étapes
# ============================================================

class TestNavigateStepFullCoverage:
    @pytest.mark.parametrize("start,direction,expected", [
        (0, "next", 1),
        (1, "next", 2),
        (2, "next", 3),
        (3, "next", 4),
        (4, "next", 5),
        (5, "next", 5),   # clamped
        (5, "prev", 4),
        (4, "prev", 3),
        (3, "prev", 2),
        (2, "prev", 1),
        (1, "prev", 0),
        (0, "prev", 0),   # clamped
    ])
    def test_step_transition(self, start, direction, expected):
        result = sm.navigate_step(start, direction, None)
        assert result[0] == expected

    @pytest.mark.parametrize("step", range(6))
    def test_only_current_step_visible(self, step):
        """Après navigation, seul l'onglet cible doit être visible."""
        # Aller vers step depuis step-1 (ou step+1 si step==0)
        if step > 0:
            result = sm.navigate_step(step - 1, "next", None)
        else:
            result = sm.navigate_step(1, "prev", None)
        new_step = result[0]
        for i in range(6):
            vis = result[1 + i]
            assert vis["visible"] == (i == new_step), \
                f"step={step}, i={i}: attendu visible={i == new_step}, got {vis}"

    def test_prev_disabled_at_step_0(self):
        result = sm.navigate_step(1, "prev", None)
        assert result[0] == 0
        prev_update = result[8]
        assert prev_update["interactive"] is False

    def test_next_disabled_at_step_5(self):
        result = sm.navigate_step(4, "next", None)
        assert result[0] == 5
        next_update = result[9]
        assert next_update["interactive"] is False

    @pytest.mark.parametrize("step", range(1, 5))
    def test_both_buttons_enabled_in_middle(self, step):
        result = sm.navigate_step(step, "next", None)
        if result[0] < 5:
            prev_update = result[8]
            next_update = result[9]
            assert prev_update["interactive"] is True
            assert next_update["interactive"] is True
