from prompt_toolkit.document import Document

from airix_cli.repl.completion import ReferenceCompleter, SlashCommandCompleter


def _make_repo(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "deploy_yolo.py").write_text("print('deploy')", encoding="utf-8")
    (tmp_path / "README.md").write_text("# repo", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "dep.js").write_text("hidden", encoding="utf-8")
    return tmp_path


def _complete(completer, text):
    document = Document(text=text, cursor_position=len(text))
    return list(completer.get_completions(document, None))


def test_at_alone_suggests_files_and_whole_project_keywords(tmp_path):
    _make_repo(tmp_path)
    completer = ReferenceCompleter(tmp_path)

    completions = _complete(completer, "analiza @")

    texts = {c.text for c in completions}
    assert "src/deploy_yolo.py" in texts
    assert "README.md" in texts
    assert "proyecto" in texts
    assert "all" in texts


def test_partial_name_filters_suggestions(tmp_path):
    _make_repo(tmp_path)
    completer = ReferenceCompleter(tmp_path)

    completions = _complete(completer, "revisa @deploy")

    texts = {c.text for c in completions}
    assert texts == {"src/deploy_yolo.py"}


def test_ignored_directories_are_never_suggested(tmp_path):
    _make_repo(tmp_path)
    completer = ReferenceCompleter(tmp_path)

    completions = _complete(completer, "@dep")

    texts = {c.text for c in completions}
    assert "node_modules/dep.js" not in texts
    assert "src/deploy_yolo.py" in texts


def test_no_at_in_line_yields_no_suggestions(tmp_path):
    _make_repo(tmp_path)
    completer = ReferenceCompleter(tmp_path)

    assert _complete(completer, "analiza deploy_yolo.py") == []


def test_email_like_at_is_not_completed(tmp_path):
    _make_repo(tmp_path)
    completer = ReferenceCompleter(tmp_path)

    assert _complete(completer, "contacta a soporte@ejem") == []


def test_completion_stops_after_reference_is_finished(tmp_path):
    _make_repo(tmp_path)
    completer = ReferenceCompleter(tmp_path)

    # Ya se escribió "@README.md " (con espacio): el cursor está en otra
    # palabra y no debe reabrir sugerencias sobre la mención ya cerrada.
    assert _complete(completer, "@README.md y ") == []


def test_completion_replaces_only_the_partial_query(tmp_path):
    _make_repo(tmp_path)
    completer = ReferenceCompleter(tmp_path)

    completions = _complete(completer, "revisa @dep")

    match = next(c for c in completions if c.text == "src/deploy_yolo.py")
    assert match.start_position == -len("dep")


def _candidates_for(text):
    from airix_cli.commands.run import get_repl_completion_candidates

    return get_repl_completion_candidates(text)


def test_slash_completer_suggests_all_commands_on_bare_slash():
    completer = SlashCommandCompleter(_candidates_for)

    completions = _complete(completer, "/")

    texts = {c.text for c in completions}
    assert "/help" in texts
    assert "/llm" in texts
    assert "/review" in texts


def test_slash_completer_expands_llm_subcommands():
    completer = SlashCommandCompleter(_candidates_for)

    completions = _complete(completer, "/llm")

    texts = {c.text for c in completions}
    assert texts == {"/llm show", "/llm list", "/llm set"}


def test_slash_completer_replaces_the_whole_line():
    completer = SlashCommandCompleter(_candidates_for)

    completions = _complete(completer, "/rev")

    match = next(c for c in completions if c.text == "/review")
    assert match.start_position == -len("/rev")


def test_slash_completer_does_nothing_outside_slash_commands():
    completer = SlashCommandCompleter(_candidates_for)

    assert _complete(completer, "analiza @deploy_yolo.py") == []
    assert _complete(completer, "hola, revisa esto") == []
