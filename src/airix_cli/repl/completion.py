# src/airix_cli/repl/completion.py
from collections.abc import Callable
from pathlib import Path

from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document

from airix_cli.context.workspace import IGNORED_DIRS

# Mismas palabras clave que interpreta `airix_cli.context.references` para
# pedir el repositorio completo. Se sugieren aparte de los archivos porque no
# corresponden a una ruta real.
_WHOLE_PROJECT_KEYWORDS = ["proyecto", "project", "todo", "all", "workspace", "codebase", "repo"]

# Evita recorrer árboles enormes en cada tecla; con más archivos que esto se
# corta la búsqueda (el usuario puede seguir escribiendo para acotar por ruta
# exacta, que sí resuelve sin este límite al enviar la instrucción).
_MAX_CANDIDATES = 4000


class ReferenceCompleter(Completer):
    """
    Autocompleta menciones `@archivo` mientras se escribe en el REPL.

    Al escribir `@` seguido de texto, sugiere archivos del repositorio cuyo
    nombre o ruta contenga ese texto, además de las palabras clave que piden
    el proyecto completo (`@proyecto`, `@all`, ...). No sugiere nada fuera de
    una mención `@`, para no interferir con el resto de la instrucción.
    """

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root.resolve()

    def _candidate_paths(self) -> list[str]:
        # Se recalcula en cada invocación (rglob solo de nombres, sin leer
        # contenido) para reflejar archivos creados o borrados en la sesión.
        paths = []
        for path in self.repo_root.rglob("*"):
            if len(paths) >= _MAX_CANDIDATES:
                break
            if not path.is_file():
                continue
            rel = path.relative_to(self.repo_root)
            if any(part in IGNORED_DIRS for part in rel.parts):
                continue
            paths.append(rel.as_posix())
        return paths

    def get_completions(self, document: Document, complete_event: CompleteEvent):
        text = document.text_before_cursor
        at_index = text.rfind("@")
        if at_index == -1:
            return
        # La @ debe estar al inicio de la línea o precedida de espacio (igual
        # que al interpretar la instrucción luego), y no debe haber espacios
        # entre la @ y el cursor: si los hay, ya se terminó de escribir esa
        # mención y el cursor está en otra palabra.
        if at_index > 0 and not text[at_index - 1].isspace():
            return
        query = text[at_index + 1 :]
        if " " in query:
            return

        query_lower = query.lower()

        for keyword in _WHOLE_PROJECT_KEYWORDS:
            if keyword.startswith(query_lower):
                yield Completion(
                    keyword,
                    start_position=-len(query),
                    display=f"@{keyword}",
                    display_meta="todo el proyecto",
                )

        for rel_path in sorted(self._candidate_paths()):
            name = Path(rel_path).name
            if query_lower in rel_path.lower() or query_lower in name.lower():
                yield Completion(
                    rel_path,
                    start_position=-len(query),
                    display=rel_path,
                )


class SlashCommandCompleter(Completer):
    """
    Autocompleta los comandos `/algo` del REPL, reutilizando
    `get_repl_completion_candidates` (la misma lista que ya usa `run.py` para
    interpretar los comandos) en vez de mantener las sugerencias por separado.

    Recibe esa función por parámetro en vez de importarla directamente para
    no crear un import circular con `commands/run.py`, que ya importa este
    módulo para armar el `PromptSession`.
    """

    def __init__(self, candidates_for: Callable[[str], list[str]]):
        self._candidates_for = candidates_for

    def get_completions(self, document: Document, complete_event: CompleteEvent):
        text = document.text_before_cursor
        if not text.startswith("/"):
            return
        for candidate in self._candidates_for(text):
            if candidate == text:
                continue
            yield Completion(candidate, start_position=-len(text), display=candidate)
