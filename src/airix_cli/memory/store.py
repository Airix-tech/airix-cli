# src/airix_cli/memory/store.py
import os
import tempfile
from pathlib import Path
from airix_cli.memory.schema import MemoryFile, ResolvedError, TechnicalDecision

def init_memory_file(path: Path) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(MemoryFile().model_dump_json(indent=2), encoding="utf-8")

def load_memory(path: Path) -> MemoryFile:
    if not path.exists():
        init_memory_file(path)
    return MemoryFile.model_validate_json(path.read_text(encoding="utf-8"))

def save_memory(path: Path, memory: MemoryFile) -> None:
    """Escritura atómica: escribe a un temp file y renombra (evita corrupción)."""
    data = memory.model_dump_json(indent=2)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        # Sin esto, un fallo a mitad de escritura dejaba un .tmp huérfano
        # junto a memory.json en cada intento.
        Path(tmp_path).unlink(missing_ok=True)
        raise

def append_decision(path: Path, decision: TechnicalDecision) -> None:
    mem = load_memory(path)
    mem.decisions.append(decision)
    save_memory(path, mem)

def append_resolved_error(path: Path, error: ResolvedError) -> None:
    mem = load_memory(path)
    mem.resolved_errors.append(error)
    save_memory(path, mem)