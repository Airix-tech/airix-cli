# airix-cli

Agente de codificación con memoria persistente, motor AST incremental con
invalidación en cascada, área de staging con pruebas, REPL de aprobación y
compactación de contexto.

## Instalación

```bash
uv sync
cd sidecar && npm install && cd ..
```

airix soporta tres proveedores de LLM: `gemini` (nube, default), `anthropic`/Claude
(nube) y `ollama` (local). Exporta la API key del proveedor que uses antes de
correr `airix run`:

```bash
export GEMINI_API_KEY=AIza...       # o GOOGLE_API_KEY, para el proveedor gemini
export ANTHROPIC_API_KEY=sk-ant-... # para el proveedor anthropic (Claude)
# ollama no necesita API key; solo requiere `ollama serve` corriendo en local
```

Cambiá de proveedor con `airix llm set <provider> <model>` (ver `airix llm show`
para ver el estado de cada uno).

## Conectar servidores MCP

airix puede actuar como **cliente MCP** (Model Context Protocol): conectarse a
servidores externos (Figma, filesystem, etc.) para que el agente use sus
herramientas al responder consultas. El tool-calling solo funciona con los
proveedores `gemini` y `anthropic` (Ollama no tiene tool-calling nativo
confiable y sigue funcionando igual, sin tools).

```bash
# Agregar un servidor (queda en .airix/mcp_config.json)
airix mcp add figma npx --env FIGMA_API_KEY=... -- -y figma-mcp-server

# Listar servidores configurados
airix mcp list

# Quitar un servidor
airix mcp remove figma
```

Dentro del REPL (`airix run`) hay comandos equivalentes:

```text
/mcp show            # servidores configurados + estado de conexión
/mcp tools           # herramientas disponibles de los servidores conectados
/mcp add <nombre> <comando> [args...] [--env=VAR=valor ...]
/mcp remove <nombre>
/mcp reload          # reconecta todos los servidores configurados
```

Si hay servidores configurados y el proveedor activo es `gemini`/`anthropic`,
airix los conecta automáticamente al arrancar el REPL (una sola vez, no en
cada instrucción). Una consulta que necesite una herramienta MCP no
transmite en streaming: se avisa "Consultando herramientas MCP..." y se
imprime la respuesta completa al terminar.

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