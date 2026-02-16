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

"""Lecture des bases de données SQLite d'AMC pour afficher résultats et stats."""

import math
import os
import sqlite3

import pandas as pd


class AMCDatabase:
    """Lit les 5 bases SQLite d'AMC : layout, capture, scoring,
    association, report."""

    def __init__(self, data_dir):
        self.data_dir = data_dir

    def _connect(self, db_name):
        """Ouvre une connexion SQLite vers la base spécifiée.

        Returns:
            Connection SQLite ou None si le fichier n'existe pas.
        """
        path = os.path.join(self.data_dir, db_name)
        if not os.path.exists(path):
            return None
        return sqlite3.connect(path)

    def get_layout_info(self):
        """Informations depuis la base layout.

        Returns:
            Dict avec nombre de pages, étudiants, questions.
        """
        conn = self._connect("layout.sqlite")
        if not conn:
            return {"pages": 0, "students": 0, "questions": 0}
        try:
            cur = conn.cursor()
            # Nombre de pages
            cur.execute(
                "SELECT COUNT(DISTINCT page) FROM layout_page"
            )
            pages = cur.fetchone()[0]

            # Nombre d'étudiants (copies)
            cur.execute(
                "SELECT COUNT(DISTINCT student) FROM layout_page"
            )
            students = cur.fetchone()[0]

            # Nombre de questions
            cur.execute(
                "SELECT COUNT(DISTINCT question) FROM layout_box"
            )
            questions = cur.fetchone()[0]

            return {
                "pages": pages,
                "students": students,
                "questions": questions,
            }
        except sqlite3.OperationalError:
            return {"pages": 0, "students": 0, "questions": 0}
        finally:
            conn.close()

    def get_capture_stats(self):
        """Statistiques de capture (scans analysés).

        Returns:
            Dict avec nombre de scans analysés et pages détectées.
        """
        conn = self._connect("capture.sqlite")
        if not conn:
            return {"scans_analysed": 0, "pages_detected": 0}
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(DISTINCT src) FROM capture_page"
            )
            scans = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM capture_page")
            pages = cur.fetchone()[0]

            return {"scans_analysed": scans, "pages_detected": pages}
        except sqlite3.OperationalError:
            return {"scans_analysed": 0, "pages_detected": 0}
        finally:
            conn.close()

    def get_association_stats(self):
        """Statistiques d'association étudiants/copies.

        Returns:
            Dict avec nombre d'associés et non-associés.
        """
        conn = self._connect("association.sqlite")
        if not conn:
            return {"associated": 0, "unassociated": 0}
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM association_association "
                "WHERE manual IS NOT NULL OR auto IS NOT NULL"
            )
            associated = cur.fetchone()[0]

            cur.execute(
                "SELECT COUNT(*) FROM association_association "
                "WHERE manual IS NULL AND auto IS NULL"
            )
            unassociated = cur.fetchone()[0]

            return {
                "associated": associated,
                "unassociated": unassociated,
            }
        except sqlite3.OperationalError:
            return {"associated": 0, "unassociated": 0}
        finally:
            conn.close()

    def get_scoring_results(self):
        """Résultats de notation par étudiant.

        Returns:
            DataFrame pandas avec colonnes : student, copy, code, total, max,
            mark.  La colonne ``code`` contient le numéro étudiant décodé
            depuis les cases cochées (table scoring_code, ex: AMCcodeGridInt).
        """
        empty = pd.DataFrame(
            columns=["student", "copy", "code", "total", "max", "mark"]
        )
        conn = self._connect("scoring.sqlite")
        if not conn:
            return empty
        try:
            df = pd.read_sql_query(
                "SELECT student, copy, total, max, mark "
                "FROM scoring_mark ORDER BY student, copy",
                conn,
            )
            # Récupérer les codes étudiants (remplis sur la copie)
            try:
                codes = pd.read_sql_query(
                    "SELECT student, copy, value AS code "
                    "FROM scoring_code "
                    "ORDER BY student, copy",
                    conn,
                )
                df = df.merge(codes, on=["student", "copy"], how="left")
            except (sqlite3.OperationalError, pd.io.sql.DatabaseError):
                df["code"] = None
        except (sqlite3.OperationalError, pd.io.sql.DatabaseError):
            return empty
        finally:
            conn.close()

        # Réordonner les colonnes
        cols = ["student", "copy", "code", "total", "max", "mark"]
        return df[[c for c in cols if c in df.columns]]

    def find_correction_copy(self, correction_filename):
        """Cherche dans capture_page la copie correspondant au corrigé.

        Args:
            correction_filename: Nom de base du fichier corrigé (ex: "DOC023").
                On cherche les lignes dont ``src`` contient ce nom.

        Returns:
            Tuple (student, copy) ou None si introuvable.
        """
        conn = self._connect("capture.sqlite")
        if not conn:
            return None
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT student, copy FROM capture_page "
                "WHERE src LIKE ? LIMIT 1",
                (f"%{correction_filename}%",),
            )
            row = cur.fetchone()
            if row:
                return (row[0], row[1])
            return None
        except sqlite3.OperationalError:
            return None
        finally:
            conn.close()

    def get_question_stats(self):
        """Statistiques par question.

        Returns:
            DataFrame pandas avec colonnes : question, correct, total, pct.
        """
        conn = self._connect("scoring.sqlite")
        if not conn:
            return pd.DataFrame(
                columns=["question", "correct", "total", "pct"]
            )
        try:
            df = pd.read_sql_query(
                "SELECT t.title AS question, "
                "SUM(CASE WHEN s.score > 0 THEN 1 ELSE 0 END) AS correct, "
                "COUNT(*) AS total, "
                "ROUND(100.0 * SUM(CASE WHEN s.score > 0 THEN 1 ELSE 0 END) "
                "/ COUNT(*), 1) AS pct "
                "FROM scoring_score s "
                "JOIN scoring_title t ON s.question = t.question "
                "GROUP BY t.title ORDER BY t.title",
                conn,
            )
            return df
        except (sqlite3.OperationalError, pd.io.sql.DatabaseError):
            return pd.DataFrame(
                columns=["question", "correct", "total", "pct"]
            )
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Vérification OMR — lecture/écriture capture_zone
    # ------------------------------------------------------------------

    def get_captured_pages(self):
        """Liste des pages scannées (student, page, copy, src).

        Returns:
            Liste de dicts ou liste vide.
        """
        conn = self._connect("capture.sqlite")
        if not conn:
            return []
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT student, page, copy, src FROM capture_page "
                "WHERE timestamp_auto > 0 ORDER BY student, page, copy"
            )
            rows = cur.fetchall()
            return [
                {"student": r[0], "page": r[1], "copy": r[2], "src": r[3]}
                for r in rows
            ]
        except sqlite3.OperationalError:
            return []
        finally:
            conn.close()

    def get_page_boxes(self, student, page, copy):
        """Cases réponse d'une page avec positions et état.

        Returns:
            Liste de dicts avec zoneid, question, answer, total, black,
            manual, x1, y1, x2, y2.
        """
        conn = self._connect("capture.sqlite")
        if not conn:
            return []
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT cz.zoneid, cz.id_a AS question, cz.id_b AS answer, "
                "       cz.total, cz.black, cz.manual, "
                "       cp1.x AS x1, cp1.y AS y1, "
                "       cp2.x AS x2, cp2.y AS y2 "
                "FROM capture_zone cz "
                "JOIN capture_position cp1 "
                "  ON cp1.zoneid = cz.zoneid AND cp1.corner = 1 "
                "  AND cp1.type = cz.type "
                "JOIN capture_position cp2 "
                "  ON cp2.zoneid = cz.zoneid AND cp2.corner = 3 "
                "  AND cp2.type = cz.type "
                "WHERE cz.student = ? AND cz.page = ? AND cz.copy = ? "
                "  AND cz.type = 4 "
                "ORDER BY cz.id_a, cz.id_b",
                (student, page, copy),
            )
            cols = [
                "zoneid", "question", "answer", "total", "black",
                "manual", "x1", "y1", "x2", "y2",
            ]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        except sqlite3.OperationalError:
            return []
        finally:
            conn.close()

    def set_zone_manual(self, zoneid, value):
        """Met à jour le champ manual d'une zone (0, 1 ou -1).

        Args:
            zoneid: Identifiant de la zone.
            value: -1 (auto), 0 (forcé non-coché), 1 (forcé coché).
        """
        conn = self._connect("capture.sqlite")
        if not conn:
            return
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE capture_zone SET manual = ? WHERE zoneid = ?",
                (value, zoneid),
            )
            conn.commit()
        except sqlite3.OperationalError:
            pass
        finally:
            conn.close()

    def toggle_box_at(self, student, page, copy, x, y, threshold=40):
        """Trouve la case la plus proche de (x, y) et toggle son état.

        Returns:
            zoneid modifié ou None si aucune case assez proche.
        """
        boxes = self.get_page_boxes(student, page, copy)
        if not boxes:
            return None

        best = None
        best_dist = float("inf")
        for box in boxes:
            cx = (box["x1"] + box["x2"]) / 2
            cy = (box["y1"] + box["y2"]) / 2
            dist = math.hypot(x - cx, y - cy)
            # Accepter aussi si le clic est à l'intérieur du rectangle
            inside = (
                min(box["x1"], box["x2"]) <= x <= max(box["x1"], box["x2"])
                and min(box["y1"], box["y2"]) <= y <= max(box["y1"], box["y2"])
            )
            if inside:
                dist = 0
            if dist < best_dist:
                best_dist = dist
                best = box

        if best is None or best_dist > threshold:
            return None

        # Déterminer l'état actuel
        manual = best["manual"]
        if manual is not None and manual >= 0:
            is_ticked = manual == 1
        else:
            total = best["total"] or 1
            black = best["black"] or 0
            is_ticked = (black / total) > 0.15

        # Toggle
        new_val = 0 if is_ticked else 1
        self.set_zone_manual(best["zoneid"], new_val)
        return best["zoneid"]

    def get_scan_path(self, student, page, copy):
        """Chemin du fichier scan depuis capture_page.src.

        Résout les raccourcis %PROJET etc.

        Returns:
            Chemin absolu du scan ou None.
        """
        conn = self._connect("capture.sqlite")
        if not conn:
            return None
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT src FROM capture_page "
                "WHERE student = ? AND page = ? AND copy = ?",
                (student, page, copy),
            )
            row = cur.fetchone()
            if not row:
                return None
            src = row[0]
            # Résoudre %PROJET → répertoire parent de data/
            project_dir = os.path.dirname(self.data_dir)
            src = src.replace("%PROJET/", project_dir + "/")
            src = src.replace("%PROJET", project_dir)
            if os.path.isabs(src) and os.path.exists(src):
                return src
            # Essayer relatif au projet
            candidate = os.path.join(project_dir, src)
            if os.path.exists(candidate):
                return candidate
            return src
        except sqlite3.OperationalError:
            return None
        finally:
            conn.close()
