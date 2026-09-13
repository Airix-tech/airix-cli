# src/airix_cli/commands/compact.py
import typer
from airix_cli.context.compactor import compact_session, summarize_session


def compact_session_cmd() -> None:
    """
    Compacta la sesión actual, vuelca las decisiones clave a memory.json y
    borra el historial de instrucciones del REPL (repl_history).

    Usa el LLM activo para resumir (entiende el texto en vez de solo buscar
    palabras clave); si no está disponible, cae automáticamente a un resumen
    heurístico para no perder la compactación por eso.
    """
    compact_session(summarizer=summarize_session)
    typer.secho(
        "✔ Sesión compactada, decisiones clave volcadas a memory.json e historial del REPL reiniciado",
        fg=typer.colors.GREEN,
    )
