# src/airix_cli/context/references.py
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from airix_cli.context.workspace import IGNORED_DIRS

# Palabras que, tras una @, piden el contexto completo del repositorio en vez
# de un archivo puntual. Un "@" suelto (sin nada detrás) cuenta igual.
_WHOLE_PROJECT_KEYWORDS = {
    "proyecto",
    "project",
    "todo",
    "all",
    "workspace",
    "codebase",
    "repo",
    "repositorio",
}

# El lookbehind exige que la @ esté al inicio o precedida de espacio, para no
# disparar con direcciones de correo ("foo@bar.com") dentro de la instrucción.
_REFERENCE_PATTERN = re.compile(r"(?<!\S)@(\S*)")
_TRAILING_PUNCTUATION = ".,;:!?)]}\"'"


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def _clean_token(token: str) -> str:
    return token.strip().rstrip(_TRAILING_PUNCTUATION)


@dataclass
class ParsedReferences:
    whole_project: bool = False
    files: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)


def resolve_reference(token: str, root: Path) -> str | list[str] | None:
    """
    Resuelve un nombre o ruta de archivo mencionado (con o sin @) a una o más
    rutas relativas existentes bajo `root`.

    Primero intenta la ruta exacta relativa a la raíz del repo; si no existe,
    busca por nombre de archivo en todo el árbol (ignorando .git, node_modules,
    etc.), igual que el resto del contexto del agente. Devuelve None si no
    encuentra nada, una ruta si hay una sola coincidencia, o una lista si el
    nombre es ambiguo (varios archivos con el mismo nombre en el repo).
    """
    root = root.resolve()
    candidate = Path(token)
    if not token or candidate.is_absolute() or candidate.drive or ".." in candidate.parts:
        return None

    direct = root / candidate
    if direct.is_file():
        return candidate.as_posix()

    matches = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob(candidate.name)
        if path.is_file() and not any(part in IGNORED_DIRS for part in path.relative_to(root).parts)
    )
    if not matches:
        return None
    return matches[0] if len(matches) == 1 else matches


def parse_references(instruction: str, root: Path) -> ParsedReferences:
    """
    Interpreta las menciones `@algo` de la instrucción del usuario:

    - `@ruta/archivo.py` referencia un archivo puntual del repositorio.
    - `@proyecto`, `@all`, `@workspace`... (o un `@` suelto) piden el contexto
      completo, como antes de tener referencias explícitas.

    Una instrucción sin ningún `@` devuelve un `ParsedReferences` vacío: ese
    caso se resuelve aparte (ver `_context_for_instruction` en commands/run.py)
    para no escanear el repo cuando no hace falta.
    """
    result = ParsedReferences()
    root = root.resolve()
    seen: set[str] = set()
    for match in _REFERENCE_PATTERN.finditer(instruction):
        token = _clean_token(match.group(1))
        if not token or _normalize(token) in _WHOLE_PROJECT_KEYWORDS:
            result.whole_project = True
            continue
        resolved = resolve_reference(token, root)
        if resolved is None:
            result.unresolved.append(token)
            continue
        for path in [resolved] if isinstance(resolved, str) else resolved:
            if path not in seen:
                seen.add(path)
                result.files.append(path)
    return result
