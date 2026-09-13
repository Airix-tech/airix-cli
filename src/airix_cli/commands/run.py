# src/airix_cli/commands/run.py
import atexit
import re
import shlex
from pathlib import Path

import typer
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import merge_completers
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from rich.panel import Panel
from rich.prompt import Prompt

from airix_cli.memory.store import load_memory
from airix_cli.context.compactor import (
    load_session,
    save_session,
    should_compact,
    compact_session,
    summarize_session,
)
from airix_cli.staging.test_runner import run_tests_against_staging
from airix_cli.staging import fswriter
from airix_cli.staging.fswriter import PartialWriteError, UnsafePathError, stage_file
from airix_cli.repl.completion import ReferenceCompleter, SlashCommandCompleter
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
from airix_cli.agent.mcp_manager import add_server, get_mcp_manager, load_mcp_config, remove_server
from airix_cli.context.references import parse_references, resolve_reference
from airix_cli.context.workspace import build_workspace_context

MEMORY_PATH = Path(".airix/memory.json")
AGENT_MD_PATH = Path("AGENT.md")
REPL_HISTORY_PATH = Path(".airix/repl_history")


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
    """Extrae nombres de archivo mencionados sueltos (sin @) para priorizarlos en el contexto."""
    return re.findall(r"(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.[A-Za-z0-9]+", instruction)


def _context_for_instruction(
    instruction: str, repo_root: Path, *, change_request: bool
) -> tuple[str, str, list[str]]:
    """
    Decide cuánto del repositorio se manda al agente, según la instrucción:

    - `@proyecto`, `@all`, `@workspace`... (o un `@` suelto) -> el repo completo,
      igual que antes de existir referencias explícitas.
    - `@archivo.py`, o simplemente mencionar "archivo.py" sin @ -> solo ese
      archivo, en vez de todo el repositorio.
    - nada de lo anterior en una consulta (analizar/revisar/preguntar) -> sin
      contenido de archivos: evita pagar el escaneo completo del workspace
      (varios segundos con un LLM local) para un simple "hola, cómo estás".
    - nada de lo anterior en un pedido de cambio -> el repo completo, como
      antes: sin un archivo puntual el agente necesita ver el proyecto para
      ubicar dónde aplicar el cambio.

    Devuelve (contexto, descripción para el panel, referencias @ no encontradas).
    """
    refs = parse_references(instruction, repo_root)
    files = list(refs.files)
    for name in _requested_workspace_paths(instruction):
        resolved = resolve_reference(name, repo_root)
        matches = [resolved] if isinstance(resolved, str) else (resolved or [])
        files.extend(path for path in matches if path not in files)

    if refs.whole_project:
        return build_workspace_context(repo_root, focus_paths=files), "proyecto completo", refs.unresolved
    if files:
        context = build_workspace_context(repo_root, only_paths=files)
        return context, f"archivo(s): {', '.join(files)}", refs.unresolved
    if change_request:
        return build_workspace_context(repo_root), "proyecto completo (sin @, se asume necesario)", refs.unresolved
    return "", "sin archivos (usa @archivo.py o @proyecto para incluir código)", refs.unresolved


def _dispatch_to_agent(instruction: str, repo_root: Path) -> str | None:
    """
    Envía la instrucción del usuario al agente LLM. Las consultas (analizar,
    revisar, explicar) se responden directamente en el CLI; solo las peticiones
    de cambio escriben propuestas en `.tmp/`. Devuelve el texto de respuesta del
    agente (o None si falló), para que el REPL pueda persistirlo en la sesión.
    """
    governance = AGENT_MD_PATH.read_text(encoding="utf-8") if AGENT_MD_PATH.exists() else ""
    memory_context = bootstrap_context()
    change_request = is_change_request(instruction)
    workspace_context, context_note, unresolved = _context_for_instruction(
        instruction, repo_root, change_request=change_request
    )

    if unresolved:
        refs_list = ", ".join(f"@{u}" for u in unresolved)
        print_status(f"No se encontró {refs_list} en el repositorio.", style="yellow", icon="!")

    mode = "cambios (propuestas en .tmp/)" if change_request else "consulta (respuesta en el CLI)"
    console.print(Panel.fit(
        f"[bold]Procesando instrucción[/bold]\n[dim]Modo {mode} · contexto: {context_note} · "
        "consultando al agente...[/dim]",
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

        def _on_status(message: str) -> None:
            print_status(message, style="dim", icon="🔧")

        try:
            answer = answer_question(
                instruction, governance, memory_context, workspace_context,
                on_chunk=_on_chunk, on_status=_on_status,
            )
        except Exception as e:
            if received:
                console.print()  # cierra la línea de streaming antes del error
            print_status(f"Error consultando al agente: {e}", style="red", icon="✗")
            return None

        if received:
            console.print()  # línea en blanco de cierre tras el streaming
        elif answer:
            # Path de tool-calling MCP (Fase C): no hay streaming ahí, así que
            # la respuesta completa recién se conoce al terminar y se imprime
            # de una sola vez.
            console.print(answer)
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


def _read_repl_input(session: PromptSession) -> str:
    """
    Lee la siguiente línea del REPL con autocompletado de referencias `@` y de
    comandos `/`. Deja propagar `KeyboardInterrupt` (Ctrl+C) y `EOFError`
    (Ctrl+D): el loop en `start_repl` decide qué hacer con cada una.

    Aislado en su propia función para que los tests puedan sustituirla sin
    depender de `prompt_toolkit` (que necesita una terminal real para el menú
    de sugerencias en vivo).
    """
    return session.prompt(HTML("<b>airix&gt;</b> ")).strip()


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
        "/mcp",
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
    if "mcp".startswith(normalized):
        suggestions.extend(["/mcp show", "/mcp list", "/mcp tools", "/mcp add", "/mcp remove", "/mcp reload"])

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


def _connect_configured_mcp_servers() -> None:
    """
    Conecta los servidores MCP configurados, una sola vez (costo ~1-3s por
    servidor `npx`), no en cada instrucción. Un servidor roto se reporta y no
    impide que los demás queden disponibles.
    """
    manager = get_mcp_manager()
    manager.start()
    for name, ok, detail in manager.connect_all_sync():
        if ok:
            print_status(f"MCP '{name}' conectado ({detail}).", style="dim", icon="🔌")
        else:
            print_status(f"MCP '{name}' no se pudo conectar: {detail}", style="yellow", icon="!")


def handle_mcp_command(user_input: str) -> bool:
    """Procesa comandos /mcp dentro del REPL y devuelve True si fueron consumidos."""
    text = normalize_repl_command(user_input)
    if not text:
        return False
    parts = text.split()
    if not parts or parts[0] != "mcp":
        return False

    manager = get_mcp_manager()
    subcommand = parts[1] if len(parts) > 1 else "show"

    if subcommand in ("show", "list"):
        servers = load_mcp_config().get("mcpServers", {})
        if not servers:
            typer.secho("No hay servidores MCP configurados. Usa /mcp add.", fg=typer.colors.YELLOW)
            return True
        status = manager.status() if manager.is_started() else {}
        for name, spec in servers.items():
            state = status.get(name, "no conectado")
            typer.secho(f"- {name} ({spec['command']}): {state}", fg=typer.colors.CYAN)
        return True

    if subcommand == "tools":
        if not manager.is_started() or not manager.has_tools():
            _connect_configured_mcp_servers()
        tools = manager.list_tools()
        if not tools:
            typer.secho("No hay herramientas MCP disponibles.", fg=typer.colors.YELLOW)
            return True
        for t in tools:
            typer.echo(f"- {t['qualified_name']}: {t['description']}")
        return True

    if subcommand == "add":
        if len(parts) < 4:
            typer.secho("Uso: /mcp add <nombre> <comando> [args...] [--env=VAR=valor ...]", fg=typer.colors.RED)
            return True
        name, command, *rest = parts[2:]
        env: dict[str, str] = {}
        args: list[str] = []
        for token in rest:
            if token.startswith("--env="):
                k, v = token[len("--env="):].split("=", 1)
                env[k] = v
            else:
                args.append(token)
        try:
            add_server(name, command, args, env)
        except ValueError as exc:
            typer.secho(f"Error: {exc}", fg=typer.colors.RED)
            return True
        typer.secho(f"Servidor MCP '{name}' agregado. Usa /mcp reload para conectarlo.", fg=typer.colors.GREEN)
        return True

    if subcommand == "remove":
        if len(parts) < 3:
            typer.secho("Uso: /mcp remove <nombre>", fg=typer.colors.RED)
            return True
        try:
            remove_server(parts[2])
        except ValueError as exc:
            typer.secho(f"Error: {exc}", fg=typer.colors.RED)
            return True
        typer.secho(f"Servidor MCP '{parts[2]}' eliminado.", fg=typer.colors.GREEN)
        return True

    if subcommand == "reload":
        manager.shutdown()
        _connect_configured_mcp_servers()
        typer.secho("Servidores MCP recargados.", fg=typer.colors.GREEN)
        return True

    typer.secho("Comandos MCP disponibles: show | list | tools | add | remove | reload", fg=typer.colors.YELLOW)
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
    console.print(
        "[dim]Escribe una instrucción o usa [cyan]/help[/cyan] para ver los comandos. "
        "Escribe [cyan]@[/cyan] para referenciar un archivo o [cyan]@proyecto[/cyan] para todo el repo. "
        "Flecha arriba recupera comandos de sesiones anteriores.[/dim]\n"
    )

    # Los servidores MCP configurados se conectan una sola vez al arrancar el
    # REPL (no en cada instrucción): levantar un subproceso `npx` tarda
    # 1-3s, y pagar ese costo por turno haría que cualquier consulta con
    # tools se sintiera lenta. Solo tiene sentido si el proveedor activo
    # soporta tool-calling (Ollama queda fuera en esta iteración).
    if load_mcp_config().get("mcpServers") and get_active_model_config()["provider"] in ("gemini", "anthropic"):
        manager = get_mcp_manager()
        atexit.register(manager.shutdown)
        _connect_configured_mcp_servers()

    REPL_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    session: PromptSession = PromptSession(
        completer=merge_completers([
            ReferenceCompleter(repo_root),
            SlashCommandCompleter(get_repl_completion_candidates),
        ]),
        complete_while_typing=True,
        history=FileHistory(str(REPL_HISTORY_PATH)),
    )

    while True:
        # Compactación dinámica al alcanzar el umbral crítico de tokens,
        # evaluada en cada vuelta del loop antes de aceptar el siguiente turno.
        messages = load_session()
        if should_compact(messages):
            compact_session(memory_path=MEMORY_PATH, summarizer=summarize_session)
            # compact_session reescribe session.json: recargar para no volver a
            # guardar encima el historial ya compactado.
            messages = load_session()
            # compact_session también borra el archivo de repl_history; el
            # PromptSession ya cacheó las entradas viejas en memoria, así que
            # hay que darle un History nuevo para que ↑/↓ y Ctrl+R dejen de
            # mostrarlas dentro de esta misma sesión.
            session.history = FileHistory(str(REPL_HISTORY_PATH))
            print_status("Contexto compactado automáticamente.", style="dim", icon="↻")

        try:
            user_input = _read_repl_input(session)
        except KeyboardInterrupt:
            # Ctrl+C: cancela la línea actual sin cerrar la sesión, como en la
            # mayoría de REPLs (bash, python -i). Antes esto no se capturaba y
            # tiraba un traceback crudo a la terminal.
            console.print("[dim](Ctrl+C) Instrucción cancelada. Escribe /salir para salir.[/dim]")
            continue
        except EOFError:
            # Ctrl+D en una línea vacía: salida silenciosa, igual que bash.
            console.print()
            break

        if not user_input:
            continue

        command = normalize_repl_command(user_input)

        if command in ("salir", "exit", "quit"):
            break

        if command == "help":
            print_help()
            continue

        if command and (handle_llm_command(user_input) or handle_mcp_command(user_input)):
            continue

        # Toda entrada que llega al agente (y solo esa) se registra en la
        # sesión. Antes únicamente se guardaban los comandos con "/", así que
        # el historial quedaba vacío y la compactación automática nunca se
        # disparaba pese a evaluarse en cada vuelta.
        if command == "review":
            _review_staged_changes(repo_root, test_command)
            continue
        if command == "compact":
            compact_session(memory_path=MEMORY_PATH, summarizer=summarize_session)
            session.history = FileHistory(str(REPL_HISTORY_PATH))
            print_status("Contexto compactado manualmente e historial del REPL reiniciado.", icon="↻")
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
