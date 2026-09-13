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
    if from_file.endswith(".py"):
        return _resolve_python_import(from_file, import_spec)
    return _resolve_ts_import(from_file, import_spec)


def _resolve_ts_import(from_file: str, import_spec: str) -> str | None:
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


def _resolve_python_import(from_file: str, import_spec: str) -> str | None:
    """
    Resolución simplificada de imports Python para el grafo de dependencias:
    - Relativos ("." / ".." / ".pkg.mod"): se resuelven contra el directorio
      del archivo, subiendo un nivel por cada punto extra (semántica estándar
      de paquetes relativos).
    - Absolutos ("airix_cli.ast_engine.cache"): se prueban contra la raíz del
      repo y contra `src/`, el layout de este propio proyecto. No reproduce
      sys.path completo ni namespace packages ni editable installs con rutas
      custom.
    Un spec que no resuelve a un archivo real (paquete externo, alias
    inexistente) se descarta en vez de fallar.
    """
    dots = len(import_spec) - len(import_spec.lstrip("."))
    remainder = import_spec[dots:]
    parts = remainder.split(".") if remainder else []

    if dots > 0:
        base_dir = Path(from_file).parent
        for _ in range(dots - 1):
            base_dir = base_dir.parent
        candidate_roots = [base_dir]
    else:
        candidate_roots = [Path.cwd(), Path.cwd() / "src"]

    for root in candidate_roots:
        target = root.joinpath(*parts) if parts else root
        module_file = target.with_suffix(".py")
        if module_file.is_file():
            return str(module_file.resolve())
        init_file = target / "__init__.py"
        if init_file.is_file():
            return str(init_file.resolve())
    return None


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
