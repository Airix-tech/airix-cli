from airix_cli.commands import run as run_module


def _stub_context(monkeypatch):
    monkeypatch.setattr(run_module, "bootstrap_context", lambda: "")
    monkeypatch.setattr(run_module, "build_workspace_context", lambda *a, **k: "")


def test_review_request_streams_answer_in_cli_and_does_not_stage(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _stub_context(monkeypatch)
    printed = []
    monkeypatch.setattr(run_module.console, "print", lambda *a, **k: printed.append((a, k)))

    def fake_answer_question(*_args, on_chunk, **_kwargs):
        for piece in ("## Revisión\n", "- falta un try/except"):
            on_chunk(piece)
        return "## Revisión\n- falta un try/except"

    monkeypatch.setattr(run_module, "answer_question", fake_answer_question)

    def fail_propose(*_args):
        raise AssertionError("una consulta no debe pedir propuestas de archivo")

    monkeypatch.setattr(run_module, "propose_changes", fail_propose)

    answer = run_module._dispatch_to_agent("analiza deploy_yolo.py", tmp_path)

    assert answer == "## Revisión\n- falta un try/except"
    assert not (tmp_path / ".tmp").exists()
    # Cada fragmento se imprime en cuanto llega (streaming), no todo junto al final.
    streamed_calls = [a for a, k in printed if a and k.get("end") == ""]
    assert [a[0] for a in streamed_calls] == ["## Revisión\n", "- falta un try/except"]


def test_change_request_still_stages_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _stub_context(monkeypatch)
    monkeypatch.setattr(run_module.console, "print", lambda *a, **k: None)
    monkeypatch.setattr(
        run_module,
        "propose_changes",
        lambda *a: {"files": [{"path": "deploy_yolo.py", "content": "print('ok')\n"}], "rationale": "corregido"},
    )

    run_module._dispatch_to_agent("corrige deploy_yolo.py", tmp_path)

    assert (tmp_path / ".tmp" / "deploy_yolo.py").read_text(encoding="utf-8") == "print('ok')\n"


def test_at_file_reference_sends_only_that_file_as_context(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(run_module, "bootstrap_context", lambda: "")
    monkeypatch.setattr(run_module.console, "print", lambda *a, **k: None)
    (tmp_path / "deploy_yolo.py").write_text("print('target')", encoding="utf-8")
    (tmp_path / "other.py").write_text("print('should not be sent')", encoding="utf-8")

    captured = {}

    def fake_answer_question(_instruction, _governance, _memory, workspace_context, *, on_chunk, **_kwargs):
        captured["workspace_context"] = workspace_context
        return "ok"

    monkeypatch.setattr(run_module, "answer_question", fake_answer_question)

    run_module._dispatch_to_agent("analiza @deploy_yolo.py", tmp_path)

    assert "print('target')" in captured["workspace_context"]
    assert "should not be sent" not in captured["workspace_context"]


def test_at_proyecto_sends_the_whole_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(run_module, "bootstrap_context", lambda: "")
    monkeypatch.setattr(run_module.console, "print", lambda *a, **k: None)
    (tmp_path / "a.py").write_text("print('a')", encoding="utf-8")
    (tmp_path / "b.py").write_text("print('b')", encoding="utf-8")

    captured = {}

    def fake_answer_question(_instruction, _governance, _memory, workspace_context, *, on_chunk, **_kwargs):
        captured["workspace_context"] = workspace_context
        return "ok"

    monkeypatch.setattr(run_module, "answer_question", fake_answer_question)

    run_module._dispatch_to_agent("@proyecto explica la arquitectura", tmp_path)

    assert "print('a')" in captured["workspace_context"]
    assert "print('b')" in captured["workspace_context"]


def test_query_without_reference_sends_no_file_context(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(run_module, "bootstrap_context", lambda: "")
    monkeypatch.setattr(run_module.console, "print", lambda *a, **k: None)
    (tmp_path / "a.py").write_text("print('a')", encoding="utf-8")

    captured = {}

    def fake_answer_question(_instruction, _governance, _memory, workspace_context, *, on_chunk, **_kwargs):
        captured["workspace_context"] = workspace_context
        return "ok"

    monkeypatch.setattr(run_module, "answer_question", fake_answer_question)

    run_module._dispatch_to_agent("hola, como estas", tmp_path)

    assert captured["workspace_context"] == ""


def test_change_request_without_reference_still_sends_whole_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(run_module, "bootstrap_context", lambda: "")
    monkeypatch.setattr(run_module.console, "print", lambda *a, **k: None)
    (tmp_path / "a.py").write_text("print('a')", encoding="utf-8")

    captured = {}

    def fake_propose(_instruction, _governance, _memory, workspace_context):
        captured["workspace_context"] = workspace_context
        return {"files": [], "rationale": "ok"}

    monkeypatch.setattr(run_module, "propose_changes", fake_propose)

    run_module._dispatch_to_agent("refactoriza el parser", tmp_path)

    assert "print('a')" in captured["workspace_context"]


def test_unknown_reference_warns_but_does_not_crash(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(run_module, "bootstrap_context", lambda: "")
    printed = []
    monkeypatch.setattr(run_module.console, "print", lambda *a, **k: printed.append(a))
    monkeypatch.setattr(run_module, "answer_question", lambda *a, **k: "ok")

    run_module._dispatch_to_agent("analiza @no_existe.py", tmp_path)

    assert any("no_existe.py" in str(call) for call in printed)
