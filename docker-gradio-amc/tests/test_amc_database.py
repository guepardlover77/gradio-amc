"""Tests pour amc_database.py — toutes les méthodes de requête SQLite."""

import sqlite3

import pandas as pd
import pytest

from amc_database import AMCDatabase


# ============================================================
# _connect
# ============================================================

class TestConnect:
    def test_connect_existing_db(self, capture_db, project_dir):
        db = AMCDatabase(str(project_dir / "data"))
        conn = db._connect("capture.sqlite")
        assert conn is not None
        conn.close()

    def test_connect_missing_db(self, project_dir):
        db = AMCDatabase(str(project_dir / "data"))
        conn = db._connect("nonexistent.sqlite")
        assert conn is None

    def test_connect_missing_data_dir(self, tmp_path):
        db = AMCDatabase(str(tmp_path / "no_such_dir"))
        conn = db._connect("capture.sqlite")
        assert conn is None


# ============================================================
# get_layout_info
# ============================================================

class TestGetLayoutInfo:
    def test_with_data(self, layout_db, project_dir):
        db = AMCDatabase(str(project_dir / "data"))
        info = db.get_layout_info()
        assert info["pages"] == 2
        assert info["students"] == 2
        assert info["questions"] == 2

    def test_no_db(self, project_dir):
        db = AMCDatabase(str(project_dir / "data"))
        info = db.get_layout_info()
        assert info == {"pages": 0, "students": 0, "questions": 0}

    def test_empty_tables(self, project_dir):
        db_path = project_dir / "data" / "layout.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE layout_page (student INTEGER, page INTEGER)")
        conn.execute("CREATE TABLE layout_box (question INTEGER)")
        conn.commit()
        conn.close()

        db = AMCDatabase(str(project_dir / "data"))
        info = db.get_layout_info()
        assert info["pages"] == 0
        assert info["students"] == 0
        assert info["questions"] == 0


# ============================================================
# get_capture_stats
# ============================================================

class TestGetCaptureStats:
    def test_with_data(self, capture_db, project_dir):
        db = AMCDatabase(str(project_dir / "data"))
        stats = db.get_capture_stats()
        assert stats["scans_analysed"] >= 1
        assert stats["pages_detected"] == 2

    def test_no_db(self, project_dir):
        db = AMCDatabase(str(project_dir / "data"))
        stats = db.get_capture_stats()
        assert stats == {"scans_analysed": 0, "pages_detected": 0}


# ============================================================
# get_association_stats
# ============================================================

class TestGetAssociationStats:
    def test_with_data(self, association_db, project_dir):
        db = AMCDatabase(str(project_dir / "data"))
        stats = db.get_association_stats()
        assert stats["associated"] == 1
        assert stats["unassociated"] == 1

    def test_no_db(self, project_dir):
        db = AMCDatabase(str(project_dir / "data"))
        stats = db.get_association_stats()
        assert stats == {"associated": 0, "unassociated": 0}


# ============================================================
# get_scoring_results
# ============================================================

class TestGetScoringResults:
    def test_with_data(self, scoring_db, project_dir):
        db = AMCDatabase(str(project_dir / "data"))
        df = db.get_scoring_results()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert "student" in df.columns
        assert "code" in df.columns
        assert df.loc[df["student"] == 1, "code"].iloc[0] == "12345"

    def test_no_db(self, project_dir):
        db = AMCDatabase(str(project_dir / "data"))
        df = db.get_scoring_results()
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_no_scoring_code_table(self, project_dir):
        """scoring_code peut ne pas exister — code doit être None."""
        db_path = project_dir / "data" / "scoring.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE scoring_mark "
            "(student INTEGER, copy INTEGER, total REAL, max REAL, mark REAL)"
        )
        conn.execute("INSERT INTO scoring_mark VALUES (1, 0, 10, 20, 10)")
        conn.commit()
        conn.close()

        db = AMCDatabase(str(project_dir / "data"))
        df = db.get_scoring_results()
        assert len(df) == 1
        assert df["code"].iloc[0] is None


# ============================================================
# get_question_stats
# ============================================================

class TestGetQuestionStats:
    def test_with_data(self, scoring_db, project_dir):
        db = AMCDatabase(str(project_dir / "data"))
        df = db.get_question_stats()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert "question" in df.columns
        assert "pct" in df.columns

    def test_no_db(self, project_dir):
        db = AMCDatabase(str(project_dir / "data"))
        df = db.get_question_stats()
        assert df.empty


# ============================================================
# find_correction_copy
# ============================================================

class TestFindCorrectionCopy:
    def test_found(self, capture_db, project_dir):
        db = AMCDatabase(str(project_dir / "data"))
        result = db.find_correction_copy("scan_001")
        assert result is not None
        assert result == (1, 0)

    def test_not_found(self, capture_db, project_dir):
        db = AMCDatabase(str(project_dir / "data"))
        result = db.find_correction_copy("nonexistent_scan")
        assert result is None

    def test_no_db(self, project_dir):
        db = AMCDatabase(str(project_dir / "data"))
        result = db.find_correction_copy("anything")
        assert result is None


# ============================================================
# get_captured_pages (nouveau — onglet Vérification)
# ============================================================

class TestGetCapturedPages:
    def test_with_data(self, capture_db, project_dir):
        db = AMCDatabase(str(project_dir / "data"))
        pages = db.get_captured_pages()
        assert len(pages) == 2
        assert pages[0]["student"] == 1
        assert pages[0]["page"] == 1
        assert "src" in pages[0]

    def test_order(self, capture_db, project_dir):
        db = AMCDatabase(str(project_dir / "data"))
        pages = db.get_captured_pages()
        assert pages[0]["page"] <= pages[1]["page"]

    def test_no_db(self, project_dir):
        db = AMCDatabase(str(project_dir / "data"))
        pages = db.get_captured_pages()
        assert pages == []

    def test_only_auto_pages(self, project_dir):
        """Les pages avec timestamp_auto=0 ne doivent pas apparaître."""
        db_path = project_dir / "data" / "capture.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE capture_page "
            "(student INTEGER, page INTEGER, copy INTEGER, "
            "src TEXT, timestamp_auto REAL)"
        )
        conn.execute(
            "INSERT INTO capture_page VALUES (1, 1, 0, 'scan.png', 0)"
        )
        conn.execute(
            "INSERT INTO capture_page VALUES (2, 1, 0, 'scan2.png', 500.0)"
        )
        conn.commit()
        conn.close()

        db = AMCDatabase(str(project_dir / "data"))
        pages = db.get_captured_pages()
        assert len(pages) == 1
        assert pages[0]["student"] == 2


# ============================================================
# get_page_boxes (nouveau — onglet Vérification)
# ============================================================

class TestGetPageBoxes:
    def test_with_data(self, capture_db, project_dir):
        db = AMCDatabase(str(project_dir / "data"))
        boxes = db.get_page_boxes(1, 1, 0)
        assert len(boxes) == 4
        keys = {"zoneid", "question", "answer", "total", "black",
                "manual", "x1", "y1", "x2", "y2"}
        assert keys == set(boxes[0].keys())

    def test_positions(self, capture_db, project_dir):
        db = AMCDatabase(str(project_dir / "data"))
        boxes = db.get_page_boxes(1, 1, 0)
        box1 = boxes[0]
        assert box1["x1"] == 100.0
        assert box1["y1"] == 100.0
        assert box1["x2"] == 130.0
        assert box1["y2"] == 130.0

    def test_empty_page(self, capture_db, project_dir):
        db = AMCDatabase(str(project_dir / "data"))
        boxes = db.get_page_boxes(99, 99, 99)
        assert boxes == []

    def test_no_db(self, project_dir):
        db = AMCDatabase(str(project_dir / "data"))
        boxes = db.get_page_boxes(1, 1, 0)
        assert boxes == []

    def test_order_by_question_answer(self, capture_db, project_dir):
        db = AMCDatabase(str(project_dir / "data"))
        boxes = db.get_page_boxes(1, 1, 0)
        qa_pairs = [(b["question"], b["answer"]) for b in boxes]
        assert qa_pairs == sorted(qa_pairs)

    def test_only_type_4(self, project_dir):
        """Ne retourne que les ZONE_BOX (type=4), pas les autres types."""
        db_path = project_dir / "data" / "capture.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.executescript("""
            CREATE TABLE capture_zone (
                zoneid INTEGER PRIMARY KEY AUTOINCREMENT,
                student INTEGER, page INTEGER, copy INTEGER,
                type INTEGER, id_a INTEGER, id_b INTEGER,
                total REAL, black REAL, manual INTEGER DEFAULT -1
            );
            CREATE TABLE capture_position (
                zoneid INTEGER, corner INTEGER, type INTEGER,
                x REAL, y REAL
            );
        """)
        # Type 4 (box) — doit apparaître
        conn.execute(
            "INSERT INTO capture_zone "
            "(student, page, copy, type, id_a, id_b, total, black, manual) "
            "VALUES (1, 1, 0, 4, 1, 1, 1000, 300, -1)"
        )
        z1 = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO capture_position VALUES (?, 1, 4, 10, 10)", (z1,)
        )
        conn.execute(
            "INSERT INTO capture_position VALUES (?, 3, 4, 30, 30)", (z1,)
        )
        # Type 1 (name) — ne doit PAS apparaître
        conn.execute(
            "INSERT INTO capture_zone "
            "(student, page, copy, type, id_a, id_b, total, black, manual) "
            "VALUES (1, 1, 0, 1, 0, 0, 100, 10, -1)"
        )
        z2 = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO capture_position VALUES (?, 1, 1, 50, 50)", (z2,)
        )
        conn.execute(
            "INSERT INTO capture_position VALUES (?, 3, 1, 80, 80)", (z2,)
        )
        conn.commit()
        conn.close()

        db = AMCDatabase(str(project_dir / "data"))
        boxes = db.get_page_boxes(1, 1, 0)
        assert len(boxes) == 1
        assert boxes[0]["question"] == 1


# ============================================================
# set_zone_manual
# ============================================================

class TestSetZoneManual:
    def test_set_to_checked(self, capture_db, project_dir):
        db = AMCDatabase(str(project_dir / "data"))
        boxes = db.get_page_boxes(1, 1, 0)
        zoneid = boxes[0]["zoneid"]

        db.set_zone_manual(zoneid, 1)

        boxes2 = db.get_page_boxes(1, 1, 0)
        updated = next(b for b in boxes2 if b["zoneid"] == zoneid)
        assert updated["manual"] == 1

    def test_set_to_unchecked(self, capture_db, project_dir):
        db = AMCDatabase(str(project_dir / "data"))
        boxes = db.get_page_boxes(1, 1, 0)
        zoneid = boxes[0]["zoneid"]

        db.set_zone_manual(zoneid, 0)

        boxes2 = db.get_page_boxes(1, 1, 0)
        updated = next(b for b in boxes2 if b["zoneid"] == zoneid)
        assert updated["manual"] == 0

    def test_reset_to_auto(self, capture_db, project_dir):
        db = AMCDatabase(str(project_dir / "data"))
        boxes = db.get_page_boxes(1, 1, 0)
        zoneid = boxes[0]["zoneid"]

        db.set_zone_manual(zoneid, 1)
        db.set_zone_manual(zoneid, -1)

        boxes2 = db.get_page_boxes(1, 1, 0)
        updated = next(b for b in boxes2 if b["zoneid"] == zoneid)
        assert updated["manual"] == -1

    def test_no_db(self, project_dir):
        """Ne doit pas lever d'exception si la base n'existe pas."""
        db = AMCDatabase(str(project_dir / "data"))
        db.set_zone_manual(999, 1)  # no-op silencieux


# ============================================================
# toggle_box_at
# ============================================================

class TestToggleBoxAt:
    def test_click_inside_box(self, capture_db, project_dir):
        """Clic à l'intérieur de la box 1 (Q1A, cochée auto) → toggle."""
        db = AMCDatabase(str(project_dir / "data"))
        zoneid = db.toggle_box_at(1, 1, 0, 115, 115)
        assert zoneid is not None

        # Vérifier que manual a été mis à 0 (était cochée → non-cochée)
        boxes = db.get_page_boxes(1, 1, 0)
        box = next(b for b in boxes if b["zoneid"] == zoneid)
        assert box["manual"] == 0

    def test_click_near_box(self, capture_db, project_dir):
        """Clic proche mais en dehors → doit quand même toggler."""
        db = AMCDatabase(str(project_dir / "data"))
        # Centre de box 1 = (115, 115), cliquer à (140, 115) = 25px
        zoneid = db.toggle_box_at(1, 1, 0, 140, 115, threshold=30)
        assert zoneid is not None

    def test_click_too_far(self, capture_db, project_dir):
        """Clic trop loin de toute case → None."""
        db = AMCDatabase(str(project_dir / "data"))
        zoneid = db.toggle_box_at(1, 1, 0, 500, 500, threshold=40)
        assert zoneid is None

    def test_toggle_manual_checked_to_unchecked(self, capture_db, project_dir):
        """Box 3 est manual=1 → toggle doit passer à 0."""
        db = AMCDatabase(str(project_dir / "data"))
        boxes = db.get_page_boxes(1, 1, 0)
        box3 = next(b for b in boxes if b["question"] == 2 and b["answer"] == 1)
        assert box3["manual"] == 1

        zoneid = db.toggle_box_at(1, 1, 0, 115, 215)
        assert zoneid == box3["zoneid"]

        boxes2 = db.get_page_boxes(1, 1, 0)
        box3_after = next(b for b in boxes2 if b["zoneid"] == zoneid)
        assert box3_after["manual"] == 0

    def test_toggle_manual_unchecked_to_checked(self, capture_db, project_dir):
        """Box 4 est manual=0 → toggle doit passer à 1."""
        db = AMCDatabase(str(project_dir / "data"))
        boxes = db.get_page_boxes(1, 1, 0)
        box4 = next(b for b in boxes if b["question"] == 2 and b["answer"] == 2)
        assert box4["manual"] == 0

        zoneid = db.toggle_box_at(1, 1, 0, 215, 215)
        assert zoneid == box4["zoneid"]

        boxes2 = db.get_page_boxes(1, 1, 0)
        box4_after = next(b for b in boxes2 if b["zoneid"] == zoneid)
        assert box4_after["manual"] == 1

    def test_no_boxes(self, project_dir):
        db = AMCDatabase(str(project_dir / "data"))
        result = db.toggle_box_at(1, 1, 0, 100, 100)
        assert result is None

    def test_double_toggle_returns_to_original_state(self, capture_db, project_dir):
        """Toggle deux fois → doit revenir à l'état d'avant."""
        db = AMCDatabase(str(project_dir / "data"))
        boxes_before = db.get_page_boxes(1, 1, 0)
        box = boxes_before[1]  # Q1B, non cochée
        x = (box["x1"] + box["x2"]) / 2
        y = (box["y1"] + box["y2"]) / 2

        db.toggle_box_at(1, 1, 0, x, y)
        db.toggle_box_at(1, 1, 0, x, y)

        boxes_after = db.get_page_boxes(1, 1, 0)
        box_after = next(b for b in boxes_after if b["zoneid"] == box["zoneid"])
        # Après double toggle manual=1 puis manual=0, état final = non-coché = même que l'auto
        # Le manual sera 0, pas -1, mais l'état effectif est identique
        assert box_after["manual"] in (0, -1) or box_after["manual"] == 0


# ============================================================
# get_scan_path
# ============================================================

class TestGetScanPath:
    def test_absolute_path(self, capture_db, project_dir):
        db = AMCDatabase(str(project_dir / "data"))
        path = db.get_scan_path(1, 1, 0)
        assert path is not None
        assert "scan_001.png" in path

    def test_projet_macro(self, project_dir):
        """Teste la résolution de %PROJET dans le chemin."""
        db_path = project_dir / "data" / "capture.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE capture_page "
            "(student INTEGER, page INTEGER, copy INTEGER, "
            "src TEXT, timestamp_auto REAL)"
        )
        # Créer le scan
        scan_path = project_dir / "scans" / "test.png"
        from tests.conftest import _create_test_image
        _create_test_image(str(scan_path))

        conn.execute(
            "INSERT INTO capture_page VALUES (1, 1, 0, "
            "'%PROJET/scans/test.png', 1000)"
        )
        conn.commit()
        conn.close()

        db = AMCDatabase(str(project_dir / "data"))
        path = db.get_scan_path(1, 1, 0)
        assert path is not None
        assert path.endswith("test.png")
        import os
        assert os.path.exists(path)

    def test_not_found(self, capture_db, project_dir):
        db = AMCDatabase(str(project_dir / "data"))
        path = db.get_scan_path(99, 99, 99)
        assert path is None

    def test_no_db(self, project_dir):
        db = AMCDatabase(str(project_dir / "data"))
        path = db.get_scan_path(1, 1, 0)
        assert path is None
