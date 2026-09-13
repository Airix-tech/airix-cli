# src/airix_cli/commands/workspace.py
import tomllib
from datetime import datetime, timezone
from pathlib import Path

import tomli_w
import typer

app = typer.Typer()

WORKSPACE_MANIFEST = ".airix-workspace.toml"


@app.command("init")
def init_workspace(
    nombre: str,
    ruta: Path = typer.Option(
        None, "--path", help="Directorio donde crear el workspace (por defecto, el actual)."
    ),
):
    """Crea la estructura de un workspace multi-repo y su manifiesto TOML."""
    # `typer.Option(Path.cwd())` evaluaba el cwd al importar el módulo, no al
    # ejecutar el comando.
    root = (ruta or Path.cwd()) / nombre
    (root / "shared" / "memory").mkdir(parents=True, exist_ok=True)
    (root / "shared" / "prompts").mkdir(parents=True, exist_ok=True)
    (root / "repos").mkdir(parents=True, exist_ok=True)

    manifest = {
        "workspace": {"name": nombre, "created": _now_iso()},
        "repos": [],
    }
    with open(root / WORKSPACE_MANIFEST, "wb") as f:
        tomli_w.dump(manifest, f)

    typer.secho(f"✔ Workspace '{nombre}' creado en {root}", fg=typer.colors.GREEN)


@app.command("add")
def add_repo(
    ruta: Path = typer.Argument(..., help="Ruta al repositorio a registrar en el workspace."),
    workspace: Path = typer.Option(
        None, "--workspace", help=f"Raíz del workspace (donde está {WORKSPACE_MANIFEST})."
    ),
):
    """Registra un repositorio existente dentro de un workspace ya inicializado."""
    workspace = workspace or Path.cwd()
    manifest_path = workspace / WORKSPACE_MANIFEST
    if not manifest_path.exists():
        typer.secho(
            f"No se encontró {WORKSPACE_MANIFEST} en {workspace}. "
            "¿Es la raíz del workspace? Usa --workspace para indicarla.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    if not ruta.exists():
        typer.secho(f"La ruta '{ruta}' no existe.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    with open(manifest_path, "rb") as f:
        manifest = tomllib.load(f)

    repo_path = str(ruta.resolve())
    repos = manifest.setdefault("repos", [])
    if repo_path in repos:
        typer.secho(f"'{repo_path}' ya estaba registrado en el workspace.", fg=typer.colors.YELLOW)
        raise typer.Exit()

    repos.append(repo_path)
    with open(manifest_path, "wb") as f:
        tomli_w.dump(manifest, f)

    typer.secho(f"✔ '{repo_path}' agregado al workspace.", fg=typer.colors.GREEN)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()