# src/airix_cli/staging/checkpoints.py
import tarfile
import time
from pathlib import Path

CHECKPOINTS_DIR = Path(".airix/checkpoints")
EXCLUDED_PARTS = {".git", ".airix", ".tmp", "node_modules", ".venv", "__pycache__"}


def checkpoints_dir(repo_root: Path | None = None) -> Path:
    """Directorio de checkpoints del repositorio indicado (no del cwd)."""
    if repo_root is None or CHECKPOINTS_DIR.is_absolute():
        return CHECKPOINTS_DIR
    return repo_root / CHECKPOINTS_DIR


def create_checkpoint(repo_root: Path, label: str = "") -> Path:
    # Los checkpoints viven dentro del repo que se está respaldando, no en el
    # cwd del proceso: de lo contrario `airix run` desde otro directorio
    # escribía (y `rewind` buscaba) en sitios distintos.
    target_dir = checkpoints_dir(repo_root)
    target_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%S")
    archive = target_dir / f"{ts}_{label or 'auto'}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for f in repo_root.rglob("*"):
            if any(part in EXCLUDED_PARTS for part in f.relative_to(repo_root).parts):
                continue
            if f.is_file() and not f.is_symlink():
                tar.add(f, arcname=f.relative_to(repo_root).as_posix())
    return archive


def rewind_to(checkpoint: Path, repo_root: Path) -> None:
    with tarfile.open(checkpoint, "r:gz") as tar:
        # filter="data" impide que un tar manipulado escriba fuera de
        # repo_root (rutas absolutas, "..", enlaces simbólicos, permisos).
        # El parámetro llegó en 3.11.4; en versiones previas se cae al
        # comportamiento antiguo.
        try:
            tar.extractall(repo_root, filter="data")
        except TypeError:
            tar.extractall(repo_root)
