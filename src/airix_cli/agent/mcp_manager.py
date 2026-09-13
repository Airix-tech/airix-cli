# src/airix_cli/agent/mcp_manager.py
"""
Cliente MCP (Model Context Protocol) para airix: conecta a servidores MCP
externos (declarados en `.airix/mcp_config.json`) vía stdio y expone sus
tools al agente.

El SDK oficial `mcp` es enteramente asíncrono, pero el resto del stack de
airix (REPL, `agent/client.py`) es síncrono. Para no pagar el costo de
levantar los subprocesos MCP en cada instrucción (los servidores suelen
arrancar con `npx`, que tarda 1-3s), `McpManager` corre un event loop propio
en un thread daemon que vive durante toda la sesión del REPL, y expone una
fachada síncrona (`list_tools`/`call_tool`) que reenvía al loop con
`asyncio.run_coroutine_threadsafe`.

`self._tools`/`self._errors` se escriben solo desde corutinas que corren en
el thread del manager y se leen desde el thread principal del REPL; al ser
asignaciones simples de dict (no mutaciones de varios pasos), esto es seguro
bajo el GIL de CPython sin necesidad de un lock — una simplificación
deliberada, no un descuido.
"""
import asyncio
import json
import threading
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

CONFIG_PATH = Path(".airix/mcp_config.json")
CALL_TOOL_TIMEOUT_SECONDS = 60
NAME_SEPARATOR = "__"


def _config_path(path: Path | None = None) -> Path:
    target = path or CONFIG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def load_mcp_config(path: Path | None = None) -> dict:
    target = _config_path(path)
    if not target.exists():
        return {"mcpServers": {}}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"mcpServers": {}}
    if not isinstance(data, dict) or not isinstance(data.get("mcpServers"), dict):
        return {"mcpServers": {}}
    return data


def save_mcp_config(config: dict, path: Path | None = None) -> dict:
    target = _config_path(path)
    target.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    return config


def add_server(
    name: str,
    command: str,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
    *,
    path: Path | None = None,
    overwrite: bool = False,
) -> dict:
    config = load_mcp_config(path)
    if name in config["mcpServers"] and not overwrite:
        raise ValueError(f"Ya existe un servidor MCP llamado '{name}'.")
    config["mcpServers"][name] = {
        "command": command,
        "args": args or [],
        "env": env or {},
    }
    return save_mcp_config(config, path)


def remove_server(name: str, *, path: Path | None = None) -> dict:
    config = load_mcp_config(path)
    if name not in config["mcpServers"]:
        raise ValueError(f"No hay un servidor MCP llamado '{name}'.")
    del config["mcpServers"][name]
    return save_mcp_config(config, path)


def list_servers(path: Path | None = None) -> dict[str, dict]:
    return load_mcp_config(path)["mcpServers"]


class McpManager:
    """Gestiona conexiones stdio a servidores MCP desde un thread propio."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._sessions: dict[str, ClientSession] = {}
        self._exit_stacks: dict[str, AsyncExitStack] = {}
        self._tools: dict[str, tuple[str, str, str, dict]] = {}  # qualified -> (server, real_name, description, schema)
        self._errors: dict[str, str] = {}

    def is_started(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def has_tools(self) -> bool:
        return bool(self._tools)

    def start(self) -> None:
        if self.is_started():
            return
        ready = threading.Event()

        def _run_loop() -> None:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            ready.set()
            self._loop.run_forever()

        self._thread = threading.Thread(target=_run_loop, daemon=True)
        self._thread.start()
        ready.wait(timeout=5)

    def connect_all_sync(self, config: dict | None = None) -> list[tuple[str, bool, str]]:
        """
        Conecta todos los servidores configurados. Devuelve una lista de
        (nombre, ok, detalle) para que el llamador (CLI/REPL) decida cómo
        mostrar el resultado; un servidor roto no impide que los demás se
        conecten.
        """
        if not self.is_started():
            self.start()
        cfg = config if config is not None else load_mcp_config()
        future = asyncio.run_coroutine_threadsafe(self._connect_all(cfg), self._loop)
        return future.result(timeout=30)

    async def _connect_all(self, config: dict) -> list[tuple[str, bool, str]]:
        servers = config.get("mcpServers", {})
        results = await asyncio.gather(
            *(self._connect_one(name, spec) for name, spec in servers.items()),
            return_exceptions=True,
        )
        report: list[tuple[str, bool, str]] = []
        for name, result in zip(servers.keys(), results, strict=True):
            if isinstance(result, Exception):
                self._errors[name] = str(result)
                report.append((name, False, str(result)))
            else:
                self._errors.pop(name, None)
                report.append((name, True, f"{result} tool(s)"))
        return report

    async def _connect_one(self, name: str, spec: dict) -> int:
        stack = AsyncExitStack()
        try:
            params = StdioServerParameters(
                command=spec["command"],
                args=spec.get("args", []),
                env=spec.get("env") or None,
            )
            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            result = await session.list_tools()
        except Exception:
            await stack.aclose()
            raise

        self._exit_stacks[name] = stack
        self._sessions[name] = session
        for tool in result.tools:
            qualified = f"{name}{NAME_SEPARATOR}{tool.name}"
            self._tools[qualified] = (name, tool.name, tool.description or "", tool.input_schema)
        return len(result.tools)

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "qualified_name": qualified,
                "server": server,
                "name": real_name,
                "description": description,
                "input_schema": schema,
            }
            for qualified, (server, real_name, description, schema) in self._tools.items()
        ]

    def status(self) -> dict[str, str]:
        """Un resumen por servidor conectado o fallido, para /mcp show."""
        connected = {server for server, _, _, _ in self._tools.values()}
        report = {name: "conectado" for name in connected}
        report.update({name: f"error: {detail}" for name, detail in self._errors.items()})
        return report

    def call_tool(self, qualified_name: str, arguments: dict) -> str:
        entry = self._tools.get(qualified_name)
        if entry is None:
            raise ValueError(f"Herramienta MCP desconocida: {qualified_name}")
        server_name, real_name, _, _ = entry
        if not self.is_started() or self._loop is None:
            raise RuntimeError("El gestor MCP no está iniciado.")
        future = asyncio.run_coroutine_threadsafe(
            self._call_tool_async(server_name, real_name, arguments), self._loop
        )
        return future.result(timeout=CALL_TOOL_TIMEOUT_SECONDS)

    async def _call_tool_async(self, server_name: str, real_name: str, arguments: dict) -> str:
        session = self._sessions[server_name]
        result = await session.call_tool(real_name, arguments)
        text = "\n".join(block.text for block in result.content if getattr(block, "type", None) == "text")
        if result.is_error:
            return f"[error de la herramienta] {text or 'sin detalle'}"
        return text

    def shutdown(self) -> None:
        if not self.is_started():
            return
        future = asyncio.run_coroutine_threadsafe(self._close_all(), self._loop)
        try:
            future.result(timeout=10)
        except Exception:
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)
        self._thread = None
        self._sessions.clear()
        self._exit_stacks.clear()
        self._tools.clear()
        self._errors.clear()

    async def _close_all(self) -> None:
        for stack in list(self._exit_stacks.values()):
            await stack.aclose()


_manager: McpManager | None = None


def get_mcp_manager() -> McpManager:
    global _manager
    if _manager is None:
        _manager = McpManager()
    return _manager
