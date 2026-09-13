import subprocess

import pytest

from airix_cli.staging.git_review import GitReviewError, stage_for_visual_review


def _git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_stage_for_visual_review_does_not_create_commit(tmp_path):
    _git(tmp_path, "init")
    (tmp_path / "app.py").write_text("print('base')\n")
    _git(tmp_path, "add", "app.py")
    _git(tmp_path, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "base")
    proposed = tmp_path / "app.py"
    proposed.write_text("print('proposed')\n")
    head = _git(tmp_path, "rev-parse", "HEAD")
    stage_for_visual_review(tmp_path, [proposed])

    assert _git(tmp_path, "rev-parse", "HEAD") == head
    assert _git(tmp_path, "diff", "--cached", "--name-only") == "app.py"
    assert _git(tmp_path, "diff", "--cached", "--", "app.py")


def test_stage_for_visual_review_supports_unborn_repository(tmp_path):
    _git(tmp_path, "init")
    proposed = tmp_path / "new.py"
    proposed.write_text("answer = 42\n")

    stage_for_visual_review(tmp_path, [proposed])

    assert _git(tmp_path, "diff", "--cached", "--name-only") == "new.py"

def test_stage_for_visual_review_rejects_files_outside_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    fuera = tmp_path / "fuera.py"
    fuera.write_text("x = 1\n")

    with pytest.raises(GitReviewError):
        stage_for_visual_review(repo, [fuera])
