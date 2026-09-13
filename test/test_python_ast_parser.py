# test/test_python_ast_parser.py
from airix_cli.ast_engine.graph import _resolve_import_path
from airix_cli.ast_engine.parser import parse_python_file


def test_parse_python_file_extracts_classes_functions_and_imports(tmp_path):
    f = tmp_path / "mod.py"
    f.write_text(
        "import os\n"
        "from .sibling import helper\n"
        "from ..pkg.util import Thing\n"
        "\n"
        "class Foo:\n"
        "    def bar(self, x) -> int:\n"
        "        return x\n"
        "\n"
        "def top_level():\n"
        "    pass\n"
    )

    symbols = parse_python_file(f)

    assert symbols["classes"] == [
        {"name": "Foo", "methods": [{"name": "bar", "params": ["x"], "returnType": "int"}]}
    ]
    assert "top_level" in symbols["exports"]
    assert "Foo" in symbols["exports"]
    assert "os" in symbols["imports"]
    assert ".sibling" in symbols["imports"]
    assert ".sibling.helper" in symbols["imports"]
    assert "..pkg.util" in symbols["imports"]


def test_parse_python_file_respects_dunder_all(tmp_path):
    f = tmp_path / "mod.py"
    f.write_text(
        "__all__ = ['a']\n"
        "def a():\n"
        "    pass\n"
        "def b():\n"
        "    pass\n"
    )

    symbols = parse_python_file(f)

    assert symbols["exports"] == ["a"]


def test_resolve_import_path_python_relative(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "sibling.py").write_text("x = 1")
    mod = pkg / "mod.py"

    resolved = _resolve_import_path(str(mod), ".sibling")

    assert resolved == str((pkg / "sibling.py").resolve())


def test_resolve_import_path_python_absolute_against_src_layout(tmp_path, monkeypatch):
    src = tmp_path / "src" / "mypkg"
    src.mkdir(parents=True)
    (src / "util.py").write_text("x = 1")
    monkeypatch.chdir(tmp_path)

    resolved = _resolve_import_path(str(tmp_path / "src" / "mypkg" / "mod.py"), "mypkg.util")

    assert resolved == str((src / "util.py").resolve())


def test_resolve_import_path_python_ignores_external_packages(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert _resolve_import_path(str(tmp_path / "mod.py"), "os") is None
    assert _resolve_import_path(str(tmp_path / "mod.py"), "typer") is None
