# test/test_mcp_repl_command.py
from airix_cli.agent import mcp_manager
from airix_cli.commands import run as run_module


def test_handle_mcp_command_ignores_non_mcp_input():
    assert run_module.handle_mcp_command("/llm show") is False
    assert run_module.handle_mcp_command("hola") is False


def test_mcp_show_reports_no_servers_configured(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    printed = []
    monkeypatch.setattr(run_module.typer, "secho", lambda msg, **k: printed.append(msg))

    consumed = run_module.handle_mcp_command("/mcp show")

    assert consumed is True
    assert any("No hay servidores" in msg for msg in printed)


def test_mcp_add_and_remove_via_repl(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    printed = []
    monkeypatch.setattr(run_module.typer, "secho", lambda msg, **k: printed.append(msg))

    run_module.handle_mcp_command("/mcp add figma npx -y figma-mcp")
    config = mcp_manager.load_mcp_config()
    assert config["mcpServers"]["figma"]["command"] == "npx"
    assert config["mcpServers"]["figma"]["args"] == ["-y", "figma-mcp"]

    run_module.handle_mcp_command("/mcp remove figma")
    assert "figma" not in mcp_manager.load_mcp_config()["mcpServers"]


def test_mcp_add_with_env_flag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(run_module.typer, "secho", lambda *a, **k: None)

    run_module.handle_mcp_command("/mcp add figma npx --env=FIGMA_API_KEY=abc -y figma-mcp")

    config = mcp_manager.load_mcp_config()
    assert config["mcpServers"]["figma"]["env"] == {"FIGMA_API_KEY": "abc"}
    assert config["mcpServers"]["figma"]["args"] == ["-y", "figma-mcp"]


def test_mcp_remove_unknown_server_reports_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    printed = []
    monkeypatch.setattr(run_module.typer, "secho", lambda msg, **k: printed.append(msg))

    run_module.handle_mcp_command("/mcp remove nope")

    assert any("Error" in msg for msg in printed)
