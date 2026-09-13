# src/airix_cli/ast_engine/graph.py
from collections import defaultdict, deque
from pathlib import Path
from airix_cli.ast_engine.cache import load_cache, save_cache, analyze_file

TS_SUFFIXES = (".ts", ".tsx", ".d.ts")


def build_reverse_dependency_graph(cache: dict) -> dict[str, set[str]]:
    """dependents[modulo] = { archivos que lo importan }"""
    dependents: dict[str, set[str]] = defaultdict(set)
    for file, entry in cache.items():
        # Una entrada malformada (cache truncado, versión antigua) no debe
        # tumbar todo el análisis.
        symbols = (entry or {}).get("symbols") or {}
        for imp in symbols.get("imports", []):
            resolved = _resolve_import_path(file, imp)
            if resolved is not None:
                dependents[resolved].add(file)
    return dependents


def _resolve_import_path(from_file: str, import_spec: str) -> str | None:
    # Resolución simplificada de rutas relativas; en producción usar
    # el resolutor de módulos real (tsconfig paths, node_resolve, etc.).
    # Los specs que no empiezan por "." son paquetes de node_modules y no
    # forman parte del grafo del repositorio.
    if not import_spec.startswith("."):
        return None
    base = Path(from_file).parent
    target = base / import_spec
    # `with_suffix` truncaba en el último punto: "./lib/v1.2" se convertía en
    # "v1.ts" y "./foo.utils" en "foo.ts". Solo se reemplaza un sufijo que ya
    # sea de TypeScript/JavaScript.
    if not target.name.endswith(TS_SUFFIXES):
        if target.suffix in {".js", ".jsx", ".mjs", ".cjs"}:
            target = target.with_suffix(".ts")
        else:
            target = target.with_name(target.name + ".ts")
    return str(target.resolve())


def cascade_reanalyze(changed_files: list[Path]) -> list[str]:
    """
    1. Reanaliza los archivos cambiados.
    2. Si sus firmas exportadas difieren de la versión cacheada anterior,
       encola en BFS a todos los que dependen (directa o transitivamente)
       de ese archivo.
    """
    cache = load_cache()
    # OJO: la llave debe ser str(f), no f (Path), porque más abajo se
    # consulta con `key = str(file)`. Con Path como llave, el lookup
    # siempre fallaba y trataba la firma anterior como vacía, disparando
    # la cascada de más en cualquier archivo con exports.
    previous_signatures = {str(f): cache.get(str(f), {}).get("symbols", {}).get("exports", [])
                            for f in changed_files}

    reanalyzed: set[str] = set()
    queue: deque[Path] = deque(changed_files)

    dependents_graph = build_reverse_dependency_graph(cache)

    while queue:
        file = queue.popleft()
        key = str(file)
        if key in reanalyzed:
            continue

        # El grafo se construye con una resolución de imports aproximada, así
        # que puede apuntar a archivos inexistentes. Saltarlos en vez de
        # abortar todo el análisis con FileNotFoundError.
        if not file.is_file():
            continue

        symbols, was_reanalyzed = analyze_file(file, cache)
        reanalyzed.add(key)

        old_exports = set(previous_signatures.get(key, []))
        new_exports = set(symbols.get("exports", []))
        signature_changed = old_exports != new_exports

        if signature_changed:
            for dependent in dependents_graph.get(key, []):
                if dependent not in reanalyzed:
                    queue.append(Path(dependent))

    save_cache(cache)
    return sorted(reanalyzed)
