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


def test_summarize_session_uses_llm_summary_when_available(monkeypatch):
    llm_summary = {
        "summary": "Resumen generado por el LLM.",
        "key_decisions": ["decisión del LLM"],
        "active_tasks": [],
        "unresolved_issues": [],
        "affected_files": [],
    }
    monkeypatch.setattr(compactor, "summarize_with_llm", lambda messages: llm_summary)

    result = compactor.summarize_session([{"role": "user", "content": "hola"}])

    assert result == llm_summary


def test_summarize_session_falls_back_to_heuristic_when_llm_fails(monkeypatch):
    def fail(_messages):
        raise RuntimeError("Ollama no responde")

    monkeypatch.setattr(compactor, "summarize_with_llm", fail)
    messages = [
        {"role": "user", "content": "Arreglar el parser y resolver el error de importación."},
        {"role": "assistant", "content": "Voy a revisar src/airix_cli/ast_engine/parser.py."},
    ]

    result = compactor.summarize_session(messages)
    expected = compactor.build_session_summary(messages)

    # Sin el LLM disponible, cae a la heurística por palabras clave en vez de
    # perder la compactación por completo. Se compara todo menos
    # `last_updated`: cada llamada usa `datetime.now()`, así que puede diferir
    # en microsegundos entre las dos invocaciones.
    assert {k: v for k, v in result.items() if k != "last_updated"} == {
        k: v for k, v in expected.items() if k != "last_updated"
    }


def test_compact_session_clears_repl_history(tmp_path, monkeypatch):
    session_dir = tmp_path / ".airix"
    session_dir.mkdir()
    session_path = session_dir / "session.json"
    session_path.write_text(
        json.dumps([{"role": "user", "content": "hola"}]),
        encoding="utf-8",
    )
    history_path = session_dir / "repl_history"
    history_path.write_text("instrucción vieja\n", encoding="utf-8")
    memory_path = session_dir / "memory.json"
    monkeypatch.setattr(compactor, "SESSION_PATH", session_path)

    compactor.compact_session(memory_path=memory_path, summarizer=lambda _messages: {
        "summary": "ok", "key_decisions": [], "active_tasks": [],
        "unresolved_issues": [], "affected_files": [],
    })

    assert not history_path.exists()


def test_compact_session_keeps_history_when_clear_history_is_false(tmp_path, monkeypatch):
    session_dir = tmp_path / ".airix"
    session_dir.mkdir()
    session_path = session_dir / "session.json"
    session_path.write_text(
        json.dumps([{"role": "user", "content": "hola"}]),
        encoding="utf-8",
    )
    history_path = session_dir / "repl_history"
    history_path.write_text("instrucción vieja\n", encoding="utf-8")
    memory_path = session_dir / "memory.json"
    monkeypatch.setattr(compactor, "SESSION_PATH", session_path)

    compactor.compact_session(
        memory_path=memory_path,
        summarizer=lambda _messages: {
            "summary": "ok", "key_decisions": [], "active_tasks": [],
            "unresolved_issues": [], "affected_files": [],
        },
        clear_history=False,
    )

    assert history_path.exists()


def test_summarize_with_llm_delegates_to_agent_client(monkeypatch):
    from airix_cli.agent import client

    monkeypatch.setattr(client, "summarize_conversation", lambda messages: {"summary": f"{len(messages)} mensajes"})

    result = compactor.summarize_with_llm([{"role": "user", "content": "a"}, {"role": "user", "content": "b"}])

    assert result == {"summary": "2 mensajes"}
