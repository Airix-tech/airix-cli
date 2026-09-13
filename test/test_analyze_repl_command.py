# test/test_analyze_repl_command.py
from airix_cli.commands import run as run_module
from airix_cli.commands.analyze import discover_analysis_targets, run_analysis


def test_discover_analysis_targets_finds_python_files(tmp_path):
    (tmp_path / "a.py").write_text("x = 1", encoding="utf-8")
    (tmp_path / "b.txt").write_text("no python", encoding="utf-8")

    targets = discover_analysis_targets(tmp_path)

    assert targets == [tmp_path / "a.py"]


def test_discover_analysis_targets_uses_explicit_paths(tmp_path):
    a = tmp_path / "a.py"
    a.write_text("x = 1", encoding="utf-8")

    targets = discover_analysis_targets(tmp_path, [str(a)])

    assert targets == [a.resolve()]


def test_run_analysis_populates_ast_cache(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.py").write_text("def foo():\n    pass\n", encoding="utf-8")

    reanalyzed = run_analysis(tmp_path)

    assert reanalyzed == [str((tmp_path / "a.py").resolve())]
    assert (tmp_path / ".airix" / "ast_cache.json").exists()


def test_repl_analyze_command_reports_reanalyzed_modules(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.py").write_text("def foo():\n    pass\n", encoding="utf-8")
    printed = []
    monkeypatch.setattr(run_module.console, "print", lambda *a, **k: printed.append(a))

    run_module._run_analyze_command(tmp_path, [])

    assert any("reanalizado" in str(call) for call in printed)
    assert (tmp_path / ".airix" / "ast_cache.json").exists()


def test_repl_analyze_command_with_no_targets_warns(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    printed = []
    monkeypatch.setattr(run_module.console, "print", lambda *a, **k: printed.append(a))

    run_module._run_analyze_command(tmp_path, [])

    assert any("No se encontraron" in str(call) for call in printed)


def test_analyze_repl_dispatch_accepts_explicit_paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from airix_cli.context import compactor

    monkeypatch.setattr(compactor, "SESSION_PATH", tmp_path / ".airix" / "session.json")
    monkeypatch.setattr(run_module, "print_banner", lambda *a, **k: None)
    monkeypatch.setattr(run_module.console, "print", lambda *a, **k: None)
    (tmp_path / "a.py").write_text("def foo():\n    pass\n", encoding="utf-8")

    captured = {}
    monkeypatch.setattr(
        run_module,
        "_run_analyze_command",
        lambda repo_root, args: captured.update(repo_root=repo_root, args=args),
    )

    inputs = iter(["/analyze a.py", "/salir"])
    monkeypatch.setattr(run_module, "_read_repl_input", lambda *a, **k: next(inputs))

    run_module.start_repl(test_cmd=None, provider=None, model=None)

    assert captured["repo_root"] == tmp_path
    assert captured["args"] == ["a.py"]
