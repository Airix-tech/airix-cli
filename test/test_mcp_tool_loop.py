# test/test_mcp_tool_loop.py
from types import SimpleNamespace

from airix_cli.agent import client as client_module
from airix_cli.agent.client import answer_question, set_model_config


class _FakeManager:
    def __init__(self, tools, calls):
        self._tools = tools
        self._calls = calls
        self.started = True

    def is_started(self):
        return self.started

    def list_tools(self):
        return self._tools

    def call_tool(self, qualified_name, arguments):
        self._calls.append((qualified_name, arguments))
        return "42"


def _one_tool():
    return [{
        "qualified_name": "testsrv__get_answer",
        "server": "testsrv",
        "name": "get_answer",
        "description": "devuelve la respuesta",
        "input_schema": {"type": "object", "properties": {}},
    }]


def test_answer_question_without_tools_uses_plain_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    set_model_config("gemini", "gemini-flash-latest")
    monkeypatch.setattr(client_module, "get_mcp_manager", lambda: _FakeManager([], []))
    monkeypatch.setattr(client_module, "_complete", lambda *a, **k: "respuesta normal")

    result = answer_question("hola", "reglas", "memoria", "workspace")

    assert result == "respuesta normal"


def test_answer_question_routes_ollama_away_from_tools_even_if_present(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    set_model_config("ollama", "qwen-coder-fast")
    calls = []
    monkeypatch.setattr(client_module, "get_mcp_manager", lambda: _FakeManager(_one_tool(), calls))
    monkeypatch.setattr(client_module, "_complete", lambda *a, **k: "respuesta ollama")

    result = answer_question("hola", "reglas", "memoria", "workspace")

    assert result == "respuesta ollama"
    assert calls == []


def test_gemini_tool_loop_calls_tool_then_returns_final_text(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    set_model_config("gemini", "gemini-flash-latest")
    calls = []
    manager = _FakeManager(_one_tool(), calls)
    monkeypatch.setattr(client_module, "get_mcp_manager", lambda: manager)

    function_call = SimpleNamespace(name="testsrv__get_answer", args={"x": 1})
    call_part = SimpleNamespace(function_call=function_call, text=None)
    first_response = SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=[call_part], role="model"))],
        text=None,
    )
    text_part = SimpleNamespace(function_call=None, text="La respuesta es 42.")
    second_response = SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=[text_part], role="model"))],
        text="La respuesta es 42.",
    )
    responses = [first_response, second_response]

    class FakeModels:
        def generate_content(self, **kwargs):
            return responses.pop(0)

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(client_module, "_get_client", lambda: FakeClient())

    status_messages = []
    result = answer_question(
        "usa la herramienta", "reglas", "memoria", "workspace", on_status=status_messages.append
    )

    assert result == "La respuesta es 42."
    assert calls == [("testsrv__get_answer", {"x": 1})]
    assert status_messages == ["Consultando herramientas MCP..."]


def test_gemini_tool_loop_bails_out_after_max_iterations(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    set_model_config("gemini", "gemini-flash-latest")
    calls = []
    manager = _FakeManager(_one_tool(), calls)
    monkeypatch.setattr(client_module, "get_mcp_manager", lambda: manager)

    function_call = SimpleNamespace(name="testsrv__get_answer", args={})
    call_part = SimpleNamespace(function_call=function_call, text=None)

    def always_tool_call_response(**_kwargs):
        return SimpleNamespace(
            candidates=[SimpleNamespace(content=SimpleNamespace(parts=[call_part], role="model"))],
            text=None,
        )

    class FakeModels:
        def generate_content(self, **kwargs):
            return always_tool_call_response(**kwargs)

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(client_module, "_get_client", lambda: FakeClient())

    result = answer_question("usa la herramienta", "reglas", "memoria", "workspace")

    assert "límite" in result
    assert len(calls) == client_module.MAX_TOOL_ITERATIONS


def test_anthropic_tool_loop_calls_tool_then_returns_final_text(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    set_model_config("anthropic", "claude-sonnet-5")
    calls = []
    manager = _FakeManager(_one_tool(), calls)
    monkeypatch.setattr(client_module, "get_mcp_manager", lambda: manager)

    tool_use_block = SimpleNamespace(type="tool_use", id="call_1", name="testsrv__get_answer", input={"x": 1})
    first_response = SimpleNamespace(stop_reason="tool_use", content=[tool_use_block])
    text_block = SimpleNamespace(type="text", text="La respuesta es 42.")
    second_response = SimpleNamespace(stop_reason="end_turn", content=[text_block])
    responses = [first_response, second_response]

    class FakeMessages:
        def create(self, **kwargs):
            return responses.pop(0)

    class FakeClient:
        messages = FakeMessages()

    monkeypatch.setattr(client_module, "_get_anthropic_client", lambda: FakeClient())

    result = answer_question("usa la herramienta", "reglas", "memoria", "workspace")

    assert result == "La respuesta es 42."
    assert calls == [("testsrv__get_answer", {"x": 1})]


def test_anthropic_tool_loop_feeds_back_tool_error_without_raising(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    set_model_config("anthropic", "claude-sonnet-5")

    class FailingManager(_FakeManager):
        def call_tool(self, qualified_name, arguments):
            raise RuntimeError("el servidor MCP no respondió")

    calls = []
    manager = FailingManager(_one_tool(), calls)
    monkeypatch.setattr(client_module, "get_mcp_manager", lambda: manager)

    tool_use_block = SimpleNamespace(type="tool_use", id="call_1", name="testsrv__get_answer", input={})
    first_response = SimpleNamespace(stop_reason="tool_use", content=[tool_use_block])
    text_block = SimpleNamespace(type="text", text="No pude usar la herramienta.")
    second_response = SimpleNamespace(stop_reason="end_turn", content=[text_block])
    responses = [first_response, second_response]

    captured_messages = {}

    class FakeMessages:
        def create(self, **kwargs):
            captured_messages["last"] = kwargs["messages"]
            return responses.pop(0)

    class FakeClient:
        messages = FakeMessages()

    monkeypatch.setattr(client_module, "_get_anthropic_client", lambda: FakeClient())

    result = answer_question("usa la herramienta", "reglas", "memoria", "workspace")

    assert result == "No pude usar la herramienta."
    tool_result = captured_messages["last"][-1]["content"][0]
    assert tool_result["is_error"] is True
    assert "el servidor MCP no respondió" in tool_result["content"]
