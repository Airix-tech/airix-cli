# src/airix_cli/repl/console.py
import difflib
import shutil
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.syntax import Syntax
from rich.prompt import Prompt
from rich.panel import Panel
from rich.table import Table

from airix_cli.memory.schema import TechnicalDecision
from airix_cli.memory.store import append_decision
from airix_cli.staging.checkpoints import create_checkpoint
from airix_cli.staging import fswriter
from airix_cli.staging.fswriter import clear_staging
from airix_cli.staging.git_review import GitReviewError, stage_for_visual_review

console = Console(highlight=False)


def print_banner(test_command: str | None) -> None:
    details = "Agente local · memoria persistente · revisión controlada"
    if test_command:
        details += f"\nTests: [bold]{test_command}[/bold]"
    console.print(Panel.fit(
        f"[bold bright_white]AIRIX[/bold bright_white] [dim]coding workspace[/dim]\n"
        f"[cyan]{details}[/cyan]",
        border_style="bright_cyan",
        padding=(1, 3),
    ))


def print_status(message: str, *, style: str = "green", icon: str = "✔") -> None:
    console.print(f"[{style}]{icon}[/] {message}")


def print_help() -> None:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Comando", style="bright_cyan", no_wrap=True)
    table.add_column("Acción", style="white")
    table.add_row("/help", "Muestra esta ayuda")
    table.add_row("/llm show", "Muestra el proveedor/modelo activo")
    table.add_row("/llm list <provider>", "Lista modelos disponibles del proveedor")
    table.add_row("/llm set <provider> <model>", "Guarda la configuración del LLM")
    table.add_row("/review", "Ejecuta tests y revisa los cambios de .tmp/")
    table.add_row("/compact", "Fuerza la compactación del historial")
    table.add_row("/salir", "Cierra la sesión")
    table.add_row("<instrucción>", "Envía una tarea al agente")
    console.print(Panel(table, title="[bold]Comandos[/bold]", border_style="blue", expand=False))


def _staged_relative_path(tmp_file: Path) -> Path:
    """Ruta del archivo staged relativa al directorio de staging activo."""
    return tmp_file.resolve().relative_to(fswriter.TMP_DIR.resolve())


def show_diff(original: Path, proposed: Path) -> None:
    old_lines = original.read_text(encoding="utf-8").splitlines() if original.exists() else []
    new_lines = proposed.read_text(encoding="utf-8").splitlines()
    diff = difflib.unified_diff(old_lines, new_lines, lineterm="",
                                 fromfile=str(original), tofile=str(proposed))
    console.print(Panel(
        Syntax("\n".join(diff), "diff", theme="ansi_dark", word_wrap=False),
        title=f"[bold cyan]{original}[/bold cyan]",
        border_style="dim",
        padding=(0, 1),
    ))


def approval_repl(staged_files: list[Path], repo_root: Path) -> dict[Path, bool]:
    """
    Pide una decisión por archivo. `todo` aprueba los archivos PENDIENTES (no
    revierte un `no` ya dado); `salir` rechaza los pendientes y corta la revisión.
    """
    decisions: dict[Path, bool] = {}
    console.rule("[bold bright_green]REVISIÓN DE CAMBIOS[/bold bright_green]")
    console.print(f"[dim]{len(staged_files)} archivo(s) preparado(s) para revisar[/dim]\n")

    for index, tmp_file in enumerate(staged_files, start=1):
        rel = _staged_relative_path(tmp_file)
        real_file = repo_root / rel
        console.print(f"[bold blue]{index:02d}[/bold blue] [bold]{rel}[/bold]")
        show_diff(real_file, tmp_file)

        choice = Prompt.ask(
            "  Decisión",
            choices=["si", "no", "todo", "salir"],
            default="si",
        )
        pending = staged_files[index - 1:]
        if choice == "todo":
            decisions.update({f: True for f in pending})
            break
        if choice == "salir":
            decisions.update({f: False for f in pending})
            break
        decisions[tmp_file] = (choice == "si")

    return decisions


def consolidate(decisions: dict[Path, bool], repo_root: Path, rationale: str) -> None:
    approved = [f for f, ok in decisions.items() if ok]
    if not approved:
        print_status("Ningún cambio aprobado. Descartando .tmp/.", style="yellow", icon="!")
        clear_staging()
        return

    create_checkpoint(repo_root, label="pre-consolidacion")

    repo_root = repo_root.resolve()
    affected: list[str] = []
    destinations: list[Path] = []
    for tmp_file in approved:
        rel = _staged_relative_path(tmp_file)
        dest = (repo_root / rel).resolve()
        # Defensa en profundidad: fswriter ya rechaza rutas que escapan del
        # staging, pero nunca escribimos fuera de la raíz del repositorio.
        if repo_root not in dest.parents:
            print_status(f"Omitido (fuera del repositorio): {rel}", style="red", icon="✗")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(tmp_file, dest)
        destinations.append(dest)
        affected.append(rel.as_posix())

    if not destinations:
        clear_staging()
        return

    try:
        stage_for_visual_review(repo_root, destinations)
    except GitReviewError as exc:
        print_status(f"No se pudieron preparar los cambios en VS Code: {exc}", style="yellow", icon="!")
    else:
        console.print(Panel(
            "[white]Los cambios aparecen en [/][bold bright_cyan]Staged Changes[/bold bright_cyan].\n"
            "[dim]Solo se modifica el índice local. No se crea commit ni se usa ningún remoto.[/dim]",
            title="[bold green]REVISIÓN LISTA[/bold green]",
            border_style="green",
            expand=False,
        ))

    append_decision(
        repo_root / ".airix/memory.json",
        TechnicalDecision(
            timestamp=datetime.now(timezone.utc),
            summary="Consolidación de cambios aprobados vía REPL",
            rationale=rationale,
            affected_files=affected,
        ),
    )

    clear_staging()
    print_status(f"{len(destinations)} archivo(s) consolidados.")
