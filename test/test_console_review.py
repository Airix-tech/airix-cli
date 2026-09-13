
import pytest

from airix_cli.repl import console as console_module
from airix_cli.repl.console import approval_repl, consolidate
from airix_cli.staging import fswriter


@pytest.fixture(autouse=True)
def _tmp_staging(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(fswriter, "TMP_DIR", tmp_path / ".tmp")
    yield


def _answers(monkeypatch, values):
    it = iter(values)
    monkeypatch.setattr(console_module.Prompt, "ask", lambda *a, **k: next(it))


def test_todo_does_not_revive_a_previous_rejection(tmp_path, monkeypatch):
    a = fswriter.stage_file("a.py", "a")
    b = fswriter.stage_file("b.py", "b")
    c = fswriter.stage_file("c.py", "c")
    _answers(monkeypatch, ["no", "todo"])

    decisions = approval_repl([a, b, c], tmp_path)

    assert decisions[a] is False  # "todo" aplica a los pendientes, no a lo ya rechazado
    assert decisions[b] is True
    assert decisions[c] is True


def test_salir_rejects_only_pending_files(tmp_path, monkeypatch):
    a = fswriter.stage_file("a.py", "a")
    b = fswriter.stage_file("b.py", "b")
    _answers(monkeypatch, ["si", "salir"])

    decisions = approval_repl([a, b], tmp_path)

    assert decisions[a] is True
    assert decisions[b] is False


def test_consolidate_copies_approved_files_into_repo(tmp_path):
    repo = tmp_path
    staged = fswriter.stage_file("src/app.py", "print('nuevo')\n")

    consolidate({staged: True}, repo, "porque sí")

    assert (repo / "src" / "app.py").read_text(encoding="utf-8") == "print('nuevo')\n"
    assert fswriter.staged_files() == []


def test_consolidate_with_no_approvals_clears_staging(tmp_path):
    staged = fswriter.stage_file("a.py", "a")

    consolidate({staged: False}, tmp_path, "")

    assert fswriter.staged_files() == []
    assert not (tmp_path / "a.py").exists()
