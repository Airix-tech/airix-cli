# test/test_context_scope.py
from airix_cli.commands import run as run_module
from airix_cli.commands.run import ContextScope, _context_for_instruction


def test_project_scope_persists_across_turns_without_reference(tmp_path):
    (tmp_path / "a.py").write_text("print('a')", encoding="utf-8")
    scope = ContextScope()

    context1, note1, _ = _context_for_instruction(
        "@proyecto explica la arquitectura", tmp_path, change_request=False, scope=scope
    )
    assert "print('a')" in context1
    assert note1 == "proyecto completo"

    context2, note2, _ = _context_for_instruction(
        "¿y el módulo de auth?", tmp_path, change_request=False, scope=scope
    )
    assert "print('a')" in context2
    assert "persistido" in note2


def test_file_scope_persists_and_is_replaced_by_new_reference(tmp_path):
    (tmp_path / "a.py").write_text("print('a')", encoding="utf-8")
    (tmp_path / "b.py").write_text("print('b')", encoding="utf-8")
    scope = ContextScope()

    _context_for_instruction("analiza @a.py", tmp_path, change_request=False, scope=scope)
    context2, note2, _ = _context_for_instruction("¿y qué más?", tmp_path, change_request=False, scope=scope)
    assert "print('a')" in context2
    assert "print('b')" not in context2
    assert "persistido" in note2

    context3, _, _ = _context_for_instruction("ahora @b.py", tmp_path, change_request=False, scope=scope)
    assert "print('b')" in context3
    assert "print('a')" not in context3
    assert scope.files == ["b.py"]


def test_ninguno_resets_persisted_scope(tmp_path):
    (tmp_path / "a.py").write_text("print('a')", encoding="utf-8")
    scope = ContextScope()
    _context_for_instruction("@proyecto explica todo", tmp_path, change_request=False, scope=scope)

    context, note, _ = _context_for_instruction("@ninguno olvida el contexto", tmp_path, change_request=False, scope=scope)
    assert context == ""
    assert "ninguno" in note
    assert scope.kind == "none"

    context2, note2, _ = _context_for_instruction("otra consulta", tmp_path, change_request=False, scope=scope)
    assert context2 == ""
    assert "fijado con @ninguno" in note2


def test_without_ever_setting_scope_keeps_old_default_behavior(tmp_path):
    (tmp_path / "a.py").write_text("print('a')", encoding="utf-8")
    scope = ContextScope()

    query_context, query_note, _ = _context_for_instruction("hola, como estas", tmp_path, change_request=False, scope=scope)
    assert query_context == ""
    assert scope.kind == "unset"

    change_context, change_note, _ = _context_for_instruction(
        "refactoriza el parser", tmp_path, change_request=True, scope=scope
    )
    assert "print('a')" in change_context
    assert scope.kind == "unset"


def test_context_scope_describe():
    assert "sin fijar" in ContextScope().describe()
    assert ContextScope(kind="project").describe() == "proyecto completo"
    assert ContextScope(kind="files", files=["a.py", "b.py"]).describe() == "archivo(s): a.py, b.py"
    assert ContextScope(kind="none").describe() == "sin archivos"


def test_repl_contexto_command_shows_active_scope(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from airix_cli.context import compactor

    monkeypatch.setattr(compactor, "SESSION_PATH", tmp_path / ".airix" / "session.json")
    monkeypatch.setattr(run_module, "print_banner", lambda *a, **k: None)
    printed = []
    monkeypatch.setattr(run_module.console, "print", lambda *a, **k: printed.append(a))

    inputs = iter(["/contexto", "/salir"])
    monkeypatch.setattr(run_module, "_read_repl_input", lambda *a, **k: next(inputs))

    run_module.start_repl(test_cmd=None, provider=None, model=None)

    assert any("sin fijar" in str(call) for call in printed)
