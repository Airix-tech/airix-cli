# src/airix_cli/commands/analyze.py
from pathlib import Path

import typer
from rich.console import Console

from airix_cli.ast_engine.graph import cascade_reanalyze

console = Console()

# Nota: parser.py hoy solo implementa parse_ts_file (vía ts-morph), así que
# el análisis está limitado a TypeScript/TSX hasta que se agregue un parser
# para otros lenguajes (ver sección 3 de la guía).
SUPPORTED_EXTENSIONS = {".ts", ".tsx"}
IGNORED_DIRS = {".git", ".airix", ".tmp", "node_modules", ".venv"}


def analyze(
    paths: list[str] = typer.Argument(
        None, help="Archivos específicos a reanalizar. Si se omite, escanea todo el repo."
    ),
) -> None:
    """Ejecuta el motor AST con caché diferencial e invalidación en cascada."""
    repo_root = Path.cwd()

    if paths:
        changed = [Path(p).resolve() for p in paths]
    else:
        changed = [
            f for f in repo_root.rglob("*")
            if f.is_file()
            and f.suffix in SUPPORTED_EXTENSIONS
            and not any(part in IGNORED_DIRS for part in f.relative_to(repo_root).parts)
        ]

    if not changed:
        console.print(
            "[yellow]No se encontraron archivos TypeScript para analizar "
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