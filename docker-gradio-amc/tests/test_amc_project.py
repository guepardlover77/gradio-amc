"""Tests pour amc_project.py — gestion de l'arborescence projet AMC."""

import os
import zipfile

import pytest

from amc_project import AMCProject, SUBDIRS


# ============================================================
# create_new
# ============================================================

class TestCreateNew:
    def test_creates_project(self, tmp_projects):
        proj = AMCProject.create_new(str(tmp_projects), "mon_examen")
        assert os.path.isdir(proj.project_dir)
        for sub in SUBDIRS:
            assert os.path.isdir(os.path.join(proj.project_dir, sub))

    def test_raises_on_duplicate(self, tmp_projects):
        AMCProject.create_new(str(tmp_projects), "dup")
        with pytest.raises(FileExistsError):
            AMCProject.create_new(str(tmp_projects), "dup")

    def test_project_dir_path(self, tmp_projects):
        proj = AMCProject.create_new(str(tmp_projects), "test123")
        assert proj.project_dir == os.path.join(str(tmp_projects), "test123")


# ============================================================
# import_existing
# ============================================================

class TestImportExisting:
    def _make_zip(self, tmp_path, with_root_dir=False):
        """Crée une archive ZIP de test."""
        zip_path = str(tmp_path / "project.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            prefix = "myproject/" if with_root_dir else ""
            zf.writestr(f"{prefix}data/layout.sqlite", b"fake")
            zf.writestr(f"{prefix}source.tex", b"\\documentclass{article}")
        return zip_path

    def test_import_flat_zip(self, tmp_path):
        zip_path = self._make_zip(tmp_path, with_root_dir=False)
        base = str(tmp_path / "projects")
        proj = AMCProject.import_existing(base, "imported", zip_path)
        assert os.path.isdir(proj.project_dir)
        assert os.path.exists(
            os.path.join(proj.project_dir, "data", "layout.sqlite")
        )
        assert os.path.exists(
            os.path.join(proj.project_dir, "source.tex")
        )

    def test_import_zip_with_root_dir(self, tmp_path):
        zip_path = self._make_zip(tmp_path, with_root_dir=True)
        base = str(tmp_path / "projects")
        proj = AMCProject.import_existing(base, "imported2", zip_path)
        # Le préfixe myproject/ doit être strippé
        assert os.path.exists(
            os.path.join(proj.project_dir, "data", "layout.sqlite")
        )

    def test_import_creates_subdirs(self, tmp_path):
        zip_path = self._make_zip(tmp_path)
        base = str(tmp_path / "projects")
        proj = AMCProject.import_existing(base, "imported3", zip_path)
        for sub in SUBDIRS:
            assert os.path.isdir(os.path.join(proj.project_dir, sub))

    def test_import_raises_on_duplicate(self, tmp_path):
        zip_path = self._make_zip(tmp_path)
        base = str(tmp_path / "projects")
        AMCProject.import_existing(base, "dup", zip_path)
        with pytest.raises(FileExistsError):
            AMCProject.import_existing(base, "dup", zip_path)


# ============================================================
# list_projects
# ============================================================

class TestListProjects:
    def test_empty(self, tmp_path):
        projects = AMCProject.list_projects(str(tmp_path))
        assert projects == []

    def test_lists_projects_with_data_dir(self, tmp_path):
        # Projet valide (a un sous-dossier data/)
        (tmp_path / "valid" / "data").mkdir(parents=True)
        # Pas un projet (pas de data/)
        (tmp_path / "not_a_project").mkdir()
        projects = AMCProject.list_projects(str(tmp_path))
        assert projects == ["valid"]

    def test_sorted(self, tmp_path):
        for name in ["zebra", "alpha", "middle"]:
            (tmp_path / name / "data").mkdir(parents=True)
        projects = AMCProject.list_projects(str(tmp_path))
        assert projects == ["alpha", "middle", "zebra"]

    def test_nonexistent_dir(self, tmp_path):
        projects = AMCProject.list_projects(str(tmp_path / "nope"))
        assert projects == []


# ============================================================
# get_status
# ============================================================

class TestGetStatus:
    def test_empty_project(self, project_dir):
        proj = AMCProject(str(project_dir))
        status = proj.get_status()
        assert status["source"] is False
        assert status["compiled"] is False
        assert status["scans"] is False
        assert status["analysed"] is False
        assert status["associated"] is False
        assert status["graded"] is False
        assert status["exported"] is False

    def test_with_source(self, project_dir):
        (project_dir / "source.tex").write_text("\\documentclass{article}")
        proj = AMCProject(str(project_dir))
        status = proj.get_status()
        assert status["source"] is True

    def test_with_scans(self, project_dir):
        (project_dir / "scans" / "page1.png").write_bytes(b"PNG")
        proj = AMCProject(str(project_dir))
        status = proj.get_status()
        assert status["scans"] is True

    def test_with_exports(self, project_dir):
        (project_dir / "exports" / "results.csv").write_text("a,b")
        proj = AMCProject(str(project_dir))
        status = proj.get_status()
        assert status["exported"] is True


# ============================================================
# save_source / get_source_content / get_source_path
# ============================================================

class TestSource:
    def test_save_from_content(self, project_dir):
        proj = AMCProject(str(project_dir))
        proj.save_source(content="\\documentclass{article}")
        assert proj.get_source_content() == "\\documentclass{article}"
        assert proj.get_source_path() is not None

    def test_save_from_file(self, project_dir, tmp_path):
        src = tmp_path / "uploaded.tex"
        src.write_text("hello latex")
        proj = AMCProject(str(project_dir))
        proj.save_source(uploaded_file=str(src))
        assert proj.get_source_content() == "hello latex"

    def test_no_source(self, project_dir):
        proj = AMCProject(str(project_dir))
        assert proj.get_source_path() is None
        assert proj.get_source_content() == ""

    def test_find_any_tex(self, project_dir):
        """Si source.tex n'existe pas, cherche un autre .tex."""
        (project_dir / "exam.tex").write_text("test")
        proj = AMCProject(str(project_dir))
        assert proj.get_source_path().endswith("exam.tex")


# ============================================================
# save_student_list / get_student_list_path
# ============================================================

class TestStudentList:
    def test_save_and_get(self, project_dir, tmp_path):
        csv = tmp_path / "students.csv"
        csv.write_text("ID,name\n1,Alice")
        proj = AMCProject(str(project_dir))
        proj.save_student_list(str(csv))
        path = proj.get_student_list_path()
        assert path is not None
        assert os.path.exists(path)

    def test_no_list(self, project_dir):
        proj = AMCProject(str(project_dir))
        assert proj.get_student_list_path() is None


# ============================================================
# get_scans
# ============================================================

class TestGetScans:
    def test_with_scans(self, project_dir):
        for name in ["a.png", "b.jpg", "c.tiff", "d.txt"]:
            (project_dir / "scans" / name).write_bytes(b"data")
        proj = AMCProject(str(project_dir))
        scans = proj.get_scans()
        assert "a.png" in scans
        assert "b.jpg" in scans
        assert "c.tiff" in scans
        assert "d.txt" not in scans  # pas une image

    def test_empty(self, project_dir):
        proj = AMCProject(str(project_dir))
        assert proj.get_scans() == []

    def test_sorted(self, project_dir):
        for name in ["z.png", "a.png", "m.png"]:
            (project_dir / "scans" / name).write_bytes(b"data")
        proj = AMCProject(str(project_dir))
        scans = proj.get_scans()
        assert scans == sorted(scans)


# ============================================================
# get_pdf_path
# ============================================================

class TestGetPdfPath:
    def test_sujet_pdf(self, project_dir):
        (project_dir / "_build" / "DOC-sujet.pdf").write_bytes(b"%PDF")
        proj = AMCProject(str(project_dir))
        assert proj.get_pdf_path().endswith("DOC-sujet.pdf")

    def test_fallback_any_pdf(self, project_dir):
        (project_dir / "_build" / "other.pdf").write_bytes(b"%PDF")
        proj = AMCProject(str(project_dir))
        path = proj.get_pdf_path()
        assert path is not None and path.endswith(".pdf")

    def test_fallback_compiled(self, project_dir):
        (project_dir / "amc-compiled.pdf").write_bytes(b"%PDF")
        proj = AMCProject(str(project_dir))
        assert proj.get_pdf_path().endswith("amc-compiled.pdf")

    def test_no_pdf(self, project_dir):
        proj = AMCProject(str(project_dir))
        assert proj.get_pdf_path() is None
