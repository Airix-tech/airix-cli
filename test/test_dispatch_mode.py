from airix_cli.commands import run as run_module


def _stub_context(monkeypatch):
    monkeypatch.setattr(run_module, "bootstrap_context", lambda: "")
    monkeypatch.setattr(run_module, "build_workspace_context", lambda *a, **k: "")


def test_review_request_streams_answer_in_cli_and_does_not_stage(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _stub_context(monkeypatch)
    printed = []
    monkeypatch.setattr(run_module.console, "print", lambda *a, **k: printed.append((a, k)))

    def fake_answer_question(*_args, on_chunk):
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
