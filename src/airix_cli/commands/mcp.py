import typer

from airix_cli.agent.mcp_manager import add_server, list_servers, remove_server

app = typer.Typer()


@app.command("list")
def list_servers_cmd() -> None:
    servers = list_servers()
    if not servers:
        typer.secho("No hay servidores MCP configurados. Usa `airix mcp add`.", fg=typer.colors.YELLOW)
        return
    typer.secho("Servidores MCP configurados", fg=typer.colors.CYAN, bold=True)
    for name, spec in servers.items():
        args = " ".join(spec.get("args", []))
        typer.echo(f"  - {name}: {spec['command']} {args}".rstrip())


@app.command("add")
def add_server_cmd(
    name: str = typer.Argument(..., help="Nombre único del servidor MCP."),
    command: str = typer.Argument(..., help="Comando a ejecutar, ej: npx"),
    args: list[str] = typer.Argument(None, help="Argumentos del comando."),
    env: list[str] = typer.Option(None, "--env", help="Variable de entorno VAR=valor, repetible."),
) -> None:
    try:
        env_dict = dict(item.split("=", 1) for item in (env or []))
    except ValueError:
        typer.secho("Error: --env debe tener la forma VAR=valor.", fg=typer.colors.RED)
        raise typer.Exit(code=1) from None

    try:
        add_server(name, command, args or [], env_dict)
    except ValueError as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from None

    typer.secho(f"Servidor MCP '{name}' agregado.", fg=typer.colors.GREEN)


@app.command("remove")
def remove_server_cmd(name: str = typer.Argument(..., help="Nombre del servidor a eliminar.")) -> None:
    try:
        remove_server(name)
    except ValueError as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from None

    typer.secho(f"Servidor MCP '{name}' eliminado.", fg=typer.colors.GREEN)
