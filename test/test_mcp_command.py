# test/test_mcp_command.py
import json

from typer.testing import CliRunner

from airix_cli.commands.mcp import app

runner = CliRunner()


def test_add_list_remove_via_cli(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["add", "figma", "npx", "--env", "FIGMA_API_KEY=x", "--", "-y", "figma-mcp"])
    assert result.exit_code == 0, result.output
    assert "agregado" in result.output

    raw = json.loads((tmp_path / ".airix" / "mcp_config.json").read_text(encoding="utf-8"))
    assert raw["mcpServers"]["figma"]["command"] == "npx"
    assert raw["mcpServers"]["figma"]["args"] == ["-y", "figma-mcp"]
    assert raw["mcpServers"]["figma"]["env"] == {"FIGMA_API_KEY": "x"}

    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "figma" in result.output

    result = runner.invoke(app, ["remove", "figma"])
    assert result.exit_code == 0
    assert "eliminado" in result.output

    result = runner.invoke(app, ["list"])
    assert "No hay servidores" in result.output


def test_add_rejects_duplicate_name(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["add", "figma", "npx"])

    result = runner.invoke(app, ["add", "figma", "npx"])

    assert result.exit_code == 1
    assert "Error" in result.output


def test_remove_rejects_missing_name(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["remove", "nope"])

    assert result.exit_code == 1
    assert "Error" in result.output
