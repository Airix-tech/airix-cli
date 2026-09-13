# src/airix_cli/commands/rewind.py
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from airix_cli.staging.checkpoints import checkpoints_dir, rewind_to

console = Console()


def rewind(
    checkpoint: str = typer.Argument(
        None, help="Nombre del archivo de checkpoint a restaurar (ver --list)."
    ),
    list_checkpoints: bool = typer.Option(
        False, "--list", "-l", help="Lista los checkpoints disponibles y termina."
    ),
) -> None:
    """Restaura el repositorio a un checkpoint anterior (rewind instantáneo)."""
    repo_root = Path.cwd()
    cp_dir = checkpoints_dir(repo_root)

    if not cp_dir.exists() or not any(cp_dir.glob("*.tar.gz")):
        console.print("[yellow]No hay checkpoints registrados todavía.[/yellow]")
        raise typer.Exit()

    checkpoints = sorted(cp_dir.glob("*.tar.gz"), reverse=True)

    if list_checkpoints or checkpoint is None:
        table = Table(title="Checkpoints disponibles (más reciente primero)")
        table.add_column("#", justify="right")
        table.add_column("Archivo")
        for i, cp in enumerate(checkpoints):
            table.add_row(str(i), cp.name)
        console.print(table)
        if checkpoint is None:
            console.print("\n[dim]Uso: airix rewind <nombre_de_archivo.tar.gz>[/dim]")
        raise typer.Exit()

    target = cp_dir / checkpoint
    if not target.exists():
        console.print(f"[red]No se encontró el checkpoint: {checkpoint}[/red]")
        raise typer.Exit(code=1)

    confirmado = typer.confirm(
        f"¿Restaurar el repositorio al estado de '{checkpoint}'? "
        "Esto sobrescribe los archivos actuales que coincidan."
    )
    if not confirmado:
        raise typer.Exit()

    rewind_to(target, repo_root)
    console.print(f"[bold green]✔ Repositorio restaurado a {checkpoint}[/bold green]")