# src/airix_cli/ast_engine/parser.py
import ast
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


def _python_import_specs(node: ast.ImportFrom) -> list[str]:
    """
    Normaliza un `from X import Y` a specs resolubles por el grafo de
    dependencias, con la misma forma que usan los imports de TS (una cadena
    por potencial módulo referenciado).

    Absolutos (level 0): solo el módulo (p. ej. "airix_cli.ast_engine.cache"),
    sin expandir por nombre — en el estilo de este proyecto casi siempre se
    importa ya desde el submódulo exacto, así que expandir agregaría ruido
    (falsos "módulos" que en realidad son funciones/clases).

    Relativos (level > 0): además del módulo base, se agrega una variante por
    nombre importado ("from .pkg import foo" -> ".pkg" y ".pkg.foo"), porque
    en relativos es común importar submódulos directamente ("from . import
    foo" donde foo.py vive al lado). Un spec que no resuelve a archivo
    simplemente se descarta en `_resolve_python_import`.
    """
    dots = "." * node.level
    base = f"{dots}{node.module}" if node.module else dots
    if node.level == 0:
        return [base]

    specs = [base]
    joiner = "" if base.endswith(".") else "."
    for alias in node.names:
        if alias.name == "*":
            continue
        specs.append(f"{base}{joiner}{alias.name}")
    return specs


def _extract_dunder_all(tree: ast.Module) -> list[str] | None:
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
            continue
        if isinstance(node.value, (ast.List, ast.Tuple)):
            return [elt.value for elt in node.value.elts if isinstance(elt, ast.Constant) and isinstance(elt.value, str)]
    return None


def parse_python_file(path: Path) -> dict:
    """
    Extrae símbolos de un archivo Python con el módulo `ast` de la stdlib
    (sin sidecar externo, a diferencia de TS/ts-morph).
    """
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        raise RuntimeError(f"No se pudo parsear {path}: {exc}") from exc

    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.extend(_python_import_specs(node))

    classes: list[dict] = []
    exports: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            classes.append({
                "name": node.name,
                "methods": [
                    {
                        "name": item.name,
                        "params": [a.arg for a in item.args.args if a.arg != "self"],
                        "returnType": ast.unparse(item.returns) if item.returns else "",
                    }
                    for item in node.body
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                ],
            })
            exports.append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            exports.append(node.name)

    dunder_all = _extract_dunder_all(tree)
    if dunder_all is not None:
        exports = dunder_all

    return {
        "classes": classes,
        "interfaces": [],
        "imports": sorted(set(imports)),
        "exports": exports,
    }
