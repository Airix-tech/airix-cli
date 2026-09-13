import typer

from airix_cli.agent.client import (
    PROVIDER_MODELS,
    get_available_models,
    get_provider_status,
    load_model_config,
    set_model_config,
)

app = typer.Typer()

AVAILABLE_PROVIDERS = list(PROVIDER_MODELS)


# Click/Typer invoca `shell_complete(ctx, param, incomplete)` en ese orden.
# Con la firma anterior (incomplete primero) el prefijo real llegaba al
# parámetro ignorado y el autocompletado devolvía siempre la lista entera.
def complete_provider(_ctx: object | None, _param: object | None, incomplete: str | None):
    prefix = (incomplete or "").lower()
    return [provider for provider in AVAILABLE_PROVIDERS if provider.startswith(prefix)]


def complete_model(_ctx: object | None, _param: object | None, incomplete: str | None):
    prefix = (incomplete or "").lower()
    models: list[str] = []
    for provider in AVAILABLE_PROVIDERS:
        for model in get_available_models(provider):
            if model not in models:
                models.append(model)
    return [model for model in models if model.lower().startswith(prefix)]


@app.command("show")
def show_config() -> None:
    config = load_model_config()
    typer.secho("Configuración activa", fg=typer.colors.CYAN, bold=True)
    typer.echo(f"  Proveedor: {config['provider']}")
    typer.echo(f"  Modelo: {config['model']}")
    typer.secho("\nProveedores disponibles", fg=typer.colors.CYAN, bold=True)
    for provider in get_provider_status():
        state = "disponible" if provider["available"] else "no disponible"
        color = typer.colors.GREEN if provider["available"] else typer.colors.YELLOW
        typer.secho(
            f"  - {provider['name']} ({provider['kind']}): {state} - {provider['detail']}",
            fg=color,
        )


@app.command("list")
def list_models(
    provider: str = typer.Argument(
        "gemini",
        help="Proveedor del que listar los modelos disponibles.",
        shell_complete=complete_provider,
    ),
) -> None:
    models = get_available_models(provider)
    typer.secho(f"Modelos para {provider}:", fg=typer.colors.GREEN)
    for model in models:
        typer.echo(f"- {model}")


@app.command("set")
def set_config(
    provider: str = typer.Argument(
        ...,
        help="Proveedor LLM a usar.",
        shell_complete=complete_provider,
    ),
    model: str = typer.Argument(
        ...,
        help="Modelo concreto del proveedor.",
        shell_complete=complete_model,
    ),
) -> None:
    try:
        config = set_model_config(provider, model)
    except ValueError as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from None

    typer.secho(f"Configuración guardada: {config['provider']} / {config['model']}", fg=typer.colors.GREEN)
