# airix-cli

Agente de codificación con memoria persistente, motor AST incremental con
invalidación en cascada, área de staging con pruebas, REPL de aprobación y
compactación de contexto.

## Instalación

```bash
uv sync
cd sidecar && npm install && cd ..
```

Exporta tu API key de Anthropic antes de usar `airix run` (es la que consulta
el agente que propone cambios):

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

## Uso básico

```bash
# Dentro de un repositorio existente:
airix init                  # crea AGENT.md + .airix/, detecta lenguaje/frameworks/test command

airix run                   # abre el REPL: escribe instrucciones, el agente propone
                             # cambios en .tmp/, "review" los valida contra tests y
                             # los aprueba/rechaza, "compact" condensa el contexto

airix analyze               # corre el motor AST (TypeScript) con caché e invalidación
                             # en cascada sobre todo el repo

airix rewind --list         # lista checkpoints disponibles
airix rewind <archivo>       # restaura el repo a un checkpoint anterior

airix compact                # fuerza la compactación de la sesión actual

# Contenedor multi-repo:
airix workspace init <nombre>
airix workspace add <ruta-a-un-repo> --workspace <ruta-al-workspace>
```

## Desarrollo

```bash
uv run pytest
```