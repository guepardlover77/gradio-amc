"""Tests d'intégration pour le workflow complet de vérification OMR.

Simule le parcours utilisateur : charger une page, voir les cases,
cliquer pour toggler, vérifier la persistance en DB.
"""

import sqlite3
from unittest.mock import MagicMock

import pandas as pd
import pytest

import app
from amc_database import AMCDatabase


@pytest.fixture(autouse=True)
def reset_state():
    app.current_project["path"] = None
    yield
    app.current_project["path"] = None


@pytest.fixture
def setup_project(project_dir, capture_db):
    app.current_project["path"] = str(project_dir)
    return project_dir


class TestFullVerificationWorkflow:
    """Simule le parcours utilisateur complet."""

    def test_step1_load_pages(self, setup_project):
        """1. Charger la liste des pages."""
        result = app.load_verification_pages()
        # Devrait contenir au moins une page
        choices = (
            result.get("choices", [])
            if isinstance(result, dict)
            else getattr(result, "choices", [])
        )
        assert len(choices) >= 1
        assert "Étudiant 1" in choices[0]

    def test_step2_load_page_image(self, setup_project):
        """2. Charger l'image annotée d'une page."""
        img, info, df = app.load_page_image(
            "Étudiant 1 - Page 1 (copie 0)"
        )
        assert img is not None
        assert "4 case(s)" in info
        assert len(df) == 4

    def test_step3_verify_initial_states(self, setup_project):
        """3. Vérifier les états initiaux des cases."""
        _, _, df = app.load_page_image(
            "Étudiant 1 - Page 1 (copie 0)"
        )
        # Q1A: auto cochée (black=300/1000 > 0.15)
        q1a = df[
            (df["Question"] == 1) & (df["Réponse"] == 1)
        ].iloc[0]
        assert "Coché" in q1a["État"]
        assert "auto" in q1a["État"]

        # Q1B: auto non-cochée (black=50/1000 < 0.15)
        q1b = df[
            (df["Question"] == 1) & (df["Réponse"] == 2)
        ].iloc[0]
        assert "Non-coché" in q1b["État"]

        # Q2A: manuellement cochée
        q2a = df[
            (df["Question"] == 2) & (df["Réponse"] == 1)
        ].iloc[0]
        assert "manuel" in q2a["État"]
        assert "Coché" in q2a["État"]

        # Q2B: manuellement non-cochée
        q2b = df[
            (df["Question"] == 2) & (df["Réponse"] == 2)
        ].iloc[0]
        assert "manuel" in q2b["État"]
        assert "Non-coché" in q2b["État"]

    def test_step4_click_toggle(self, setup_project):
        """4. Cliquer sur une case pour toggler son état."""
        evt = MagicMock()
        evt.index = (115, 115)  # Centre de Q1A

        img, info, df = app.on_image_click(
            "Étudiant 1 - Page 1 (copie 0)", evt
        )

        assert img is not None
        assert "Question 1" in info
        assert "non-coché" in info  # était coché → non-coché

        # Vérifier dans le DataFrame
        q1a = df[
            (df["Question"] == 1) & (df["Réponse"] == 1)
        ].iloc[0]
        assert "Non-coché" in q1a["État"]
        assert "manuel" in q1a["État"]

    def test_step5_persistence(self, setup_project, project_dir):
        """5. Vérifier que le changement est persisté en DB."""
        evt = MagicMock()
        evt.index = (115, 115)
        app.on_image_click("Étudiant 1 - Page 1 (copie 0)", evt)

        # Lire directement la DB
        db_path = project_dir / "data" / "capture.sqlite"
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute(
            "SELECT manual FROM capture_zone "
            "WHERE student=1 AND page=1 AND copy=0 AND id_a=1 AND id_b=1"
        )
        manual = cur.fetchone()[0]
        conn.close()
        assert manual == 0  # forcé non-coché

    def test_step6_reload_reflects_changes(self, setup_project):
        """6. Recharger la page reflète les modifications."""
        # Toggle Q1A
        evt = MagicMock()
        evt.index = (115, 115)
        app.on_image_click("Étudiant 1 - Page 1 (copie 0)", evt)

        # Recharger
        img, info, df = app.load_page_image(
            "Étudiant 1 - Page 1 (copie 0)"
        )
        q1a = df[
            (df["Question"] == 1) & (df["Réponse"] == 1)
        ].iloc[0]
        assert "Non-coché" in q1a["État"]
        assert "manuel" in q1a["État"]

    def test_toggle_twice_changes_back(self, setup_project):
        """Toggle deux fois une case revient à l'opposé du premier toggle."""
        sel = "Étudiant 1 - Page 1 (copie 0)"

        # Premier toggle: coché → non-coché
        evt = MagicMock()
        evt.index = (115, 115)
        _, info1, _ = app.on_image_click(sel, evt)
        assert "non-coché" in info1

        # Deuxième toggle: non-coché → coché
        _, info2, _ = app.on_image_click(sel, evt)
        assert "coché" in info2


class TestVerificationEdgeCases:
    def test_page_with_no_boxes(self, setup_project):
        """Page 2 n'a pas de cases (boxes sont sur page 1)."""
        img, info, df = app.load_page_image(
            "Étudiant 1 - Page 2 (copie 0)"
        )
        assert img is None
        assert "Aucune case" in info

    def test_click_between_boxes(self, setup_project):
        """Clic entre deux boxes, assez loin → aucune case trouvée."""
        evt = MagicMock()
        evt.index = (350, 350)  # Loin de toutes les boxes
        img, info, df = app.on_image_click(
            "Étudiant 1 - Page 1 (copie 0)", evt
        )
        assert "Aucune case" in info

    def test_noircissement_percentage(self, setup_project):
        """Vérifier que les % de noircissement sont corrects."""
        _, _, df = app.load_page_image(
            "Étudiant 1 - Page 1 (copie 0)"
        )
        q1a = df[
            (df["Question"] == 1) & (df["Réponse"] == 1)
        ].iloc[0]
        assert q1a["Noircissement %"] == 30.0  # 300/1000 * 100

        q1b = df[
            (df["Question"] == 1) & (df["Réponse"] == 2)
        ].iloc[0]
        assert q1b["Noircissement %"] == 5.0  # 50/1000 * 100


class TestRenderingColors:
    """Vérifie que les couleurs des rectangles sont correctes."""

    def test_ticked_box_is_green(self, setup_project, project_dir):
        """Case cochée → pixels verts dans la zone."""
        from PIL import Image
        img, _, _ = app.load_page_image(
            "Étudiant 1 - Page 1 (copie 0)"
        )
        # Q1A est cochée, centrée sur (115, 115)
        pixel = img.getpixel((115, 115))
        # Le vert devrait dominer (overlay vert semi-transparent sur blanc)
        r, g, b = pixel
        assert g > r  # plus de vert que de rouge

    def test_unticked_box_is_red(self, setup_project, project_dir):
        """Case non-cochée → pixels rouges dans la zone."""
        img, _, _ = app.load_page_image(
            "Étudiant 1 - Page 1 (copie 0)"
        )
        # Q1B est non-cochée, centrée sur (215, 115)
        pixel = img.getpixel((215, 115))
        r, g, b = pixel
        assert r > g  # plus de rouge que de vert
