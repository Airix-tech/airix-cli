import tarfile

import pytest

from airix_cli.staging.checkpoints import checkpoints_dir, create_checkpoint, rewind_to


def test_checkpoint_lives_inside_repo_not_cwd(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    otro = tmp_path / "otro"
    repo.mkdir()
    otro.mkdir()
    (repo / "app.py").write_text("v1", encoding="utf-8")
    monkeypatch.chdir(otro)

    archive = create_checkpoint(repo, label="t")

    assert archive.parent == checkpoints_dir(repo)
    assert archive.is_relative_to(repo)
    assert not (otro / ".airix").exists()


def test_checkpoint_excludes_internal_dirs_and_roundtrips(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".airix").mkdir(parents=True)
    (repo / "node_modules").mkdir()
    (repo / "node_modules" / "dep.js").write_text("dep", encoding="utf-8")
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("v1", encoding="utf-8")

    archive = create_checkpoint(repo, label="base")
    with tarfile.open(archive) as tar:
        names = tar.getnames()
    assert "src/app.py" in names
    assert not any(n.startswith(("node_modules", ".airix")) for n in names)

    (repo / "src" / "app.py").write_text("v2", encoding="utf-8")
    rewind_to(archive, repo)
    assert (repo / "src" / "app.py").read_text(encoding="utf-8") == "v1"


def test_rewind_refuses_paths_escaping_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    payload = tmp_path / "payload.txt"
    payload.write_text("pwned", encoding="utf-8")
    malicious = tmp_path / "malicious.tar.gz"
    with tarfile.open(malicious, "w:gz") as tar:
        tar.add(payload, arcname="../escapado.txt")

    with pytest.raises(tarfile.OutsideDestinationError):
        rewind_to(malicious, repo)
    assert not (tmp_path / "escapado.txt").exists()
