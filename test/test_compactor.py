import json

from airix_cli.context import compactor


def test_build_session_summary_extracts_context_and_decisions():
    messages = [
        {"role": "user", "content": "Necesitamos refactorizar el parser y revisar el error de importación."},
        {"role": "assistant", "content": "Voy a revisar src/airix_cli/ast_engine/parser.py y corregir el problema."},
        {"role": "user", "content": "La decisión es usar cache por hash en src/airix_cli/ast_engine/cache.py."},
        {"role": "assistant", "content": "El error actual es un TypeError al cargar el módulo de importación."},
    ]

    summary = compactor.build_session_summary(messages)

    assert "refactorizar" in summary["summary"].lower()
    assert "src/airix_cli/ast_engine/cache.py" in summary["affected_files"]
    assert any("cache por hash" in decision.lower() for decision in summary["key_decisions"])
    assert any("TypeError" in issue for issue in summary["unresolved_issues"])


def test_compact_session_persists_structured_summary(tmp_path, monkeypatch):
    session_dir = tmp_path / ".airix"
    session_dir.mkdir()
    session_path = session_dir / "session.json"
    session_path.write_text(
        json.dumps(
            [
                {"role": "user", "content": "Arreglar el parser y resolver el error de importación."},
                {"role": "assistant", "content": "Voy a revisar src/airix_cli/ast_engine/parser.py."},
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    memory_path = session_dir / "memory.json"
    monkeypatch.setattr(compactor, "SESSION_PATH", session_path)

    compactor.compact_session(memory_path=memory_path)

    saved = json.loads(session_path.read_text(encoding="utf-8"))
    payload = saved[0]["content"]

    assert "key_decisions" in payload
    assert "active_tasks" in payload
    assert "summary" in payload
