# src/airix_cli/commands/run.py
import re
import shlex
from pathlib import Path

import typer
from rich.panel import Panel
from rich.prompt import Prompt

from airix_cli.memory.store import load_memory
from airix_cli.context.compactor import load_session, save_session, should_compact, compact_session
from airix_cli.staging.test_runner import run_tests_against_staging
from airix_cli.staging import fswriter
from airix_cli.staging.fswriter import PartialWriteError, UnsafePathError, stage_file
from airix_cli.repl.console import (
    console,
    approval_repl,
    consolidate,
    print_banner,
    print_help,
    print_status,
)
from airix_cli.agent.client import (
    answer_question,
    get_available_models,
    get_active_model_config,
    load_model_config,
    propose_changes,
    set_model_config,
)
from airix_cli.agent.intent import is_change_request
from airix_cli.context.workspace import build_workspace_context

MEMORY_PATH = Path(".airix/memory.json")
AGENT_MD_PATH = Path("AGENT.md")


def bootstrap_context() -> str:
    """Devuelve un resumen textual inyectable al prompt del sistema del agente."""
    mem = load_memory(MEMORY_PATH)
    lines = ["## Contexto recuperado de memory.json"]
    if mem.profile.language:
        lines.append(f"- Lenguaje/framework: {mem.profile.language} / {', '.join(mem.profile.frameworks)}")
    if mem.profile.detected_patterns:
        lines.append(f"- Patrones detectados: {', '.join(mem.profile.detected_patterns)}")
    for d in mem.decisions[-10:]:
        lines.append(f"- Decisión ({d.timestamp.date()}): {d.summary}")
    for e in mem.resolved_errors[-10:]:
        lines.append(f"- Error resuelto: {e.error_signature} → causa: {e.root_cause}")
    return "\n".join(lines)


def _staged_files() -> list[Path]:
    return fswriter.staged_files()


def _requested_workspace_paths(instruction: str) -> list[str]:
    """Extrae nombres de archivo mencionados para priorizarlos en el contexto."""
    return re.findall(r"(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.[A-Za-z0-9]+", instruction)


def _dispatch_to_agent(instruction: str, repo_root: Path) -> str | None:
    """
    Envía la instrucción del usuario al agente LLM. Las consultas (analizar,
    revisar, explicar) se responden directamente en el CLI; solo las peticiones
    de cambio escriben propuestas en `.tmp/`. Devuelve el texto de respuesta del
    agente (o None si falló), para que el REPL pueda persistirlo en la sesión.
    """
    governance = AGENT_MD_PATH.read_text(encoding="utf-8") if AGENT_MD_PATH.exists() else ""
    memory_context = bootstrap_context()
    workspace_context = build_workspace_context(
        repo_root,
        focus_paths=_requested_workspace_paths(instruction),
    )

    change_request = is_change_request(instruction)
    mode = "cambios (propuestas en .tmp/)" if change_request else "consulta (respuesta en el CLI)"
    console.print(Panel.fit(
        f"[bold]Procesando instrucción[/bold]\n[dim]Modo {mode} · consultando al agente...[/dim]",
        border_style="blue",
    ))

    if not change_request:
        # Streaming: cada fragmento se imprime en cuanto llega en vez de
        # esperar a que el modelo termine toda la respuesta. Con un LLM local
        # esto no acorta el tiempo total, pero el usuario ve texto moviéndose
        # de inmediato en lugar de mirar el spinner varios segundos/minutos.
        # markup=False/highlight=False evitan que un fragmento cortado a mitad
        # de una secuencia como "[algo]" se interprete como marcado de rich.
        received: list[str] = []

        def _on_chunk(chunk: str) -> None:
            received.append(chunk)
            console.print(chunk, end="", markup=False, highlight=False)

        try:
            answer = answer_question(
                instruction, governance, memory_context, workspace_context, on_chunk=_on_chunk
            )
        except Exception as e:
            if received:
                console.print()  # cierra la línea de streaming antes del error
            print_status(f"Error consultando al agente: {e}", style="red", icon="✗")
            return None

        if received:
            console.print()  # línea en blanco de cierre tras el streaming
        else:
            console.print("[yellow]El agente devolvió una respuesta vacía.[/yellow]")
        return answer

    try:
        result = propose_changes(instruction, governance, memory_context, workspace_context)
    except Exception as e:
        print_status(f"Error consultando al agente: {e}", style="red", icon="✗")
        return None

    files = result.get("files") or []
    rationale = result.get("rationale", "")

    if not files:
        if rationale:
            console.print(rationale)
        else:
            console.print("[yellow]El agente no propuso cambios de archivo.[/yellow]")
        return rationale

    written = 0
    for f in files:
        try:
            stage_file(f["path"], f["content"])
            written += 1
        except PartialWriteError as e:
            print_status(f"Rechazado ({f.get('path')}): {e}", style="red", icon="✗")
        except UnsafePathError as e:
            print_status(f"Rechazado ({f.get('path')}): {e}", style="red", icon="✗")
        except (KeyError, TypeError):
            print_status(f"Propuesta inválida del agente (falta 'path' o 'content'): {f}", style="red", icon="✗")

    if rationale:
        console.print(f"[dim]{rationale}[/dim]")
    if written:
        print_status(f"{written} archivo(s) preparados en .tmp/. Usa /review para revisarlos.")
    return rationale


def _review_staged_changes(repo_root: Path, test_command: list[str] | None) -> None:
    """Corre el flujo completo: tests contra .tmp/ -> REPL de aprobación -> consolidación."""
    staged = _staged_files()
    if not staged:
        print_status("No hay archivos en .tmp/ para revisar.", style="yellow", icon="!")
        return

    if test_command:
        console.print(f"[dim]Ejecutando: {' '.join(test_command)}[/dim]")
        result = run_tests_against_staging(repo_root, fswriter.TMP_DIR, test_command)
        if result.returncode != 0:
            console.print(Panel(
                (result.stdout or "") + (f"\n{result.stderr}" if result.stderr else ""),
                title="[bold red]TESTS FALLIDOS[/bold red]",
                border_style="red",
            ))
            return
        print_status("Tests superados.")
    else:
        print_status("No hay comando de tests configurado; se omite la validación.", style="yellow", icon="!")

    decisions = approval_repl(staged, repo_root)
    if not any(decisions.values()):
        console.print("[yellow]No se aprobó ningún cambio.[/yellow]")
        consolidate(decisions, repo_root, "")
        return

    rationale = Prompt.ask("Justificación técnica de estos cambios (para memory.json)", default="")
    consolidate(decisions, repo_root, rationale)


def normalize_repl_command(user_input: str) -> str:
    text = user_input.strip()
    if text.startswith("/"):
        return text[1:].strip()
    return ""


def get_repl_completion_candidates(incomplete: str) -> list[str]:
    """Devuelve sugerencias de autocompletado para el REPL con prefijo /."""
    prefix = (incomplete or "").strip()
    command_candidates = [
        "/help",
        "/llm",
        "/review",
        "/compact",
        "/salir",
    ]

    if not prefix:
        return command_candidates

    if not prefix.startswith("/"):
        return []

    normalized = prefix[1:].strip()
    if not normalized:
        return command_candidates

    suggestions = []
    if "llm".startswith(normalized):
        suggestions.extend(["/llm show", "/llm list", "/llm set"])

    for command in ["/help", "/review", "/compact", "/salir"]:
        if command.startswith(prefix):
            suggestions.append(command)

    if normalized in {"help", "review", "compact", "salir"}:
        suggestions.append(f"/{normalized}")

    return sorted(set(suggestions))


def handle_llm_command(user_input: str) -> bool:
    """Procesa comandos llm dentro del REPL y devuelve True si fueron consumidos."""
    text = normalize_repl_command(user_input)
    if not text:
        return False
    parts = text.split()
    if not parts or parts[0] != "llm":
        return False

    if len(parts) == 1:
        config = load_model_config()
        typer.secho(f"Proveedor: {config['provider']}", fg=typer.colors.CYAN)
        typer.secho(f"Modelo: {config['model']}", fg=typer.colors.CYAN)
        return True

    subcommand = parts[1]

    if subcommand == "show":
        config = load_model_config()
        typer.secho(f"Proveedor: {config['provider']}", fg=typer.colors.CYAN)
        typer.secho(f"Modelo: {config['model']}", fg=typer.colors.CYAN)
        return True

    if subcommand == "list":
        provider = parts[2] if len(parts) > 2 else "gemini"
        models = get_available_models(provider)
        typer.secho(f"Modelos para {provider}:", fg=typer.colors.GREEN)
        for model in models:
            typer.echo(f"- {model}")
        return True

    if subcommand == "set":
        if len(parts) < 3:
            typer.secho("Uso: llm set <provider> <model>", fg=typer.colors.RED)
            return True
        provider = parts[2]
        model = parts[3] if len(parts) > 3 else None
        try:
            config = set_model_config(provider, model)
        except ValueError as exc:
            typer.secho(f"Error: {exc}", fg=typer.colors.RED)
            return True
        typer.secho(f"Configuración guardada: {config['provider']} / {config['model']}", fg=typer.colors.GREEN)
        return True

    typer.secho("Comandos LLM disponibles: show | list <provider> | set <provider> <model>", fg=typer.colors.YELLOW)
    return True


def start_repl(
    test_cmd: str = typer.Option(
        None,
        "--test-cmd",
        help='Comando para correr la suite de tests, ej: "pytest -q". '
             'Si se omite, se usa el detectado/guardado en memory.json durante `airix init`.',
    ),
    provider: str = typer.Option(
        None,
        "--provider",
        help="Proveedor LLM activo (gemini | ollama). Si se omite, usa el configurado.",
    ),
    model: str = typer.Option(
        None,
        "--model",
        help="Modelo específico del proveedor. Si se omite, usa el configurado en `.airix/llm_config.json`.",
    ),
) -> None:
    """Inicia el REPL interactivo: carga memoria, conecta al agente y permite revisar/aprobar .tmp/."""
    try:
        # Sin --provider explícito se respeta el proveedor ya configurado: antes
        # un `--model qwen...` sobre una config de ollama se reinterpretaba como
        # `gemini/qwen...` y fallaba la validación.
        if provider or model:
            effective_provider = provider or get_active_model_config()["provider"]
            set_model_config(effective_provider, model)
    except ValueError as exc:
        typer.secho(f"No se pudo configurar el modelo: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from None

    repo_root = Path.cwd()
    mem = load_memory(MEMORY_PATH)
    resolved_test_cmd = test_cmd or mem.profile.test_command
    test_command = shlex.split(resolved_test_cmd) if resolved_test_cmd else None

    print_banner(resolved_test_cmd)
    console.print(Panel(
        bootstrap_context(),
        title="[bold]CONTEXTO ACTIVO[/bold]",
        border_style="dim",
        expand=False,
    ))
    console.print("[dim]Escribe una instrucción o usa [cyan]/help[/cyan] para ver los comandos.[/dim]\n")

    while True:
        # Compactación dinámica al alcanzar el umbral crítico de tokens,
        # evaluada en cada vuelta del loop antes de aceptar el siguiente turno.
        messages = load_session()
        if should_compact(messages):
            compact_session(memory_path=MEMORY_PATH)
            # compact_session reescribe session.json: recargar para no volver a
            # guardar encima el historial ya compactado.
            messages = load_session()
            print_status("Contexto compactado automáticamente.", style="dim", icon="↻")

        user_input = Prompt.ask("[bold]airix>[/bold]").strip()
        if not user_input:
            continue

        command = normalize_repl_command(user_input)

        if command in ("salir", "exit", "quit"):
            break

        if command == "help":
            print_help()
            continue

        if command and handle_llm_command(user_input):
            continue

        # Toda entrada que llega al agente (y solo esa) se registra en la
        # sesión. Antes únicamente se guardaban los comandos con "/", así que
        # el historial quedaba vacío y la compactación automática nunca se
        # disparaba pese a evaluarse en cada vuelta.
        if command == "review":
            _review_staged_changes(repo_root, test_command)
            continue
        if command == "compact":
            compact_session(memory_path=MEMORY_PATH)
            print_status("Contexto compactado manualmente.", icon="↻")
            continue
        if command:
            print_status(f"Comando desconocido: /{command}. Usa /help.", style="yellow", icon="!")
            continue

        messages.append({"role": "user", "content": user_input})
        save_session(messages)
        answer = _dispatch_to_agent(user_input, repo_root)
        if answer:
            messages.append({"role": "assistant", "content": answer})
            save_session(messages)
