# src/airix_cli/cli.py
import typer
from airix_cli.commands import workspace, init, compact, run, rewind, analyze, llm, mcp

app = typer.Typer(
    name="airix",
    help="Agente de codificación con memoria persistente y motor AST incremental.",
    no_args_is_help=True,
)

app.add_typer(workspace.app, name="workspace", help="Gestión del contenedor multi-repo")
app.add_typer(llm.app, name="llm", help="Configuración del proveedor y modelo del asistente")
app.add_typer(mcp.app, name="mcp", help="Gestión de servidores MCP (Model Context Protocol)")
app.command("init")(init.init_repo)
app.command("compact")(compact.compact_session_cmd)
app.command("run")(run.start_repl)
app.command("rewind")(rewind.rewind)
app.command("analyze")(analyze.analyze)

if __name__ == "__main__":
    app()