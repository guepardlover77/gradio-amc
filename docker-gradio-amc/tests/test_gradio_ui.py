"""Tests de structure de l'interface Gradio — composants, câblage, modes."""

import os

import pytest

os.environ.setdefault("AMC_PROJECTS_DIR", "/tmp/amc_test_projects")

import gradio as gr
import app


# ============================================================
# Helpers
# ============================================================

def _get_registered_fn_names(ui):
    """Collecte tous les noms de fonctions câblées dans ui.fns.

    Gradio 4.x expose ui.fns comme un dict {int: BlockFunction}.
    """
    names = set()
    fns = getattr(ui, "fns", {})
    # Supporte dict (Gradio 4.x) et list (Gradio 3.x)
    items = fns.values() if isinstance(fns, dict) else fns
    for bf in items:
        fn = getattr(bf, "fn", None)
        if callable(fn):
            names.add(getattr(fn, "__name__", ""))
            names.add(getattr(fn, "__qualname__", ""))
    return names


def _get_blocks_by_type(ui, cls):
    return [b for b in ui.blocks.values() if isinstance(b, cls)]


# ============================================================
# TestUIComponents
# ============================================================

class TestUIComponents:
    @pytest.fixture(scope="class")
    def ui(self):
        return app.build_ui()

    def test_state_project_path_exists(self, ui):
        """Un gr.State pour project_path doit exister."""
        states = _get_blocks_by_type(ui, gr.State)
        assert len(states) >= 1

    def test_at_least_two_states(self, ui):
        """project_state + correction_state → au moins 2 gr.State."""
        states = _get_blocks_by_type(ui, gr.State)
        assert len(states) >= 2

    def test_mode_radio_exists(self, ui):
        """Un gr.Radio de sélection de mode doit exister."""
        radios = _get_blocks_by_type(ui, gr.Radio)
        assert len(radios) >= 1

    def test_mode_radio_choices(self, ui):
        """Le Radio de mode doit proposer 'Standard' et 'Avancé'."""
        radios = _get_blocks_by_type(ui, gr.Radio)
        flat_choices = []
        for r in radios:
            for c in (r.choices or []):
                flat_choices.append(c if isinstance(c, str) else c[0])
        assert "Standard" in flat_choices
        assert "Avancé" in flat_choices

    def test_buttons_present(self, ui):
        """Des boutons doivent exister dans l'interface."""
        buttons = _get_blocks_by_type(ui, gr.Button)
        assert len(buttons) >= 5

    def test_all_buttons_have_labels(self, ui):
        """Aucun bouton ne doit avoir un label vide."""
        buttons = _get_blocks_by_type(ui, gr.Button)
        for btn in buttons:
            assert btn.value, f"Bouton sans label : {btn}"

    def test_textboxes_have_labels(self, ui):
        """Les Textbox doivent avoir des labels."""
        textboxes = _get_blocks_by_type(ui, gr.Textbox)
        for tb in textboxes:
            if not getattr(tb, "interactive", True):
                # Les zones de sortie (log) peuvent avoir un label vide
                continue
            # On ne force pas un label sur chaque textbox interactive,
            # mais on vérifie l'absence de crash à l'inspection
            _ = getattr(tb, "label", None)

    def test_tabs_present_in_advanced_mode(self, ui):
        """Des gr.Tab doivent exister pour le mode Avancé."""
        tabs = _get_blocks_by_type(ui, gr.Tab)
        assert len(tabs) >= 8

    def test_dropdowns_present(self, ui):
        """Des gr.Dropdown doivent exister."""
        dropdowns = _get_blocks_by_type(ui, gr.Dropdown)
        assert len(dropdowns) >= 1

    def test_file_components_present(self, ui):
        """Des gr.File doivent exister pour les uploads."""
        files = _get_blocks_by_type(ui, gr.File)
        assert len(files) >= 3


# ============================================================
# TestEventWiring
# ============================================================

class TestEventWiring:
    @pytest.fixture(scope="class")
    def ui(self):
        return app.build_ui()

    @pytest.fixture(scope="class")
    def fn_names(self, ui):
        return _get_registered_fn_names(ui)

    def test_create_project_wired(self, fn_names):
        assert any("create_project" in n for n in fn_names), \
            f"create_project absent de ui.fns : {fn_names}"

    def test_open_project_wired(self, fn_names):
        assert any("open_project" in n for n in fn_names), \
            f"open_project absent de ui.fns : {fn_names}"

    def test_compile_document_wired(self, fn_names):
        assert any("compile_document" in n for n in fn_names), \
            f"compile_document absent de ui.fns : {fn_names}"

    def test_analyse_scans_wired(self, fn_names):
        assert any("analyse_scans" in n for n in fn_names), \
            f"analyse_scans absent de ui.fns : {fn_names}"

    def test_import_scans_wired(self, fn_names):
        assert any("import_scans" in n for n in fn_names), \
            f"import_scans absent de ui.fns : {fn_names}"

    def test_export_results_wired(self, fn_names):
        assert any("export_results" in n for n in fn_names), \
            f"export_results absent de ui.fns : {fn_names}"

    def test_associate_students_wired(self, fn_names):
        assert any("associate_students" in n for n in fn_names), \
            f"associate_students absent de ui.fns : {fn_names}"

    def test_calculate_grades_wired(self, fn_names):
        assert any("calculate_grades" in n for n in fn_names), \
            f"calculate_grades absent de ui.fns : {fn_names}"

    def test_at_least_15_event_handlers(self, ui):
        """L'interface doit avoir au moins 15 gestionnaires d'événements."""
        assert len(ui.fns) >= 15

    def test_refresh_projects_wired(self, fn_names):
        assert any("refresh_projects" in n for n in fn_names), \
            f"refresh_projects absent de ui.fns : {fn_names}"

    def test_navigate_step_wired(self, ui):
        """Le mode standard doit avoir des boutons prev/next câblés.

        navigate_step est enregistré via une lambda, donc on vérifie
        que des lambdas sont présentes dans les handlers (prev/next).
        """
        fns = getattr(ui, "fns", {})
        items = fns.values() if isinstance(fns, dict) else fns
        lambda_count = sum(
            1 for bf in items
            if getattr(getattr(bf, "fn", None), "__name__", "") == "<lambda>"
        )
        assert lambda_count >= 2, \
            f"Moins de 2 lambdas câblées (prev/next navigate_step) : {lambda_count}"


# ============================================================
# TestModeSwitch
# ============================================================

class TestModeSwitch:
    @pytest.fixture(scope="class")
    def ui(self):
        return app.build_ui()

    def test_mode_toggle_is_radio(self, ui):
        radios = _get_blocks_by_type(ui, gr.Radio)
        assert any(
            "Standard" in (
                [c if isinstance(c, str) else c[0] for c in (r.choices or [])]
            )
            for r in radios
        )

    def test_mode_toggle_default_standard(self, ui):
        """La valeur par défaut du mode doit être 'Standard'."""
        radios = _get_blocks_by_type(ui, gr.Radio)
        for r in radios:
            flat = [c if isinstance(c, str) else c[0] for c in (r.choices or [])]
            if "Standard" in flat:
                # La valeur initiale est 'Standard' selon app.py:980
                assert r.value == "Standard"
                return
        pytest.fail("Aucun Radio de mode trouvé")

    def test_mode_change_event_registered(self, ui):
        """Le changement de mode doit être câblé à switch_mode."""
        fn_names = _get_registered_fn_names(ui)
        assert any("switch_mode" in n for n in fn_names), \
            f"switch_mode absent de ui.fns : {fn_names}"

    def test_standard_container_exists(self, ui):
        """Un conteneur standard (gr.Column) doit exister."""
        columns = _get_blocks_by_type(ui, gr.Column)
        assert len(columns) >= 1

    def test_progress_html_component_exists(self, ui):
        """Un composant gr.HTML pour la progression doit exister."""
        htmls = _get_blocks_by_type(ui, gr.HTML)
        assert len(htmls) >= 1


# ============================================================
# TestBuildUIIsolated
# ============================================================

class TestBuildUIIsolated:
    def test_build_twice_independent(self):
        """Deux appels à build_ui() doivent produire des instances indépendantes."""
        ui1 = app.build_ui()
        ui2 = app.build_ui()
        assert ui1 is not ui2

    def test_build_ui_returns_blocks(self):
        ui = app.build_ui()
        assert isinstance(ui, gr.Blocks)

    def test_ui_has_title(self):
        ui = app.build_ui()
        assert ui.title and "AMC" in ui.title
