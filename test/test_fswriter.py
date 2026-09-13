# tests/test_fswriter.py
import pytest

from airix_cli.staging import fswriter


@pytest.fixture(autouse=True)
def _use_tmp_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(fswriter, "TMP_DIR", tmp_path / ".tmp")
    yield


def test_stage_file_writes_full_content():
    dest = fswriter.stage_file("src/app.py", "print('hola')\n")
    assert dest.exists()
    assert dest.read_text() == "print('hola')\n"


def test_stage_file_rejects_partial_diff_markers():
    with pytest.raises(fswriter.PartialWriteError):
        fswriter.stage_file("src/app.py", "def f():\n    ...\n    # ... resto sin cambios")


def test_stage_file_rejects_conflict_markers():
    with pytest.raises(fswriter.PartialWriteError):
        fswriter.stage_file("src/app.py", "<<<<<<< HEAD\ncode\n=======\nother\n")


def test_stage_file_accepts_equals_separator_in_content():
    # Una línea de "=" es un separador legítimo en Markdown/ASCII art y no debe
    # confundirse con un marcador de conflicto de merge.
    dest = fswriter.stage_file("README.md", "Titulo\n=======\n\ntexto\n")
    assert dest.exists()


def test_stage_file_rejects_path_escaping_staging():
    with pytest.raises(fswriter.UnsafePathError):
        fswriter.stage_file("../fuera.py", "x = 1")


def test_stage_file_rejects_absolute_path():
    with pytest.raises(fswriter.UnsafePathError):
        fswriter.stage_file("/etc/passwd", "x = 1")


def test_staged_files_lists_written_files():
    fswriter.stage_file("a.py", "x = 1")
    fswriter.stage_file("pkg/b.py", "y = 2")
    names = [f.relative_to(fswriter.TMP_DIR).as_posix() for f in fswriter.staged_files()]
    assert names == ["a.py", "pkg/b.py"]


def test_clear_staging_removes_files():
    fswriter.stage_file("a.py", "x = 1")
    assert fswriter.TMP_DIR.exists()
    fswriter.clear_staging()
    assert fswriter.TMP_DIR.exists()
    assert list(fswriter.TMP_DIR.iterdir()) == []