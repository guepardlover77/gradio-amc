"""Fixtures partagées pour tous les tests."""

import os
import sqlite3
import tempfile
import shutil

import pytest


@pytest.fixture
def tmp_projects(tmp_path):
    """Répertoire temporaire pour les projets AMC."""
    return tmp_path / "projects"


@pytest.fixture
def project_dir(tmp_path):
    """Crée un projet AMC complet avec arborescence standard."""
    proj = tmp_path / "test_project"
    for sub in ("data", "scans", "cr", "exports", "_build"):
        (proj / sub).mkdir(parents=True)
    return proj


@pytest.fixture
def capture_db(project_dir):
    """Crée une base capture.sqlite peuplée avec des données de test.

    Structure :
        - 2 pages scannées (student=1 page=1 copy=0, student=1 page=2 copy=0)
        - 4 cases (zones) sur la page 1 : Q1A, Q1B, Q2A, Q2B
        - Positions connues pour tester les clics
    """
    db_path = project_dir / "data" / "capture.sqlite"
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    # Tables AMC capture
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS capture_page (
            student INTEGER, page INTEGER, copy INTEGER,
            src TEXT, timestamp_auto REAL,
            timestamp_manual REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS capture_zone (
            zoneid INTEGER PRIMARY KEY AUTOINCREMENT,
            student INTEGER, page INTEGER, copy INTEGER,
            type INTEGER, id_a INTEGER, id_b INTEGER,
            total REAL, black REAL, manual INTEGER DEFAULT -1
        );
        CREATE TABLE IF NOT EXISTS capture_position (
            zoneid INTEGER, corner INTEGER, type INTEGER,
            x REAL, y REAL
        );
    """)

    # Créer une image scan factice
    scan_path = project_dir / "scans" / "scan_001.png"
    _create_test_image(str(scan_path))

    # Pages scannées
    cur.execute(
        "INSERT INTO capture_page VALUES (1, 1, 0, ?, 1000.0, 0)",
        (str(scan_path),)
    )
    cur.execute(
        "INSERT INTO capture_page VALUES (1, 2, 0, ?, 1001.0, 0)",
        (str(scan_path),)
    )

    # Zones (cases) — type=4 = ZONE_BOX
    # Box 1: Q1 réponse A — cochée (black/total > 0.5)
    cur.execute(
        "INSERT INTO capture_zone (student, page, copy, type, id_a, id_b, "
        "total, black, manual) VALUES (1, 1, 0, 4, 1, 1, 1000, 800, -1)"
    )
    z1 = cur.lastrowid
    # Box 2: Q1 réponse B — non cochée (black/total < 0.5)
    cur.execute(
        "INSERT INTO capture_zone (student, page, copy, type, id_a, id_b, "
        "total, black, manual) VALUES (1, 1, 0, 4, 1, 2, 1000, 200, -1)"
    )
    z2 = cur.lastrowid
    # Box 3: Q2 réponse A — forcé coché manuellement
    cur.execute(
        "INSERT INTO capture_zone (student, page, copy, type, id_a, id_b, "
        "total, black, manual) VALUES (1, 1, 0, 4, 2, 1, 1000, 200, 1)"
    )
    z3 = cur.lastrowid
    # Box 4: Q2 réponse B — forcé non-coché manuellement
    cur.execute(
        "INSERT INTO capture_zone (student, page, copy, type, id_a, id_b, "
        "total, black, manual) VALUES (1, 1, 0, 4, 2, 2, 1000, 800, 0)"
    )
    z4 = cur.lastrowid

    # Positions (corner 1 = top-left, corner 3 = bottom-right)
    # type=2 = coordonnées dans l'image scannée (utilisé par AMC)
    positions = [
        # zoneid, corner, type, x, y
        (z1, 1, 2, 100.0, 100.0), (z1, 3, 2, 130.0, 130.0),
        (z2, 1, 2, 200.0, 100.0), (z2, 3, 2, 230.0, 130.0),
        (z3, 1, 2, 100.0, 200.0), (z3, 3, 2, 130.0, 230.0),
        (z4, 1, 2, 200.0, 200.0), (z4, 3, 2, 230.0, 230.0),
    ]
    cur.executemany(
        "INSERT INTO capture_position VALUES (?, ?, ?, ?, ?)", positions
    )

    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def layout_db(project_dir):
    """Crée une base layout.sqlite minimale."""
    db_path = project_dir / "data" / "layout.sqlite"
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE layout_page (student INTEGER, page INTEGER);
        CREATE TABLE layout_box (question INTEGER, answer INTEGER);
        INSERT INTO layout_page VALUES (1, 1);
        INSERT INTO layout_page VALUES (1, 2);
        INSERT INTO layout_page VALUES (2, 1);
        INSERT INTO layout_box VALUES (1, 1);
        INSERT INTO layout_box VALUES (1, 2);
        INSERT INTO layout_box VALUES (2, 1);
    """)
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def scoring_db(project_dir):
    """Crée une base scoring.sqlite avec des résultats de test."""
    db_path = project_dir / "data" / "scoring.sqlite"
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE scoring_mark (
            student INTEGER, copy INTEGER,
            total REAL, max REAL, mark REAL
        );
        CREATE TABLE scoring_code (
            student INTEGER, copy INTEGER, value TEXT
        );
        CREATE TABLE scoring_score (
            student INTEGER, copy INTEGER,
            question INTEGER, score REAL
        );
        CREATE TABLE scoring_title (
            question INTEGER, title TEXT
        );
        INSERT INTO scoring_mark VALUES (1, 0, 15.0, 20.0, 15.0);
        INSERT INTO scoring_mark VALUES (2, 0, 10.0, 20.0, 10.0);
        INSERT INTO scoring_code VALUES (1, 0, '12345');
        INSERT INTO scoring_code VALUES (2, 0, '67890');
        INSERT INTO scoring_title VALUES (1, 'Q1');
        INSERT INTO scoring_title VALUES (2, 'Q2');
        INSERT INTO scoring_score VALUES (1, 0, 1, 1.0);
        INSERT INTO scoring_score VALUES (1, 0, 2, 0.0);
        INSERT INTO scoring_score VALUES (2, 0, 1, 1.0);
        INSERT INTO scoring_score VALUES (2, 0, 2, 1.0);
    """)
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def association_db(project_dir):
    """Crée une base association.sqlite."""
    db_path = project_dir / "data" / "association.sqlite"
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE association_association (
            student INTEGER, copy INTEGER,
            manual TEXT, auto TEXT
        );
        INSERT INTO association_association VALUES (1, 0, '12345', NULL);
        INSERT INTO association_association VALUES (2, 0, NULL, NULL);
    """)
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def all_dbs(capture_db, layout_db, scoring_db, association_db):
    """Crée toutes les bases SQLite d'un projet complet."""
    return {
        "capture": capture_db,
        "layout": layout_db,
        "scoring": scoring_db,
        "association": association_db,
    }


@pytest.fixture
def capture_db_with_crem(project_dir):
    """Crée une base capture.sqlite avec 4 questions CREM (10 réponses) + 1 question normale.

    Code CREM reconstitué : "1234" (chiffre coché pour Q1=1, Q2=2, Q3=3, Q4=4).
    Question 5 : 2 réponses classiques.
    """
    db_path = project_dir / "data" / "capture.sqlite"
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS capture_page (
            student INTEGER, page INTEGER, copy INTEGER,
            src TEXT, timestamp_auto REAL,
            timestamp_manual REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS capture_zone (
            zoneid INTEGER PRIMARY KEY AUTOINCREMENT,
            student INTEGER, page INTEGER, copy INTEGER,
            type INTEGER, id_a INTEGER, id_b INTEGER,
            total REAL, black REAL, manual INTEGER DEFAULT -1
        );
        CREATE TABLE IF NOT EXISTS capture_position (
            zoneid INTEGER, corner INTEGER, type INTEGER,
            x REAL, y REAL
        );
    """)

    scan_path = project_dir / "scans" / "scan_001.png"
    _create_test_image(str(scan_path))

    cur.execute(
        "INSERT INTO capture_page VALUES (1, 1, 0, ?, 1000.0, 0)",
        (str(scan_path),)
    )
    cur.execute(
        "INSERT INTO capture_page VALUES (1, 2, 0, ?, 1001.0, 0)",
        (str(scan_path),)
    )

    # 4 questions CREM x 10 réponses chacune
    # Code = "1234" : Q1→réponse 1 cochée, Q2→2, Q3→3, Q4→4
    base_x = 50
    for q in range(1, 5):
        ticked_answer = q  # le chiffre du code
        for a in range(1, 11):
            black = 800 if a == ticked_answer else 100
            cur.execute(
                "INSERT INTO capture_zone (student, page, copy, type, id_a, id_b, "
                "total, black, manual) VALUES (1, 1, 0, 4, ?, ?, 1000, ?, -1)",
                (q, a, black),
            )
            zid = cur.lastrowid
            x = base_x + (a - 1) * 30
            y = 50 + (q - 1) * 40
            cur.executemany(
                "INSERT INTO capture_position VALUES (?, ?, ?, ?, ?)",
                [
                    (zid, 1, 2, float(x), float(y)),
                    (zid, 3, 2, float(x + 20), float(y + 20)),
                ],
            )

    # Question 5 : 2 réponses classiques
    for a, black in [(1, 800), (2, 200)]:
        cur.execute(
            "INSERT INTO capture_zone (student, page, copy, type, id_a, id_b, "
            "total, black, manual) VALUES (1, 1, 0, 4, 5, ?, 1000, ?, -1)",
            (a, black),
        )
        zid = cur.lastrowid
        x = 100 + (a - 1) * 100
        y = 250
        cur.executemany(
            "INSERT INTO capture_position VALUES (?, ?, ?, ?, ?)",
            [
                (zid, 1, 2, float(x), float(y)),
                (zid, 3, 2, float(x + 30), float(y + 30)),
            ],
        )

    conn.commit()
    conn.close()
    return db_path


def _create_test_image(path, width=400, height=600):
    """Crée une image PNG de test."""
    from PIL import Image
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    img.save(path)
    return path
