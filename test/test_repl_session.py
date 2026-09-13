import json

from airix_cli.commands import run as run_module
from airix_cli.context import compactor


def _session(tmp_path):
    path = tmp_path / ".airix" / "session.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def test_repl_records_instructions_and_answers_in_session(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    session_path = _session(tmp_path)
    monkeypatch.setattr(compactor, "SESSION_PATH", session_path)

    inputs = iter(["refactoriza el parser", "/salir"])
    monkeypatch.setattr(run_module, "_read_repl_input", lambda *a, **k: next(inputs))
    monkeypatch.setattr(run_module, "_dispatch_to_agent", lambda instruction, root, **_kwargs: "hecho")
    monkeypatch.setattr(run_module, "print_banner", lambda *a, **k: None)
    monkeypatch.setattr(run_module.console, "print", lambda *a, **k: None)

    run_module.start_repl(test_cmd=None, provider=None, model=None)

    saved = json.loads(session_path.read_text(encoding="utf-8"))
    # Antes solo se guardaban los comandos con "/", así que las instrucciones
    # reales nunca llegaban al historial ni disparaban la compactación.
    assert saved == [
        {"role": "user", "content": "refactoriza el parser"},
        {"role": "assistant", "content": "hecho"},
    ]


def test_repl_keeps_configured_provider_when_only_model_is_passed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(compactor, "SESSION_PATH", _session(tmp_path))
    from airix_cli.agent import client

    client.set_model_config("ollama", "qwen-coder-fast")

    inputs = iter(["/salir"])
    monkeypatch.setattr(run_module, "_read_repl_input", lambda *a, **k: next(inputs))
    monkeypatch.setattr(run_module, "print_banner", lambda *a, **k: None)
    monkeypatch.setattr(run_module.console, "print", lambda *a, **k: None)

    run_module.start_repl(test_cmd=None, provider=None, model="llama3.2:latest")

    assert client.load_model_config() == {
        "provider": "ollama",
        "model": "llama3.2:latest",
    }


def test_repl_reports_unknown_slash_command(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(compactor, "SESSION_PATH", _session(tmp_path))

    inputs = iter(["/inexistente", "/salir"])
    monkeypatch.setattr(run_module, "_read_repl_input", lambda *a, **k: next(inputs))
    monkeypatch.setattr(run_module, "print_banner", lambda *a, **k: None)
    called = []
    monkeypatch.setattr(run_module, "_dispatch_to_agent", lambda *a, **k: called.append(a))

    run_module.start_repl(test_cmd=None, provider=None, model=None)

    # Un comando con "/" desconocido no debe enviarse al agente como instrucción.
    assert called == []


def test_ctrl_c_cancels_current_line_without_exiting(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(compactor, "SESSION_PATH", _session(tmp_path))

    inputs = iter([KeyboardInterrupt(), "/salir"])

    def fake_read(*_a, **_k):
        item = next(inputs)
        if isinstance(item, BaseException):
            raise item
        return item

    monkeypatch.setattr(run_module, "_read_repl_input", fake_read)
    monkeypatch.setattr(run_module, "print_banner", lambda *a, **k: None)
    printed = []
    monkeypatch.setattr(run_module.console, "print", lambda *a, **k: printed.append(a))
    called = []
    monkeypatch.setattr(run_module, "_dispatch_to_agent", lambda *a, **k: called.append(a))

    # No debe propagar KeyboardInterrupt ni terminar el proceso: solo cancela
    # la línea actual y vuelve a pedir entrada.
    run_module.start_repl(test_cmd=None, provider=None, model=None)

    assert called == []
    assert any("Ctrl+C" in str(call) for call in printed)


def test_ctrl_d_exits_the_repl(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(compactor, "SESSION_PATH", _session(tmp_path))

    def fake_read(*_a, **_k):
        raise EOFError

    monkeypatch.setattr(run_module, "_read_repl_input", fake_read)
    monkeypatch.setattr(run_module, "print_banner", lambda *a, **k: None)
    monkeypatch.setattr(run_module.console, "print", lambda *a, **k: None)
    called = []
    monkeypatch.setattr(run_module, "_dispatch_to_agent", lambda *a, **k: called.append(a))

    # No debe lanzar la excepción hacia afuera: Ctrl+D en línea vacía cierra
    # el REPL igual que /salir.
    run_module.start_repl(test_cmd=None, provider=None, model=None)

    assert called == []
