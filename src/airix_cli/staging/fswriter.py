# src/airix_cli/staging/fswriter.py
import re
import shutil
from pathlib import Path

TMP_DIR = Path(".tmp")

# Marcadores de conflicto de merge y de fragmento parcial. Se exigen al inicio
# de línea para no rechazar archivos legítimos que contengan, por ejemplo, una
# línea de "=======" como separador en Markdown o en un comentario.
_PARTIAL_MARKERS = [
    re.compile(r"^\s*(?://|#)\s*\.\.\.\s*resto sin cambios", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^\s*(?://|#)\s*\.\.\.\s*(?:el\s+)?resto del archivo", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^<{7}\s", re.MULTILINE),
    re.compile(r"^>{7}\s", re.MULTILINE),
    re.compile(r"^<{7}$", re.MULTILINE),
]


class PartialWriteError(Exception):
    pass


class UnsafePathError(Exception):
    """La ruta propuesta escapa del directorio de staging."""


def resolve_staged_path(relative_path: str, tmp_dir: Path | None = None) -> Path:
    """
    Traduce una ruta propuesta por el agente a su destino dentro de `.tmp/`,
    rechazando rutas absolutas o con `..` que escaparían del staging (y, tras
    la consolidación, de la raíz del repositorio).
    """
    base = (tmp_dir if tmp_dir is not None else TMP_DIR).resolve()
    candidate = Path(relative_path)
    if candidate.is_absolute() or candidate.drive or candidate.as_posix().startswith("/"):
        raise UnsafePathError(f"Ruta absoluta no permitida: {relative_path}")
    dest = (base / candidate).resolve()
    if dest != base and base not in dest.parents:
        raise UnsafePathError(
            f"La ruta '{relative_path}' escapa del directorio de staging ({base})."
        )
    if dest == base:
        raise UnsafePathError(f"Ruta inválida: {relative_path}")
    return dest


def stage_file(relative_path: str, full_content: str, *, allow_diff_marker: bool = False) -> Path:
    """
    Escribe SIEMPRE el archivo completo. Se rechaza cualquier contenido que
    contenga marcadores típicos de "fragmento" (diffs parciales, elipsis, etc.)
    para forzar al agente a entregar el archivo íntegro.
    """
    if not allow_diff_marker and any(m.search(full_content) for m in _PARTIAL_MARKERS):
        raise PartialWriteError(
            f"Se detectó un posible fragmento parcial en {relative_path}. "
            "Las propuestas deben contener el archivo completo."
        )

    dest = resolve_staged_path(relative_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(full_content, encoding="utf-8")
    return dest


def staged_files(tmp_dir: Path | None = None) -> list[Path]:
    """Lista los archivos actualmente preparados en el directorio de staging."""
    base = tmp_dir if tmp_dir is not None else TMP_DIR
    if not base.exists():
        return []
    return sorted(f for f in base.rglob("*") if f.is_file())


def clear_staging() -> None:
    base = TMP_DIR
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True, exist_ok=True)
