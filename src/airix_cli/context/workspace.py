from fnmatch import fnmatch
from pathlib import Path

IGNORED_DIRS = {
    ".git",
    ".airix",
    ".tmp",
    ".venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "coverage",
}
IGNORED_FILENAMES = {
    ".env",
    ".env.local",
    ".env.development",
    ".env.production",
}
IGNORED_SUFFIXES = {".pem", ".key", ".crt", ".p12", ".pfx"}
DEFAULT_MAX_FILES = 100
DEFAULT_MAX_FILE_BYTES = 24_000
DEFAULT_MAX_CONTEXT_BYTES = 240_000


def _gitignore_patterns(root: Path) -> list[str]:
    path = root / ".gitignore"
    if not path.is_file():
        return []
    try:
        return [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
    except UnicodeError:
        return []


def _matches_pattern(relative_path: Path, pattern: str) -> bool:
    """
    Coincidencia aproximada de un patrón de .gitignore contra una ruta.

    Cubre los casos que la versión anterior (solo `fnmatch` sobre la ruta
    completa y sobre el nombre) dejaba pasar: patrones de directorio
    (`dist/`), anclados a la raíz (`/build`) y patrones sin barra que deben
    aplicarse a cualquier componente de la ruta (`dist` en `a/dist/b.js`).
    Las negaciones (`!algo`) se ignoran deliberadamente: en caso de duda se
    excluye el archivo, que es el lado seguro para el contexto del agente.
    """
    cleaned = pattern.strip()
    if not cleaned or cleaned.startswith("!"):
        return False
    anchored = cleaned.startswith("/")
    cleaned = cleaned.strip("/")
    if not cleaned:
        return False

    path = relative_path.as_posix()
    parts = relative_path.parts

    if fnmatch(path, cleaned):
        return True
    # Un patrón que nombra un directorio también excluye todo lo que cuelga
    # de él, así que se compara contra cada prefijo de la ruta.
    prefixes = ["/".join(parts[:i]) for i in range(1, len(parts))]
    if any(fnmatch(prefix, cleaned) for prefix in prefixes):
        return True
    if anchored or "/" in cleaned:
        return False
    # Patrón sin barra ni ancla: aplica a cualquier componente de la ruta.
    return any(fnmatch(part, cleaned) for part in parts)


def _is_ignored(relative_path: Path, patterns: list[str]) -> bool:
    for part in relative_path.parts:
        if part in IGNORED_DIRS:
            return True
    if (
        relative_path.name in IGNORED_FILENAMES
        or relative_path.name.startswith(".env")
        or relative_path.name == ".gitignore"
        or relative_path.suffix.lower() in IGNORED_SUFFIXES
    ):
        return True
    return any(_matches_pattern(relative_path, pattern) for pattern in patterns)


def _is_text_file(path: Path) -> bool:
    try:
        sample = path.read_bytes()[:4096]
    except OSError:
        return False
    return b"\x00" not in sample


def build_workspace_context(
    root: Path,
    *,
    focus_paths: list[str] | None = None,
    only_paths: list[str] | None = None,
    max_files: int = DEFAULT_MAX_FILES,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    max_context_bytes: int = DEFAULT_MAX_CONTEXT_BYTES,
) -> str:
    """
    Read a bounded, safe snapshot of text files below *root* for the agent.

    With `only_paths`, the scan of the whole tree is skipped entirely and the
    context is built from exactly those (already resolved, existing) relative
    paths — used when the user referenced specific files (`@archivo.py`)
    instead of asking for the whole project.
    """
    root = root.resolve()

    if only_paths is not None:
        candidates = [root / p for p in only_paths]
        header = [
            "## ARCHIVOS REFERENCIADOS",
            "El usuario pidió explícitamente estos archivos; el resto del repositorio no se incluyó.",
            "Las líneas `### ruta` identifican el archivo cuyo contenido aparece inmediatamente después.",
            "Raíz: . (rutas relativas)",
        ]
        return _render_sections(
            root,
            candidates,
            header,
            max_files=len(candidates),
            max_file_bytes=max_file_bytes,
            max_context_bytes=max_context_bytes,
        )

    patterns = _gitignore_patterns(root)
    candidates = sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file() and not _is_ignored(path.relative_to(root), patterns)
        ),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    focus_paths = focus_paths or []
    focus_names = {Path(value).name for value in focus_paths}
    candidates.sort(
        key=lambda path: (
            0 if path.relative_to(root).as_posix() in focus_paths else 1,
            0 if path.name in focus_names else 1,
            path.relative_to(root).as_posix(),
        )
    )

    sections = [
        "## CONTEXTO COMPLETO DEL WORKSPACE",
        "Todos los archivos legibles incluidos debajo pertenecen al workspace actual.",
        "Las líneas `### ruta` identifican el archivo cuyo contenido aparece inmediatamente después.",
        "Raíz: . (rutas relativas)",
    ]
    return _render_sections(
        root,
        candidates,
        sections,
        max_files=max_files,
        max_file_bytes=max_file_bytes,
        max_context_bytes=max_context_bytes,
    )


def _render_sections(
    root: Path,
    candidates: list[Path],
    sections: list[str],
    *,
    max_files: int,
    max_file_bytes: int,
    max_context_bytes: int,
) -> str:
    included = 0
    used_bytes = sum(len(line.encode("utf-8")) + 1 for line in sections)
    for path in candidates:
        if included >= max_files or used_bytes >= max_context_bytes:
            break
        if not _is_text_file(path):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        relative = path.relative_to(root).as_posix()
        content_bytes = content.encode("utf-8")
        if len(content_bytes) > max_file_bytes:
            content = content_bytes[:max_file_bytes].decode("utf-8", errors="ignore")
            content += "\n[contenido truncado]"
        section = f"\n### {relative}\n```text\n{content}\n```"
        section_bytes = len(section.encode("utf-8"))
        if used_bytes + section_bytes > max_context_bytes:
            break
        sections.append(section)
        used_bytes += section_bytes
        included += 1

    if not included:
        sections.append("\n(No se encontraron archivos de texto legibles.)")
    elif included < len(candidates):
        sections.append("\n[resto del workspace omitido por los límites de contexto]")
    return "".join(sections)
