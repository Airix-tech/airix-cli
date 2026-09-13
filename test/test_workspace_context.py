from airix_cli.context.workspace import build_workspace_context


def test_reads_text_files_and_respects_ignored_paths(tmp_path):
    (tmp_path / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('visible')", encoding="utf-8")
    (tmp_path / "ignored.py").write_text("print('ignored')", encoding="utf-8")
    (tmp_path / ".env.local").write_text("TOKEN=secret", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "dependency.js").write_text("hidden", encoding="utf-8")
    (tmp_path / "image.png").write_bytes(b"\x89PNG\x00binary")

    context = build_workspace_context(tmp_path)

    assert "### src/app.py" in context
    assert "print('visible')" in context
    assert "ignored.py" not in context
    assert ".env.local" not in context
    assert "dependency.js" not in context
    assert "image.png" not in context


def test_limits_number_and_size_of_files(tmp_path):
    (tmp_path / "a.txt").write_text("a" * 100, encoding="utf-8")
    (tmp_path / "b.txt").write_text("b" * 100, encoding="utf-8")

    context = build_workspace_context(
        tmp_path,
        max_files=1,
        max_file_bytes=10,
        max_context_bytes=1_000,
    )

    assert "### a.txt" in context
    assert "aaaaaaaaaa" in context
    assert "### b.txt" not in context
    assert "contenido truncado" in context


def test_focus_paths_are_included_first(tmp_path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "deploy_yolo.py").write_text("print('target')", encoding="utf-8")

    context = build_workspace_context(tmp_path, focus_paths=["deploy_yolo.py"], max_files=1)

    assert "### deploy_yolo.py" in context
    assert "print('target')" in context


def test_gitignore_directory_patterns_are_respected(tmp_path):
    (tmp_path / ".gitignore").write_text("dist/\n/solo_raiz\ngenerated\n", encoding="utf-8")
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "bundle.js").write_text("BUNDLE", encoding="utf-8")
    (tmp_path / "solo_raiz").mkdir()
    (tmp_path / "solo_raiz" / "x.py").write_text("RAIZ", encoding="utf-8")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "generated").mkdir()
    (tmp_path / "pkg" / "generated" / "y.py").write_text("GENERADO", encoding="utf-8")
    (tmp_path / "pkg" / "keep.py").write_text("VISIBLE", encoding="utf-8")

    context = build_workspace_context(tmp_path)

    assert "BUNDLE" not in context
    assert "RAIZ" not in context
    assert "GENERADO" not in context
    assert "VISIBLE" in context


def test_root_anchored_pattern_does_not_ignore_nested_match(tmp_path):
    (tmp_path / ".gitignore").write_text("/artefactos\n", encoding="utf-8")
    (tmp_path / "pkg" / "artefactos").mkdir(parents=True)
    (tmp_path / "pkg" / "artefactos" / "z.py").write_text("ANIDADO", encoding="utf-8")

    assert "ANIDADO" in build_workspace_context(tmp_path)
