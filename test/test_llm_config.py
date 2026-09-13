import json

from airix_cli.agent.client import answer_question, get_available_models, get_provider_status, load_model_config, propose_changes, set_model_config
from airix_cli.commands.llm import complete_model, complete_provider


def test_default_model_config_is_gemini_flash(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    config = load_model_config()

    assert config["provider"] == "gemini"
    assert config["model"] == "gemini-flash-latest"


def test_set_model_config_persists_and_validates_provider(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    saved = set_model_config("gemini", "gemini-2.5-pro")
    assert saved["provider"] == "gemini"
    assert saved["model"] == "gemini-2.5-pro"

    raw = json.loads((tmp_path / ".airix" / "llm_config.json").read_text(encoding="utf-8"))
    assert raw["model"] == "gemini-2.5-pro"

    models = get_available_models("gemini")
    assert "gemini-2.5-pro" in models


def test_load_model_config_migrates_retired_model(tmp_path):
    config_path = tmp_path / ".airix" / "llm_config.json"
    config_path.parent.mkdir()
    config_path.write_text(
        '{"provider": "gemini", "model": "gemini-1.5-flash"}',
        encoding="utf-8",
    )

    config = load_model_config(config_path)

    assert config["model"] == "gemini-flash-latest"
    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted["model"] == "gemini-flash-latest"


def test_llm_autocomplete_suggests_valid_values():
    # Click invoca shell_complete(ctx, param, incomplete): el prefijo es el 3er
    # argumento posicional.
    provider_suggestions = complete_provider(None, None, "g")
    model_suggestions = complete_model(None, None, "gemini-2.5")

    assert "gemini" in provider_suggestions
    assert model_suggestions
    assert all(model.startswith("gemini-2.5") for model in model_suggestions)


def test_llm_autocomplete_filters_by_prefix():
    assert complete_provider(None, None, "o") == ["ollama"]
    assert complete_provider(None, None, "zz") == []
    assert complete_model(None, None, "zz") == []


def test_ollama_model_config_accepts_local_model(tmp_path):
    saved = set_model_config("ollama", "qwen-coder-fast", tmp_path / "llm.json")

    assert saved == {"provider": "ollama", "model": "qwen-coder-fast"}


def test_ollama_config_defaults_to_qwen(tmp_path):
    config_path = tmp_path / "llm.json"
    config_path.write_text('{"provider": "ollama"}', encoding="utf-8")

    assert load_model_config(config_path) == {
        "provider": "ollama",
        "model": "qwen-coder-fast",
    }


def test_ollama_autocomplete_uses_installed_models(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"models": [{"name": "qwen-coder-fast"}, {"name": "llama3.2:latest"}]}'

    monkeypatch.setattr("airix_cli.agent.client.urlopen", lambda *_args, **_kwargs: FakeResponse())

    assert get_available_models("ollama") == ["qwen-coder-fast", "llama3.2:latest"]
    assert complete_model(None, None, "q") == ["qwen-coder-fast"]


def test_provider_status_reports_cloud_and_local(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"models": [{"name": "qwen2.5-coder:14b"}]}'

    monkeypatch.setattr("airix_cli.agent.client.urlopen", lambda *_args, **_kwargs: FakeResponse())

    status = get_provider_status()

    assert status[0]["name"] == "gemini"
    assert status[0]["kind"] == "nube"
    assert status[0]["available"] is True
    assert status[1]["name"] == "ollama"
    assert status[1]["kind"] == "local"
    assert status[1]["available"] is True
    assert "1 modelo" in status[1]["detail"]


def test_propose_changes_uses_ollama_chat_api(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    set_model_config("ollama", "qwen-coder-fast")
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"message": {"content": "{\\"files\\": [], \\"rationale\\": \\"ok\\"}"}}'

    def fake_urlopen(request, **_kwargs):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr("airix_cli.agent.client.urlopen", fake_urlopen)

    result = propose_changes("revisa el proyecto", "reglas", "memoria", "workspace")

    assert result == {"files": [], "rationale": "ok"}
    assert captured["url"].endswith("/api/chat")
    assert captured["body"]["model"] == "qwen-coder-fast"
    assert captured["body"]["stream"] is False
    assert captured["body"]["options"]["num_ctx"] == 32768
    assert "qwen-coder-fast" in captured["body"]["messages"][0]["content"]
    assert "responde directamente" in captured["body"]["messages"][0]["content"]
    assert '"rationale": "OK"' in captured["body"]["messages"][0]["content"]


def test_answer_question_returns_plain_text_without_json_format(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    set_model_config("ollama", "qwen2.5-coder:7b")
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"message": {"content": "  ## Revision\\n- falta manejo de errores  "}}'

    def fake_urlopen(request, **_kwargs):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr("airix_cli.agent.client.urlopen", fake_urlopen)

    result = answer_question("analiza deploy_yolo.py", "reglas", "memoria", "workspace")

    assert result == "## Revision\n- falta manejo de errores"
    assert "format" not in captured["body"]
    system_prompt = captured["body"]["messages"][0]["content"]
    assert "Modo consulta" in system_prompt
    assert '"files"' not in system_prompt
