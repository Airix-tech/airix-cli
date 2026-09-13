# tests/test_ast_cache.py
from unittest.mock import patch

from airix_cli.ast_engine.hashing import sha256_of
from airix_cli.ast_engine.cache import analyze_file


def test_sha256_changes_with_content(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("hola")
    h1 = sha256_of(f)
    f.write_text("hola mundo")
    h2 = sha256_of(f)
    assert h1 != h2


def test_sha256_stable_for_same_content(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("hola")
    assert sha256_of(f) == sha256_of(f)


def test_analyze_file_skips_reparse_when_unchanged(tmp_path):
    f = tmp_path / "a.ts"
    f.write_text("export class A {}")
    cache: dict = {}

    with patch("airix_cli.ast_engine.cache.parse_ts_file", return_value={"exports": ["A"]}) as mock_parse:
        symbols1, reanalyzed1 = analyze_file(f, cache)
        symbols2, reanalyzed2 = analyze_file(f, cache)

    assert reanalyzed1 is True
    assert reanalyzed2 is False
    assert symbols1 == symbols2 == {"exports": ["A"]}
    mock_parse.assert_called_once()


def test_analyze_file_dispatches_python_files_to_python_parser(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("def hola():\n    pass\n")
    cache: dict = {}

    with patch("airix_cli.ast_engine.cache.parse_python_file", return_value={"exports": ["hola"]}) as mock_parse, \
         patch("airix_cli.ast_engine.cache.parse_ts_file") as mock_ts_parse:
        symbols, reanalyzed = analyze_file(f, cache)

    assert reanalyzed is True
    assert symbols == {"exports": ["hola"]}
    mock_parse.assert_called_once()
    mock_ts_parse.assert_not_called()


def test_analyze_file_reparses_when_content_changes(tmp_path):
    f = tmp_path / "a.ts"
    f.write_text("export class A {}")
    cache: dict = {}

    with patch("airix_cli.ast_engine.cache.parse_ts_file", return_value={"exports": ["A"]}):
        analyze_file(f, cache)

    f.write_text("export class A {}\nexport class B {}")
    with patch("airix_cli.ast_engine.cache.parse_ts_file", return_value={"exports": ["A", "B"]}) as mock_parse:
        symbols, reanalyzed = analyze_file(f, cache)

    assert reanalyzed is True
    assert symbols == {"exports": ["A", "B"]}
    mock_parse.assert_called_once()