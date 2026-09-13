from pathlib import Path

from airix_cli.context.references import parse_references, resolve_reference


def _make_repo(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "deploy_yolo.py").write_text("print('deploy')", encoding="utf-8")
    (tmp_path / "README.md").write_text("# repo", encoding="utf-8")
    return tmp_path


def test_at_file_reference_resolves_by_exact_relative_path(tmp_path):
    _make_repo(tmp_path)
    refs = parse_references("revisa @src/deploy_yolo.py por favor", tmp_path)

    assert refs.whole_project is False
    assert refs.files == ["src/deploy_yolo.py"]
    assert refs.unresolved == []


def test_at_file_reference_resolves_by_bare_name_anywhere_in_repo(tmp_path):
    _make_repo(tmp_path)
    refs = parse_references("analiza @deploy_yolo.py", tmp_path)

    assert refs.files == ["src/deploy_yolo.py"]


def test_trailing_punctuation_is_stripped(tmp_path):
    _make_repo(tmp_path)
    refs = parse_references("revisa @deploy_yolo.py, gracias", tmp_path)

    assert refs.files == ["src/deploy_yolo.py"]


def test_unresolved_reference_is_reported(tmp_path):
    _make_repo(tmp_path)
    refs = parse_references("analiza @no_existe.py", tmp_path)

    assert refs.files == []
    assert refs.unresolved == ["no_existe.py"]


def test_bare_at_alone_means_whole_project(tmp_path):
    _make_repo(tmp_path)
    refs = parse_references("@ explícame la arquitectura completa", tmp_path)

    assert refs.whole_project is True
    assert refs.unresolved == []


def test_at_project_keyword_means_whole_project(tmp_path):
    _make_repo(tmp_path)
    for keyword in ["@proyecto", "@project", "@all", "@workspace", "@Proyecto"]:
        refs = parse_references(f"{keyword} dame un resumen", tmp_path)
        assert refs.whole_project is True, keyword


def test_email_like_at_is_not_treated_as_reference(tmp_path):
    _make_repo(tmp_path)
    refs = parse_references("contáctame en soporte@ejemplo.com", tmp_path)

    assert refs.whole_project is False
    assert refs.files == []
    assert refs.unresolved == []


def test_multiple_file_references_are_all_collected(tmp_path):
    _make_repo(tmp_path)
    (tmp_path / "src" / "utils.py").write_text("x = 1", encoding="utf-8")
    refs = parse_references("compara @deploy_yolo.py con @utils.py", tmp_path)

    assert sorted(refs.files) == ["src/deploy_yolo.py", "src/utils.py"]


def test_resolve_reference_rejects_path_traversal(tmp_path):
    _make_repo(tmp_path)
    assert resolve_reference("../secrets.env", tmp_path) is None
    assert resolve_reference("/etc/passwd", tmp_path) is None


def test_resolve_reference_returns_list_when_name_is_ambiguous(tmp_path):
    _make_repo(tmp_path)
    (tmp_path / "test").mkdir()
    (tmp_path / "test" / "deploy_yolo.py").write_text("print('test copy')", encoding="utf-8")

    result = resolve_reference("deploy_yolo.py", tmp_path)

    assert sorted(result) == ["src/deploy_yolo.py", "test/deploy_yolo.py"]
