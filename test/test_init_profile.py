# tests/test_init_profile.py
from airix_cli.commands.init import detect_architectural_profile, init_repo
from airix_cli.commands.run import get_repl_completion_candidates, handle_llm_command


def test_repl_llm_commands_are_not_sent_to_agent():
    assert handle_llm_command("/llm show") is True
    assert handle_llm_command("llm show") is False
    assert handle_llm_command("/llm list gemini") is True
    assert handle_llm_command("llm list gemini") is False
    assert handle_llm_command("/llm set gemini gemini-2.5-pro") is True
    assert handle_llm_command("llm set gemini gemini-2.5-pro") is False
    assert handle_llm_command("refactoriza el parser") is False


def test_repl_completion_only_suggests_slash_commands():
    suggestions = get_repl_completion_candidates("/")

    assert "/help" in suggestions
    assert "/llm" in suggestions
    assert "/review" in suggestions
    assert "/compact" in suggestions
    assert "/salir" in suggestions

    llm_suggestions = get_repl_completion_candidates("/llm")
    assert "/llm show" in llm_suggestions
    assert "/llm list" in llm_suggestions
    assert "/llm set" in llm_suggestions
    assert "llm show" not in llm_suggestions


def test_init_creates_agency_file_in_uppercase(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    init_repo()

    assert (tmp_path / "AGENT.md").exists()
    assert not (tmp_path / "agent.md").exists()


def test_detects_python_language_and_pytest(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print(1)")
    (tmp_path / "src" / "utils.py").write_text("print(2)")

    profile = detect_architectural_profile(tmp_path)

    assert profile.language == "Python"
    assert profile.test_command == "pytest -q"


def test_detects_node_project_and_npm_test(tmp_path):
    (tmp_path / "package.json").write_text(
        '{"dependencies": {"react": "^18.0.0"}, "scripts": {"test": "jest"}}'
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "index.tsx").write_text("export const App = () => null;")

    profile = detect_architectural_profile(tmp_path)

    assert profile.language == "TypeScript"
    assert "react" in profile.frameworks
    assert profile.test_command == "npm test"


def test_empty_repo_has_no_language(tmp_path):
    profile = detect_architectural_profile(tmp_path)
    assert profile.language is None
    assert profile.test_command is None

def test_init_persists_detected_profile_in_memory(tmp_path, monkeypatch):
    import json

    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\ndeps=['fastapi']\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "app.py").write_text("print(1)")

    init_repo()

    memory = json.loads((tmp_path / ".airix" / "memory.json").read_text(encoding="utf-8"))
    # `airix init` debe dejar el perfil en memory.json: de él sale el comando de
    # tests que `airix run` usa cuando no se pasa --test-cmd.
    assert memory["profile"]["language"] == "Python"
    assert memory["profile"]["test_command"] == "pytest -q"
    assert "Python" in (tmp_path / "AGENT.md").read_text(encoding="utf-8")


def test_ast_engine_package_exposes_no_cli_symbols():
    import airix_cli.ast_engine as ast_engine

    # ast_engine/__init__.py llegó a contener una copia entera de
    # commands/init.py: importar el motor AST ejecutaba el comando `init`.
    assert not hasattr(ast_engine, "init_repo")
    assert not hasattr(ast_engine, "detect_architectural_profile")
