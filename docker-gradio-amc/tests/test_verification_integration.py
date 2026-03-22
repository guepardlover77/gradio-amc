"""Tests d'intégration pour le workflow complet de vérification OMR.

Simule le parcours utilisateur : charger une page, voir les cases,
cliquer pour toggler, vérifier la persistance en DB.
"""

import sqlite3

import pandas as pd
import pytest

import app
from amc_database import AMCDatabase


@pytest.fixture
def project_path(project_dir, capture_db):
    """Retourne le chemin du projet configuré (str)."""
    return str(project_dir)


class TestFullVerificationWorkflow:
    """Simule le parcours utilisateur complet."""

    def test_step1_load_pages(self, project_path):
        """1. Charger la liste des pages."""
        result = app.load_verification_pages(project_path)
        # Devrait contenir au moins une page
        choices = (
            result.get("choices", [])
            if isinstance(result, dict)
            else getattr(result, "choices", [])
        )
        assert len(choices) >= 1
        assert "Étudiant 1" in choices[0]

    def test_step2_load_page_image(self, project_path):
        """2. Charger l'image annotée d'une page."""
        from PIL import Image
        img, info, df, qdd, add = app.load_page_image(
            project_path, "Étudiant 1 - Page 1 (copie 0)"
        )
        assert isinstance(img, Image.Image)
        assert "4 case(s)" in info
        assert len(df) == 4
        # question dropdown
        q_choices = qdd.get("choices", []) if isinstance(qdd, dict) else getattr(qdd, "choices", [])
        assert len(q_choices) == 2
        # answer dropdown for first question
        a_choices = add.get("choices", []) if isinstance(add, dict) else getattr(add, "choices", [])
        assert len(a_choices) == 2

    def test_step3_verify_initial_states(self, project_path):
        """3. Vérifier les états initiaux des cases."""
        _, _, df, _, _ = app.load_page_image(
            project_path, "Étudiant 1 - Page 1 (copie 0)"
        )
        # Q1A: auto cochée (black=800/1000 > 0.5)
        q1a = df[
            (df["Question"] == 1) & (df["Réponse"] == 1)
        ].iloc[0]
        assert "Coché" in q1a["État"]
        assert "auto" in q1a["État"]

        # Q1B: auto non-cochée (black=200/1000 < 0.5)
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

    def test_step4_toggle_decocher(self, project_path):
        """4. Décocher manuellement une case cochée."""
        img, info, df, qdd, add = app.toggle_box_manual(
            project_path, "Étudiant 1 - Page 1 (copie 0)", "Q1",
            "1 - Coché (auto)", "decocher"
        )

        from PIL import Image
        assert isinstance(img, Image.Image)
        assert "Question 1" in info
        assert "non-coché" in info

        q1a = df[
            (df["Question"] == 1) & (df["Réponse"] == 1)
        ].iloc[0]
        assert "Non-coché" in q1a["État"]
        assert "manuel" in q1a["État"]

    def test_step5_persistence(self, project_path, project_dir):
        """5. Vérifier que le changement est persisté en DB."""
        app.toggle_box_manual(
            project_path, "Étudiant 1 - Page 1 (copie 0)", "Q1",
            "1 - Coché (auto)", "decocher"
        )

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

    def test_step6_reload_reflects_changes(self, project_path):
        """6. Recharger la page reflète les modifications."""
        app.toggle_box_manual(
            project_path, "Étudiant 1 - Page 1 (copie 0)", "Q1",
            "1 - Coché (auto)", "decocher"
        )

        _, info, df, _, _ = app.load_page_image(
            project_path, "Étudiant 1 - Page 1 (copie 0)"
        )
        q1a = df[
            (df["Question"] == 1) & (df["Réponse"] == 1)
        ].iloc[0]
        assert "Non-coché" in q1a["État"]
        assert "manuel" in q1a["État"]

    def test_toggle_cocher_then_decocher(self, project_path):
        """Cocher puis décocher une case."""
        sel = "Étudiant 1 - Page 1 (copie 0)"

        # Cocher Q1B (initialement non-coché)
        _, info1, _, _, _ = app.toggle_box_manual(
            project_path, sel, "Q1", "2 - Non-coché (auto)", "cocher"
        )
        assert "coché" in info1

        # Décocher Q1B
        _, info2, _, _, _ = app.toggle_box_manual(
            project_path, sel, "Q1", "2 - Coché (manuel)", "decocher"
        )
        assert "non-coché" in info2


class TestVerificationEdgeCases:
    def test_page_with_no_boxes(self, project_path):
        """Page 2 n'a pas de cases (boxes sont sur page 1)."""
        img, info, df, qdd, add = app.load_page_image(
            project_path, "Étudiant 1 - Page 2 (copie 0)"
        )
        assert img is None
        assert "Aucune case" in info

    def test_noircissement_percentage(self, project_path):
        """Vérifier que les % de noircissement sont corrects."""
        _, _, df, _, _ = app.load_page_image(
            project_path, "Étudiant 1 - Page 1 (copie 0)"
        )
        q1a = df[
            (df["Question"] == 1) & (df["Réponse"] == 1)
        ].iloc[0]
        assert q1a["Noircissement %"] == 80.0  # 800/1000 * 100

        q1b = df[
            (df["Question"] == 1) & (df["Réponse"] == 2)
        ].iloc[0]
        assert q1b["Noircissement %"] == 20.0  # 200/1000 * 100


class TestRenderingColors:
    """Vérifie que les couleurs des rectangles sont correctes."""

    def test_ticked_box_is_green(self, project_path, project_dir):
        """Case cochée → pixels verts dans la zone."""
        from amc_database import AMCDatabase
        db = AMCDatabase(str(project_dir / "data"))
        scan_path = db.get_scan_path(1, 1, 0)
        boxes = db.get_page_boxes(1, 1, 0)
        img = app.render_annotated_scan(scan_path, boxes)
        # Q1A est cochée, centrée sur (115, 115)
        pixel = img.getpixel((115, 115))
        r, g, b = pixel
        assert g > r  # plus de vert que de rouge

    def test_unticked_box_is_red(self, project_path, project_dir):
        """Case non-cochée → pixels rouges dans la zone."""
        from amc_database import AMCDatabase
        db = AMCDatabase(str(project_dir / "data"))
        scan_path = db.get_scan_path(1, 1, 0)
        boxes = db.get_page_boxes(1, 1, 0)
        img = app.render_annotated_scan(scan_path, boxes)
        # Q1B est non-cochée, centrée sur (215, 115)
        pixel = img.getpixel((215, 115))
        r, g, b = pixel
        assert r > g  # plus de rouge que de vert
