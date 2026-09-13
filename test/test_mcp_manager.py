# test/test_mcp_manager.py
import json

import pytest

from airix_cli.agent.mcp_manager import McpManager, add_server, load_mcp_config, remove_server, save_mcp_config


def test_load_mcp_config_defaults_to_empty(tmp_path):
    path = tmp_path / ".airix" / "mcp_config.json"
    assert load_mcp_config(path) == {"mcpServers": {}}


def test_add_and_remove_server_round_trip(tmp_path):
    path = tmp_path / ".airix" / "mcp_config.json"

    add_server("figma", "npx", ["-y", "figma-mcp"], {"FIGMA_API_KEY": "x"}, path=path)
    config = load_mcp_config(path)
    assert config["mcpServers"]["figma"] == {
        "command": "npx",
        "args": ["-y", "figma-mcp"],
        "env": {"FIGMA_API_KEY": "x"},
    }

    remove_server("figma", path=path)
    assert load_mcp_config(path) == {"mcpServers": {}}


def test_add_server_rejects_duplicate_name(tmp_path):
    path = tmp_path / ".airix" / "mcp_config.json"
    add_server("figma", "npx", [], path=path)

    with pytest.raises(ValueError):
        add_server("figma", "npx", [], path=path)


def test_remove_server_rejects_missing_name(tmp_path):
    path = tmp_path / ".airix" / "mcp_config.json"
    with pytest.raises(ValueError):
        remove_server("nope", path=path)


def test_load_mcp_config_tolerates_corrupt_json(tmp_path):
    path = tmp_path / ".airix" / "mcp_config.json"
    path.parent.mkdir(parents=True)
    path.write_text("not json", encoding="utf-8")
    assert load_mcp_config(path) == {"mcpServers": {}}


def test_save_mcp_config_writes_pretty_json(tmp_path):
    path = tmp_path / ".airix" / "mcp_config.json"
    save_mcp_config({"mcpServers": {"a": {"command": "x", "args": [], "env": {}}}}, path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["mcpServers"]["a"]["command"] == "x"


def test_connect_all_aggregates_and_namespaces_tools(monkeypatch):
    manager = McpManager()

    async def fake_connect_one(name, spec):
        manager._sessions[name] = object()
        manager._tools[f"{name}__get_file"] = (name, "get_file", "obtiene un archivo", {})
        return 1

    monkeypatch.setattr(manager, "_connect_one", fake_connect_one)
    manager.start()
    try:
        report = manager.connect_all_sync({"mcpServers": {"figma": {}, "otro": {}}})
    finally:
        manager.shutdown()

    names = {r[0] for r in report}
    assert names == {"figma", "otro"}
    assert all(ok for _, ok, _ in report)


def test_connect_all_isolates_per_server_failures(monkeypatch):
    manager = McpManager()

    async def fake_connect_one(name, spec):
        if name == "roto":
            raise RuntimeError("no se pudo iniciar el subproceso")
        manager._tools[f"{name}__ping"] = (name, "ping", "", {})
        return 1

    monkeypatch.setattr(manager, "_connect_one", fake_connect_one)
    manager.start()
    try:
        report = manager.connect_all_sync({"mcpServers": {"sano": {}, "roto": {}}})
        assert "sano__ping" in manager._tools
    finally:
        manager.shutdown()

    report_by_name = {name: (ok, detail) for name, ok, detail in report}
    assert report_by_name["sano"][0] is True
    assert report_by_name["roto"][0] is False


def test_list_tools_returns_qualified_entries():
    manager = McpManager()
    manager._tools["figma__get_file"] = ("figma", "get_file", "desc", {"type": "object"})

    tools = manager.list_tools()

    assert tools == [{
        "qualified_name": "figma__get_file",
        "server": "figma",
        "name": "get_file",
        "description": "desc",
        "input_schema": {"type": "object"},
    }]


class _FakeTextBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class _FakeCallToolResult:
    def __init__(self, text, is_error=False):
        self.content = [_FakeTextBlock(text)]
        self.is_error = is_error


class _FakeSession:
    def __init__(self, result_text, is_error=False):
        self._result_text = result_text
        self._is_error = is_error
        self.called_with = None

    async def call_tool(self, name, arguments):
        self.called_with = (name, arguments)
        return _FakeCallToolResult(self._result_text, self._is_error)


def test_call_tool_returns_text_result():
    manager = McpManager()
    session = _FakeSession("42")
    manager._sessions["figma"] = session
    manager._tools["figma__get_file"] = ("figma", "get_file", "", {})
    manager.start()
    try:
        result = manager.call_tool("figma__get_file", {"path": "a.png"})
    finally:
        manager.shutdown()

    assert result == "42"
    assert session.called_with == ("get_file", {"path": "a.png"})


def test_call_tool_prefixes_error_results():
    manager = McpManager()
    manager._sessions["figma"] = _FakeSession("algo falló", is_error=True)
    manager._tools["figma__get_file"] = ("figma", "get_file", "", {})
    manager.start()
    try:
        result = manager.call_tool("figma__get_file", {})
    finally:
        manager.shutdown()

    assert result.startswith("[error de la herramienta]")
    assert "algo falló" in result


def test_call_tool_rejects_unknown_qualified_name():
    manager = McpManager()
    manager.start()
    try:
        with pytest.raises(ValueError):
            manager.call_tool("desconocido__x", {})
    finally:
        manager.shutdown()
