# src/airix_cli/commands/compact.py
import typer
from airix_cli.context.compactor import compact_session


def compact_session_cmd() -> None:
    """Compacta la sesión actual y vuelca las decisiones clave a memory.json."""
    compact_session()
    typer.secho("✔ Sesión compactada y decisiones clave volcadas a memory.json", fg=typer.colors.GREEN)
