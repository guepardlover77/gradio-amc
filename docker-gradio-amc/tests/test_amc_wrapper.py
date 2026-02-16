"""Tests pour amc_wrapper.py — wrapper subprocess AMC CLI."""

import os
from unittest.mock import patch, MagicMock

import pytest

from amc_wrapper import AMCCommandRunner


@pytest.fixture
def runner():
    return AMCCommandRunner()


# ============================================================
# _run
# ============================================================

class TestRun:
    def test_command_not_found(self, runner):
        rc, out, err = runner._run(["nonexistent-subcommand"])
        assert rc == -1
        assert "introuvable" in err

    @patch("subprocess.Popen")
    def test_successful_run(self, mock_popen, runner):
        proc = MagicMock()
        proc.communicate.return_value = ("output line\n", "")
        proc.returncode = 0
        mock_popen.return_value = proc

        rc, out, err = runner._run(["prepare", "--help"])
        assert rc == 0
        assert "output line" in out

    @patch("subprocess.Popen")
    def test_failed_run(self, mock_popen, runner):
        proc = MagicMock()
        proc.communicate.return_value = ("", "error msg")
        proc.returncode = 1
        mock_popen.return_value = proc

        rc, out, err = runner._run(["prepare"])
        assert rc == 1
        assert "error msg" in err

    @patch("subprocess.Popen")
    def test_includes_cmd_header(self, mock_popen, runner):
        proc = MagicMock()
        proc.communicate.return_value = ("hello", "")
        proc.returncode = 0
        mock_popen.return_value = proc

        rc, out, err = runner._run(["test"], cwd="/tmp")
        assert "[CMD]" in out
        assert "[CWD] /tmp" in out


# ============================================================
# prepare_document
# ============================================================

class TestPrepareDocument:
    @patch("subprocess.Popen")
    def test_args_mode_s(self, mock_popen, runner, tmp_path):
        proc = MagicMock()
        proc.communicate.return_value = ("ok", "")
        proc.returncode = 0
        mock_popen.return_value = proc

        runner.prepare_document(str(tmp_path), "source.tex", 30, mode="s")
        args = mock_popen.call_args[0][0]
        assert "prepare" in args
        assert "--mode" in args
        idx = args.index("--mode")
        assert args[idx + 1] == "s"
        assert "--n-copies" in args
        assert "30" in args

    @patch("subprocess.Popen")
    def test_creates_dirs(self, mock_popen, runner, tmp_path):
        proc = MagicMock()
        proc.communicate.return_value = ("", "")
        proc.returncode = 0
        mock_popen.return_value = proc

        runner.prepare_document(str(tmp_path), "src.tex", 10)
        assert os.path.isdir(os.path.join(str(tmp_path), "data"))
        assert os.path.isdir(os.path.join(str(tmp_path), "_build"))


# ============================================================
# compute_layout
# ============================================================

class TestComputeLayout:
    def test_missing_calage_file(self, runner, tmp_path):
        rc, out, err = runner.compute_layout(str(tmp_path))
        assert rc == 1
        assert "introuvable" in err

    @patch("subprocess.Popen")
    def test_with_calage(self, mock_popen, runner, tmp_path):
        proc = MagicMock()
        proc.communicate.return_value = ("done", "")
        proc.returncode = 0
        mock_popen.return_value = proc

        calage = tmp_path / "calage.xy"
        calage.write_text("data")
        runner.compute_layout(str(tmp_path), str(calage))
        args = mock_popen.call_args[0][0]
        assert "meptex" in args
        assert "--src" in args


# ============================================================
# import_scans
# ============================================================

class TestImportScans:
    @patch("subprocess.Popen")
    def test_import_multiple_files(self, mock_popen, runner, tmp_path):
        proc = MagicMock()
        proc.communicate.return_value = ("imported", "")
        proc.returncode = 0
        mock_popen.return_value = proc

        rc, out, err = runner.import_scans(str(tmp_path), ["a.pdf", "b.pdf"])
        assert rc == 0
        assert mock_popen.call_count == 2

    @patch("subprocess.Popen")
    def test_partial_failure(self, mock_popen, runner, tmp_path):
        proc_ok = MagicMock()
        proc_ok.communicate.return_value = ("ok", "")
        proc_ok.returncode = 0
        proc_fail = MagicMock()
        proc_fail.communicate.return_value = ("", "fail")
        proc_fail.returncode = 1
        mock_popen.side_effect = [proc_ok, proc_fail]

        rc, out, err = runner.import_scans(str(tmp_path), ["a.pdf", "b.pdf"])
        assert rc == 1

    @patch("subprocess.Popen")
    def test_creates_scans_dir(self, mock_popen, runner, tmp_path):
        proc = MagicMock()
        proc.communicate.return_value = ("", "")
        proc.returncode = 0
        mock_popen.return_value = proc

        runner.import_scans(str(tmp_path), ["x.pdf"])
        assert os.path.isdir(os.path.join(str(tmp_path), "scans"))


# ============================================================
# analyse_scans
# ============================================================

class TestAnalyseScans:
    def test_no_images(self, runner, project_dir):
        rc, out, err = runner.analyse_scans(str(project_dir))
        assert rc == 1
        assert "Aucune image" in err

    @patch("subprocess.Popen")
    def test_with_images(self, mock_popen, runner, project_dir):
        proc = MagicMock()
        proc.communicate.return_value = ("analysed", "")
        proc.returncode = 0
        mock_popen.return_value = proc

        (project_dir / "scans" / "page1.jpg").write_bytes(b"img")
        rc, out, err = runner.analyse_scans(str(project_dir), n_procs=2)
        args = mock_popen.call_args[0][0]
        assert "analyse" in args
        assert "--n-procs" in args
        assert "2" in args

    @patch("subprocess.Popen")
    def test_multiple_flag(self, mock_popen, runner, project_dir):
        proc = MagicMock()
        proc.communicate.return_value = ("", "")
        proc.returncode = 0
        mock_popen.return_value = proc

        (project_dir / "scans" / "page1.png").write_bytes(b"img")
        runner.analyse_scans(str(project_dir), multiple=True)
        args = mock_popen.call_args[0][0]
        assert "--multiple" in args

    @patch("subprocess.Popen")
    def test_no_multiple_flag_by_default(self, mock_popen, runner, project_dir):
        proc = MagicMock()
        proc.communicate.return_value = ("", "")
        proc.returncode = 0
        mock_popen.return_value = proc

        (project_dir / "scans" / "page1.png").write_bytes(b"img")
        runner.analyse_scans(str(project_dir))
        args = mock_popen.call_args[0][0]
        assert "--multiple" not in args


# ============================================================
# auto_associate
# ============================================================

class TestAutoAssociate:
    @patch("subprocess.Popen")
    def test_args(self, mock_popen, runner, tmp_path):
        proc = MagicMock()
        proc.communicate.return_value = ("", "")
        proc.returncode = 0
        mock_popen.return_value = proc

        runner.auto_associate(str(tmp_path), "students.csv", "ID", "id")
        args = mock_popen.call_args[0][0]
        assert "association-auto" in args
        assert "--liste-key" in args
        idx = args.index("--liste-key")
        assert args[idx + 1] == "ID"


# ============================================================
# calculate_grades
# ============================================================

class TestCalculateGrades:
    @patch("subprocess.Popen")
    def test_basic_args(self, mock_popen, runner, tmp_path):
        proc = MagicMock()
        proc.communicate.return_value = ("", "")
        proc.returncode = 0
        mock_popen.return_value = proc

        runner.calculate_grades(str(tmp_path), notemax=20, grain=0.5)
        args = mock_popen.call_args[0][0]
        assert "note" in args
        assert "--notemax" in args
        assert "20" in args

    @patch("subprocess.Popen")
    def test_postcorrect_args(self, mock_popen, runner, tmp_path):
        proc = MagicMock()
        proc.communicate.return_value = ("", "")
        proc.returncode = 0
        mock_popen.return_value = proc

        runner.calculate_grades(
            str(tmp_path), postcorrect_student=1, postcorrect_copy=5
        )
        args = mock_popen.call_args[0][0]
        assert "--postcorrect-student" in args
        assert "--postcorrect-copy" in args

    @patch("subprocess.Popen")
    def test_no_postcorrect(self, mock_popen, runner, tmp_path):
        proc = MagicMock()
        proc.communicate.return_value = ("", "")
        proc.returncode = 0
        mock_popen.return_value = proc

        runner.calculate_grades(str(tmp_path))
        args = mock_popen.call_args[0][0]
        assert "--postcorrect-student" not in args


# ============================================================
# export_results
# ============================================================

class TestExportResults:
    @patch("subprocess.Popen")
    def test_csv_export(self, mock_popen, runner, tmp_path):
        proc = MagicMock()
        proc.communicate.return_value = ("", "")
        proc.returncode = 0
        mock_popen.return_value = proc

        output = str(tmp_path / "exports" / "results.csv")
        runner.export_results(str(tmp_path), output, module="CSV")
        args = mock_popen.call_args[0][0]
        assert "export" in args
        assert "--module" in args
        idx = args.index("--module")
        assert args[idx + 1] == "CSV"

    @patch("subprocess.Popen")
    def test_with_student_list(self, mock_popen, runner, tmp_path):
        proc = MagicMock()
        proc.communicate.return_value = ("", "")
        proc.returncode = 0
        mock_popen.return_value = proc

        runner.export_results(
            str(tmp_path), "out.csv", student_list="students.csv"
        )
        args = mock_popen.call_args[0][0]
        assert "--fich-noms" in args
