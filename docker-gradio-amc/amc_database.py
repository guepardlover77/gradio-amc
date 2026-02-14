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
