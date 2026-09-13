# src/airix_cli/ast_engine/parser.py
import json
import os
import shutil
import subprocess
from pathlib import Path

SIDECAR_RELATIVE = Path("sidecar") / "extract_symbols.js"


def _candidate_sidecar_paths() -> list[Path]:
    """
    Ubicaciones donde puede vivir el sidecar Node, en orden de preferencia.

    `parents[3]` solo acierta con una instalación editable (src-layout desde el
    repo). Instalado en site-packages apunta a un directorio arbitrario, así que
    se prueban también el cwd y AIRIX_SIDECAR.
    """
    candidates: list[Path] = []
    override = os.environ.get("AIRIX_SIDECAR")
    if override:
        candidates.append(Path(override).expanduser())
    here = Path(__file__).resolve()
    candidates.extend(parent / SIDECAR_RELATIVE for parent in here.parents[:5])
    candidates.append(Path.cwd() / SIDECAR_RELATIVE)
    return candidates


def resolve_sidecar_script() -> Path:
    for candidate in _candidate_sidecar_paths():
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"No se encontró el sidecar Node ({SIDECAR_RELATIVE}). "
        "Verifica que exista `sidecar/extract_symbols.js` en la raíz del "
        "proyecto y que hayas corrido `npm install` dentro de `sidecar/`, "
        "o exporta AIRIX_SIDECAR con la ruta al script."
    )


def parse_ts_file(path: Path) -> dict:
    """Delega en un sidecar Node que usa ts-morph para extraer símbolos."""
    script = resolve_sidecar_script()
    if shutil.which("node") is None:
        raise FileNotFoundError(
            "No se encontró el ejecutable `node` en el PATH; el motor AST de "
            "TypeScript lo necesita para ejecutar el sidecar."
        )
    result = subprocess.run(
        ["node", str(script), str(path)],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        if "MODULE_NOT_FOUND" in detail or "ts-morph" in detail:
            detail += f"\n\nSugerencia: ejecuta `npm install` dentro de {script.parent}."
        raise RuntimeError(f"El sidecar falló analizando {path}: {detail}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"El sidecar devolvió una salida no-JSON para {path}: {result.stdout[:500]}"
        ) from exc
    # Formato esperado:
    # {
    #   "classes": [{"name": "...", "methods": [...]}],
    #   "interfaces": [...],
    #   "imports": ["./foo", "../lib/bar"],
    #   "exports": ["ClassName", "functionName"]
    # }
