# tests/test_ast_graph.py
from airix_cli.ast_engine import graph as graph_module
from airix_cli.ast_engine.graph import build_reverse_dependency_graph, _resolve_import_path


def test_resolve_import_path_relative(tmp_path):
    b = tmp_path / "b.ts"
    resolved = _resolve_import_path(str(b), "./a")
    assert resolved == str((tmp_path / "a.ts").resolve())


def test_build_reverse_dependency_graph(tmp_path):
    a = (tmp_path / "a.ts").resolve()
    b = (tmp_path / "b.ts").resolve()
    cache = {
        str(a): {"symbols": {"imports": []}},
        str(b): {"symbols": {"imports": ["./a"]}},
    }
    graph = build_reverse_dependency_graph(cache)
    assert str(b) in graph[str(a)]


def test_cascade_reanalyze_propagates_on_signature_change(tmp_path, monkeypatch):
    a = (tmp_path / "a.ts").resolve()
    b = (tmp_path / "b.ts").resolve()
    a.write_text("x")
    b.write_text("y")

    initial_cache = {
        str(a): {"hash": "old-a", "symbols": {"exports": ["A"], "imports": []}},
        str(b): {"hash": "old-b", "symbols": {"exports": ["B"], "imports": ["./a"]}},
    }
    monkeypatch.setattr(graph_module, "load_cache", lambda: dict(initial_cache))
    monkeypatch.setattr(graph_module, "save_cache", lambda c: None)

    def fake_analyze_file(path, cache):
        if path == a:
            symbols = {"exports": ["A", "A2"], "imports": []}  # firma cambió
        else:
            symbols = {"exports": ["B"], "imports": ["./a"]}  # firma NO cambió
        cache[str(path)] = {"hash": "new", "symbols": symbols}
        return symbols, True

    monkeypatch.setattr(graph_module, "analyze_file", fake_analyze_file)

    reanalyzed = graph_module.cascade_reanalyze([a])

    assert str(a) in reanalyzed
    assert str(b) in reanalyzed  # se propagó porque cambió la firma exportada de a


def test_cascade_reanalyze_does_not_propagate_without_signature_change(tmp_path, monkeypatch):
    a = (tmp_path / "a.ts").resolve()
    b = (tmp_path / "b.ts").resolve()
    a.write_text("x")
    b.write_text("y")

    initial_cache = {
        str(a): {"hash": "old-a", "symbols": {"exports": ["A"], "imports": []}},
        str(b): {"hash": "old-b", "symbols": {"exports": ["B"], "imports": ["./a"]}},
    }
    monkeypatch.setattr(graph_module, "load_cache", lambda: dict(initial_cache))
    monkeypatch.setattr(graph_module, "save_cache", lambda c: None)

    def fake_analyze_file(path, cache):
        # Ni a ni b cambiaron su firma exportada.
        symbols = {"exports": ["A"], "imports": []} if path == a else {"exports": ["B"], "imports": ["./a"]}
        cache[str(path)] = {"hash": "new", "symbols": symbols}
        return symbols, True

    monkeypatch.setattr(graph_module, "analyze_file", fake_analyze_file)

    reanalyzed = graph_module.cascade_reanalyze([a])

    assert str(a) in reanalyzed
    assert str(b) not in reanalyzed  # no se propagó: la firma de a no cambió

def test_resolve_import_path_preserves_dotted_module_names(tmp_path):
    b = tmp_path / "b.ts"
    # "./foo.utils" no debe truncarse a "foo.ts": with_suffix borraba todo lo
    # que hubiera tras el último punto.
    assert _resolve_import_path(str(b), "./foo.utils") == str((tmp_path / "foo.utils.ts").resolve())
    assert _resolve_import_path(str(b), "./lib/v1.2") == str((tmp_path / "lib" / "v1.2.ts").resolve())


def test_resolve_import_path_ignores_bare_package_specifiers(tmp_path):
    assert _resolve_import_path(str(tmp_path / "b.ts"), "react") is None
    assert _resolve_import_path(str(tmp_path / "b.ts"), "@nestjs/core") is None


def test_build_reverse_dependency_graph_tolerates_malformed_entries(tmp_path):
    a = (tmp_path / "a.ts").resolve()
    cache = {str(a): {"hash": "x"}, "otro.ts": None}
    assert build_reverse_dependency_graph(cache) == {}


def test_cascade_reanalyze_skips_missing_dependents(tmp_path, monkeypatch):
    a = (tmp_path / "a.ts").resolve()
    fantasma = (tmp_path / "fantasma.ts").resolve()
    a.write_text("x")

    initial_cache = {
        str(a): {"hash": "old-a", "symbols": {"exports": ["A"], "imports": []}},
        str(fantasma): {"hash": "old", "symbols": {"exports": [], "imports": ["./a"]}},
    }
    monkeypatch.setattr(graph_module, "load_cache", lambda: dict(initial_cache))
    monkeypatch.setattr(graph_module, "save_cache", lambda c: None)

    def fake_analyze_file(path, cache):
        symbols = {"exports": ["A", "A2"], "imports": []}
        cache[str(path)] = {"hash": "new", "symbols": symbols}
        return symbols, True

    monkeypatch.setattr(graph_module, "analyze_file", fake_analyze_file)

    # fantasma.ts está en el grafo pero no existe en disco: antes reventaba
    # todo el análisis con FileNotFoundError desde sha256_of.
    assert graph_module.cascade_reanalyze([a]) == [str(a)]
