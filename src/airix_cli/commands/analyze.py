# src/airix_cli/commands/analyze.py
from pathlib import Path

import typer
from rich.console import Console

from airix_cli.ast_engine.graph import cascade_reanalyze

console = Console()

SUPPORTED_EXTENSIONS = {".ts", ".tsx", ".py"}
IGNORED_DIRS = {".git", ".airix", ".tmp", "node_modules", ".venv", "__pycache__"}


def discover_analysis_targets(repo_root: Path, paths: list[str] | None = None) -> list[Path]:
    """Archivos candidatos a (re)analizar: los `paths` dados, o todo el repo si se omiten."""
    if paths:
        return [Path(p).resolve() for p in paths]
    return [
        f for f in repo_root.rglob("*")
        if f.is_file()
        and f.suffix in SUPPORTED_EXTENSIONS
        and not any(part in IGNORED_DIRS for part in f.relative_to(repo_root).parts)
    ]


def run_analysis(repo_root: Path, paths: list[str] | None = None) -> list[str]:
    """
    Núcleo del análisis AST, sin nada de Typer/consola: reutilizable tanto
    desde `airix analyze` como desde `/analyze` en el REPL. Deja propagar
    `FileNotFoundError`/`RuntimeError` (sidecar Node ausente, archivo Python
    con SyntaxError, etc.) para que cada llamador decida cómo reportarlo.
    """
    changed = discover_analysis_targets(repo_root, paths)
    if not changed:
        return []
    return cascade_reanalyze(changed)


def analyze(
    paths: list[str] = typer.Argument(
        None, help="Archivos específicos a reanalizar. Si se omite, escanea todo el repo."
    ),
) -> None:
    """Ejecuta el motor AST con caché diferencial e invalidación en cascada."""
    repo_root = Path.cwd()
    changed = discover_analysis_targets(repo_root, paths)

    if not changed:
        console.print(
            "[yellow]No se encontraron archivos para analizar "
            f"(extensiones soportadas: {', '.join(sorted(SUPPORTED_EXTENSIONS))}).[/yellow]"
        )
        raise typer.Exit()

    console.print(f"[dim]Analizando {len(changed)} archivo(s) candidato(s)...[/dim]")
    try:
        reanalyzed = cascade_reanalyze(changed)
    except (FileNotFoundError, RuntimeError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1) from None

    console.print(f"[bold green]✔ {len(reanalyzed)} módulo(s) reanalizado(s) (incluye cascada).[/bold green]")
    for f in reanalyzed:
        console.print(f"  - {f}")
