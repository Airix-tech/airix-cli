# AIRIX CLI — Documentación del proyecto

## 1. Resumen ejecutivo

AIRIX CLI es una herramienta de automatización para trabajar con proyectos de software como un agente local de codificación asistida por IA. Su objetivo principal es acompañar al desarrollador en un flujo de trabajo seguro y controlado:

- detectar el tipo de repositorio,
- mantener memoria técnica persistente,
- construir contexto del proyecto para un modelo de IA,
- proponer cambios completos a archivos,
- validar esos cambios en una zona de staging,
- revisar y aprobar cada cambio antes de consolidarlo,
- compactar el historial para mantener el contexto manejable.

El proyecto combina:

- un CLI basado en Typer,
- un motor de análisis AST para TypeScript,
- una capa de memoria persistente en JSON,
- una zona temporal .tmp/ para propuestas no confirmadas,
- un REPL interactivo para revisión humana,
- un flujo de control de cambios con checkpoints y registro de decisiones.

---

## 2. Objetivos del sistema

La herramienta busca reducir la fricción entre la intención del desarrollador y la implementación real en el repositorio, con una política orientada a la trazabilidad, la seguridad y la validación.

### Funcionalidades principales

1. Inicialización del repositorio
   - crea la estructura .airix/
   - genera AGENT.md con reglas de gobernanza
   - detecta lenguaje, frameworks, patrones y comando de tests
   - guarda el perfil arquitectónico en memoria

2. Interacción con IA
   - consulta a un modelo Gemini a través de la API de Google
   - envía el contexto del repositorio, la gobernanza del proyecto y la memoria histórica
   - exige una respuesta JSON estructurada con archivos completos, no fragmentos

3. Staging de propuestas
   - escribe los archivos sugeridos en .tmp/
   - evita fragmentos parciales mediante validaciones de contenido
   - permite revisar los cambios antes de aplicar en el repo real

4. Validación en entorno aislado
   - clona el repositorio en un directorio temporal
   - superpone los cambios propuestos
   - ejecuta la suite de tests real sobre esa copia

5. Revisión humana
   - permite aprobar o rechazar cada archivo propuesto
   - muestra diff visual con Rich
   - registra la decisión técnica en memory.json

6. Compactación del contexto
   - guarda mensajes del REPL en .airix/session.json
   - detecta cuándo el historial supera un umbral de tokens
   - compacta el contexto y conserva una versión resumida

7. Análisis incremental de dependencias
   - extrae símbolos TypeScript con un sidecar Node
   - cachea metadatos por archivo
   - invalida en cascada los módulos dependientes cuando cambia una exportación

8. Multi-repo / workspace
   - crea un contenedor de repositorios con manifest .airix-workspace.toml
   - permite registrar repositorios adicionales dentro de un workspace

---

## 3. Arquitectura general

El proyecto se organiza como una CLI modular con capas bien diferenciadas:

- capa de entrada: CLI y comandos
- capa de contexto y memoria: archivos JSON bajo .airix/
- capa de agente LLM: conexión con Gemini y generación de propuestas
- capa de staging: escritura, validación y review
- capa de análisis: AST, caché e invalidación en cascada
- capa de workspace: gestión multi-repo

### Diagrama conceptual

```text
usuario
  |
  v
airix CLI (Typer)
  |
  +--> comandos: init / run / analyze / rewind / compact / workspace
  |
  +--> memory.store + schema
  |
  +--> context.workspace / compactor
  |
  +--> agent.client (Gemini / Anthropic / Ollama) + agent.mcp_manager (cliente MCP)
  |
  +--> staging.* (tmp, tests, checkpoints, git review)
  |
  +--> ast_engine.* (cache, graph, parser)
  |
  +--> repl.console (interacción humana)
```

---

## 4. Estructura del proyecto

```text
airix-cli/
├── pyproject.toml
├── README.md
├── DOCUMENTACION.md
├── sidecar/
│   ├── extract_symbols.js
│   └── package.json
├── src/
│   └── airix_cli/
│       ├── __init__.py
│       ├── cli.py
│       ├── agent/
│       │   ├── __init__.py
│       │   ├── client.py
│       │   ├── intent.py
│       │   └── mcp_manager.py
│       ├── ast_engine/
│       │   ├── __init__.py
│       │   ├── cache.py
│       │   ├── graph.py
│       │   ├── hashing.py
│       │   └── parser.py
│       ├── commands/
│       │   ├── __init__.py
│       │   ├── analyze.py
│       │   ├── compact.py
│       │   ├── init.py
│       │   ├── llm.py
│       │   ├── mcp.py
│       │   ├── rewind.py
│       │   ├── run.py
│       │   └── workspace.py
│       ├── context/
│       │   ├── __init__.py
│       │   ├── compactor.py
│       │   ├── references.py
│       │   └── workspace.py
│       ├── memory/
│       │   ├── __init__.py
│       │   ├── schema.py
│       │   └── store.py
│       ├── repl/
│       │   ├── __init__.py
│       │   ├── completion.py
│       │   └── console.py
│       └── staging/
│           ├── __init__.py
│           ├── checkpoints.py
│           ├── fswriter.py
│           ├── git_review.py
│           └── test_runner.py
└── test/
    ├── test_ast_cache.py
    ├── test_ast_graph.py
    ├── test_dispatch_mode.py
    ├── test_fswriter.py
    ├── test_git_review.py
    ├── test_init_profile.py
    ├── test_intent.py
    ├── test_memory.py
    ├── test_references.py
    └── test_workspace_context.py
```

---

## 5. Componentes principales

### 5.1 CLI principal

Archivo: src/airix_cli/cli.py

La entrada principal del proyecto se define con Typer:

- nombre del comando: airix
- subcomandos: init, compact, run, rewind, analyze
- sub-aplicaciones: workspace, llm, mcp

Es la capa de orquestación de todo el sistema y conecta la interfaz con los módulos funcionales.

#### Comandos disponibles

- airix init
  - prepara el repositorio para trabajar con AIRIX
- airix run
  - entra al REPL interactivo
- airix analyze
  - ejecuta análisis AST incremental
- airix compact
  - fuerza compactación del contexto de sesión
- airix rewind
  - restaura un checkpoint previo
- airix workspace init
  - crea un workspace multi-repo
- airix workspace add
  - registra repositorios dentro de ese workspace
- airix llm show / list / set
  - consulta y cambia el proveedor/modelo LLM activo (gemini, anthropic, ollama)
- airix mcp add / list / remove
  - gestiona los servidores MCP configurados en .airix/mcp_config.json

---

### 5.2 Inicialización del proyecto

Archivo: src/airix_cli/commands/init.py
Archivo: src/airix_cli/ast_engine/__init__.py

El comando init se encarga de preparar el repositorio de trabajo:

- crea .airix/
- genera AGENT.md con políticas operativas
- crea .airix/session.json y .airix/ast_cache.json
- inicializa .airix/memory.json
- detecta perfil tecnológico del proyecto:
  - lenguaje dominante
  - frameworks
  - test command
  - patrones de arquitectura

La detección se hace en función de:

- extensiones de archivos (.py, .ts, .tsx, etc.)
- presencia de archivos de configuración (package.json, pyproject.toml, Cargo.toml, go.mod)
- presencia de carpetas tests o test
- dependencias del proyecto

Esto permite que el agente haga decisiones más apropiadas con el contexto del repositorio.

---

### 5.3 Sistema de memoria

Directorios: src/airix_cli/memory/

El proyecto usa un modelo de memoria persistente basado en Pydantic y JSON para almacenar:

- profile: lenguaje, frameworks, patrones detectados, command test
- decisions: decisiones técnicas históricas
- resolved_errors: errores ya resueltos con causa raíz y solución

#### Schema principal

- ArchitecturalProfile
- TechnicalDecision
- ResolvedError
- MemoryFile

#### Propósito

La memoria actúa como historial de trabajo del agente para que no olvide decisiones previas, técnicas o correctivas. Se usa como contexto de entrada en cada sesión y también para la compactación del historial.

#### Escritura segura

La función save_memory usa escritura atómica con archivo temporal + os.replace para evitar corrupción por escrituras interrumpidas.

---

### 5.4 Agente LLM y contexto del repositorio

Archivo: src/airix_cli/agent/client.py

El agente soporta tres proveedores intercambiables (`airix llm set <provider> <model>`):

- `gemini` (nube, default) vía el SDK `google-genai`
- `anthropic` (nube, Claude) vía el SDK `anthropic`
- `ollama` (local) vía HTTP directo a `/api/chat`

La comunicación se estructura como una llamada con:

- system_instruction con gobernanza
- memory_context
- workspace_context
- instrucción del usuario

#### Reglas de la respuesta

La respuesta del modelo debe ser exactamente un JSON con esta forma:

```json
{
  "files": [
    {"path": "ruta/archivo.py", "content": "contenido completo"}
  ],
  "rationale": "explicación breve"
}
```

#### Garantías de seguridad

- se exige contenido completo del archivo, nunca un fragmento
- se rechaza el uso de diff parcial o elipsis
- rutas relativas al repositorio
- sin markdown fuera del JSON

Este diseño busca que la IA no entregue cambios incompletos o ambigüos.

---

### 5.5 Contexto de workspace

Archivo: src/airix_cli/context/workspace.py

La herramienta construye un snapshot del repositorio para alimentar el modelo. Esta función:

- recorre el árbol del proyecto
- ignora directorios sensibles (.git, .airix, .tmp, node_modules, etc.)
- filtra archivos ignorados por .gitignore
- limita la cantidad máxima de archivos y el tamaño total del contexto
- truncado si supera el umbral

Esto evita saturar el prompt con demasiados archivos o artefactos del entorno.

`build_workspace_context` acepta además `only_paths`: en vez de recorrer todo el árbol, arma el contexto a partir de exactamente esas rutas relativas (ya resueltas). Se usa cuando el usuario referenció archivos puntuales en vez de pedir el proyecto completo (ver 5.5.1).

#### 5.5.1 Referencias `@` y selección de contexto

Archivo: src/airix_cli/context/references.py, función `_context_for_instruction` en src/airix_cli/commands/run.py

Mandar siempre el workspace completo es costoso, sobre todo con un LLM local (puede añadir varios segundos solo para leer el contexto, incluso antes de generar una sola palabra). Para controlar cuánto repositorio viaja en cada mensaje, la instrucción del usuario se interpreta así:

- `@ruta/archivo.py` o `@archivo.py` → referencia un archivo puntual. Se busca primero por ruta relativa exacta y, si no existe, por nombre de archivo en todo el árbol (respetando los mismos directorios ignorados que el escaneo de workspace). Si el nombre es ambiguo (existe en más de una carpeta), se incluyen todas las coincidencias.
- `@proyecto`, `@project`, `@all`, `@workspace`, `@codebase`, `@repo`, `@repositorio`, o un `@` suelto sin nada detrás → piden el contexto completo del repositorio (el comportamiento de antes de existir referencias explícitas).
- Mencionar un nombre de archivo sin `@` (p. ej. "corrige deploy_yolo.py") sigue funcionando igual que con `@`, por compatibilidad con el uso ya existente.
- Una **consulta** (analizar/revisar/preguntar, ver 5.4.1) sin ninguna referencia no manda contenido de archivos: evita el costo de escanear y leer el repo para algo como "hola, cómo estás".
- Un **pedido de cambio** sin ninguna referencia sí manda el repositorio completo, porque el agente necesita verlo para decidir dónde aplicar el cambio.
- Una referencia a un archivo que no existe se avisa en el CLI (`No se encontró @nombre.py en el repositorio.`) y no interrumpe el resto de la instrucción.

El panel "Procesando instrucción" siempre muestra qué contexto se usó (`proyecto completo`, `archivo(s): ...`, o `sin archivos`), para que quede claro qué vio el modelo.

---

### 5.5.2 Cliente MCP (Model Context Protocol)

Archivo: src/airix_cli/agent/mcp_manager.py, src/airix_cli/commands/mcp.py

airix puede actuar como **cliente MCP**: conectarse a servidores MCP externos
(vía stdio, ej. `npx algún-servidor-mcp`) para que el agente use sus
herramientas al responder consultas.

#### Configuración

Los servidores se declaran en `.airix/mcp_config.json`, con el mismo formato
que usa Claude Desktop:

```json
{
  "mcpServers": {
    "figma": {"command": "npx", "args": ["-y", "figma-mcp-server"], "env": {"FIGMA_API_KEY": "..."}}
  }
}
```

Se gestionan con `airix mcp add/list/remove` (CLI) o `/mcp add/remove/show/tools/reload`
(REPL, ver 5.7).

#### `McpManager`: puente síncrono/asíncrono

El SDK oficial `mcp` es enteramente asíncrono, pero el resto de airix (REPL,
`agent/client.py`) es síncrono. `McpManager` resuelve esto corriendo un event
loop propio en un thread daemon que vive durante toda la sesión del REPL, y
expone una fachada síncrona (`list_tools`, `call_tool`, `shutdown`). Así, los
servidores se conectan una sola vez al arrancar el REPL (no en cada
instrucción): levantar un subproceso `npx` puede tardar 1-3s, y pagar ese
costo por turno haría lenta cualquier consulta con herramientas.

Las tools de cada servidor se registran con un nombre calificado
(`servidor__tool`) para evitar colisiones entre servidores, y un servidor que
falla al conectar no impide que los demás queden disponibles.

#### Tool-calling

Cuando hay servidores MCP conectados y el proveedor activo es `gemini` o
`anthropic`, las consultas (`answer_question`) se resuelven con un loop de
tool-calling acotado (máximo 5 idas y vueltas): el modelo pide ejecutar una
herramienta, `McpManager.call_tool` la ejecuta y devuelve el resultado, y el
modelo continúa hasta dar una respuesta final. Este path no transmite en
streaming (se pierde la respuesta incremental token a token): se muestra un
aviso "Consultando herramientas MCP..." y luego la respuesta completa.

`ollama` queda fuera del tool-calling en esta iteración (sin soporte nativo
confiable en modelos como qwen2.5-coder:7b) y sigue el path de completions
normal sin usar tools, aunque haya servidores MCP configurados. Del mismo
modo, `propose_changes` (modo cambios) no usa MCP tools todavía — queda como
extensión futura (ver sección 13).

---

### 5.6 Compactor de contexto

Archivo: src/airix_cli/context/compactor.py

El proyecto gestiona el estado de la sesión del REPL y evita perder el hilo en conversaciones largas.

#### Funcionamiento

- carga .airix/session.json
- cuenta tokens usando tiktoken
- si el contenido supera un umbral configurable, activa compactación
- sintetiza el contenido restante en un resumen
- almacena la decisión y reemplaza el historial por una versión resumida

Esto permite continuidad sin acumular demasiados tokens en el contexto del LLM.

#### Notas técnicas

- si tiktoken no puede descargarse o no está disponible, el sistema hace una aproximación por caracteres
- el compactor se puede reemplazar por una función externa, lo que deja la puerta abierta a un resumen LLM más inteligente

---

### 5.7 REPL y revisión humana

Archivo: src/airix_cli/repl/console.py

La interacción principal se realiza mediante un REPL con Rich.

#### Comandos del REPL

- help: muestra ayuda
- llm show / list / set: consulta y cambia el proveedor/modelo LLM activo
- mcp show / tools / add / remove / reload: gestiona servidores MCP y sus herramientas (ver 5.5.2)
- review: revisa los archivos en .tmp/
- compact: fuerza compactación
- salir: cierra la sesión
- instrucción textual: se la envía al agente para producir cambios

#### Proceso de revisión

1. el agente escribe propuestas en .tmp/
2. el usuario ejecuta review
3. el sistema compara cada archivo propuesto con su equivalente real
4. muestra diff con colores y sintaxis resaltada
5. pregunta por cada archivo:
   - si
   - no
   - todo
   - salir
6. conserva solo los aprobados

---

### 5.8 Staging y preparación de cambios

Directorios: src/airix_cli/staging/

Esta capa asegura que los cambios propuestos no se mezclen directamente con el árbol real antes de la validación.

#### fswriter.py

- escribe archivos completos en .tmp/
- evita contenido parcial detectando marcadores como diff, elipsis y cabeceras incompletas
- permite clear_staging para limpiar la fase de propuesta

#### test_runner.py

- crea una copia temporal del repositorio
- superpone los archivos cambiados desde .tmp/
- ejecuta el comando de tests sobre la copia temporal
- devuelve el resultado con stdout / stderr

#### checkpoints.py

- crea un checkpoint tar.gz en .airix/checkpoints
- guarda una instantánea del repositorio excluyendo artefactos del sistema

#### git_review.py

- usa git add sobre archivos aprobados para una revisión visual en VS Code
- no crea commits ni interactúa con remotes
- hace más fácil revisar cambios en el índice local del repositorio

---

### 5.9 Motor AST e invalidación en cascada

Directorios: src/airix_cli/ast_engine/

Esta capa implementa análisis incremental de dependencias entre archivos TypeScript.

#### parser.py

- invoca un sidecar de Node: sidecar/extract_symbols.js
- usa ts-morph para extraer símbolos del archivo
- devuelve información como:
  - imports
  - exports
  - classes
  - interfaces

#### cache.py

- guarda hash por archivo
- compara hash actual con el cache
- evita reanálisis si el archivo no cambió

#### graph.py

- construye un grafo inverso de dependencias
- para cada archivo, identifica quiénes dependen de él
- si cambian las exportaciones, reanaliza recursivamente a todos los dependientes

#### cascade_reanalyze

Es el núcleo del mecanismo incremental. El algoritmo básico es:

1. detecta archivo(s) modificados
2. calcula firma previa de exports
3. reanaliza el archivo y compara firma nueva vs vieja
4. si cambia, propaga la invalidación a dependientes en BFS
5. persiste el cache actualizado

Esto mejora rendimiento cuando el repositorio es grande y solo unas partes están cambiadas.

---

### 5.10 Sidecar de Node

Carpeta: sidecar/

El proyecto incluye un script JavaScript para extraer símbolos y metadatos de archivos TypeScript.

#### Propósito

- separar la lógica de parseo de TypeScript del resto del proyecto
- facilitar la integración con ts-morph
- evitar depender de análisis Python para código TypeScript

El parser de Python llama a Node con el archivo objetivo y recibe JSON. Es un enfoque de interoperabilidad muy económico para un proyecto de este tipo.

---

## 6. Flujo de trabajo típico

### Caso de uso habitual

1. El usuario entra en un repositorio y ejecuta:
   - airix init
2. La CLI genera AGENT.md y .airix/
3. El sistema detecta el lenguaje y el comando de tests
4. El usuario ejecuta:
   - airix run
5. El REPL está listo para recibir instrucciones del tipo:
   - "agrega validación de entrada"
   - "refactoriza esta función"
   - "revisa el sistema de autenticación"
6. El agente consulta el modelo con memoria + contexto del repo
7. El modelo responde con archivos completos propuestos
8. Los cambios se escriben en .tmp/
9. El usuario ejecuta review
10. Se corren tests sobre una copia del repo con los cambios superpuestos
11. Se inspecciona el diff
12. El usuario aprueba o rechaza la propuesta
13. Los cambios aprobados se consolidan al repo real
14. Se registra la decisión en memory.json
15. Se limpia .tmp/

---

## 7. Variables de entorno y dependencias

### Dependencias principales

El proyecto usa:

- Python 3.11+
- Typer
- Rich
- Pydantic
- tiktoken
- watchdog
- tomli-w
- google-genai
- anthropic
- mcp
- prompt-toolkit

Estas dependen del archivo pyproject.toml.

### Variables requeridas

Según el proveedor LLM activo (`airix llm set <provider> <model>`), el entorno
debe contar con la API key correspondiente:

- GEMINI_API_KEY o GOOGLE_API_KEY (proveedor `gemini`, default)
- ANTHROPIC_API_KEY (proveedor `anthropic`, Claude)
- `ollama` no necesita API key, pero requiere `ollama serve` corriendo en local

Ejemplo:

```bash
export GEMINI_API_KEY=tu_clave
```

Los servidores MCP (ver 5.5.2) no requieren variables de entorno propias de
airix; cada servidor declara las suyas en `.airix/mcp_config.json` (campo `env`).

---

## 8. Instalación

```bash
uv sync
cd sidecar && npm install && cd ..
```

Esto prepara las dependencias Python y los paquetes del sidecar Node para el parseo de TypeScript.

---

## 9. Uso básico

```bash
# Inicialización del repositorio
airix init

# REPL interactivo
airix run

# Análisis AST incremental
airix analyze

# Listar checkpoints
airix rewind --list

# Restaurar a un checkpoint
airix rewind <archivo>

# Compactar sesión
airix compact

# Workspace multi-repo
airix workspace init <nombre>
airix workspace add <ruta-a-un-repo> --workspace <ruta-al-workspace>

# Proveedor/modelo LLM activo
airix llm show
airix llm set anthropic claude-sonnet-5

# Servidores MCP
airix mcp add figma npx --env FIGMA_API_KEY=... -- -y figma-mcp-server
airix mcp list
airix mcp remove figma
```

---

## 10. Archivos y directorios relevantes dentro de .airix

Cuando se inicializa el repositorio, se crea la estructura:

```text
.airix/
├── ast_cache.json
├── checkpoints/
├── llm_config.json
├── mcp_config.json
├── memory.json
├── repl_history
├── session.json
```

### Propósito de cada archivo

- ast_cache.json: cache de análisis AST (Python y TypeScript) y hashes de archivos
- checkpoints/: instantáneas comprimidas del repositorio para rewind
- llm_config.json: proveedor y modelo LLM activo (gemini/anthropic/ollama)
- mcp_config.json: servidores MCP configurados (ver 5.5.2)
- memory.json: memoria persistente del proyecto
- repl_history: historial de instrucciones del REPL (↑/↓, Ctrl+R); se reinicia al compactar
- session.json: historial activo del REPL o resumen compacto

---

## 11. Seguridad y gobernanza

El proyecto incorpora reglas de seguridad explícitas en AGENT.md.

### Principios principales

- trabajo solo dentro de la raíz del repositorio
- no se debe acceder a secretos fuera de .env explícitamente declarados
- no se permiten descargas o llamadas de red no aprobadas
- todo cambio debe pasar por .tmp/ → tests → revisión
- no se aceptan archivos parciales o snippets incompletos
- no se pueden eliminar elementos sensibles como .git o .airix sin aprobación

Esto convierte el flujo en un proceso más seguro y auditable.

---

## 12. Limitaciones y consideraciones

El proyecto es una base funcional y orientada a flujo controlado, pero tiene límites importantes:

- el motor AST soporta Python y TypeScript/TSX; otros lenguajes quedan sin analizar
- la resolución de imports es simplificada y no replica completamente el comportamiento de un bundler o de `sys.path` real
- la compactación de sesión cae a un resumen heurístico si el LLM no está disponible
- la capacidad del agente depende de la calidad del contexto y de la disponibilidad de la API del modelo
- el modelo de generación exige respuestas JSON estrictas, lo que exige una disciplina fuerte en la salida del agente
- el tool-calling con servidores MCP solo funciona con los proveedores `gemini`/`anthropic`, y solo en modo consulta (`propose_changes` no usa tools todavía)
- el path de tool-calling MCP no soporta streaming: la respuesta se muestra completa al terminar, no token a token

Estas limitaciones son bastante típicas en proyectos de automatización local con IA y marcan claramente los puntos de extensión futura.

---

## 13. Posibles extensiones futuras

El sistema está listo para evolucionar en varias direcciones:

1. soporte más amplio de lenguajes y parsers
2. resolución completa de imports con tsconfig, aliases y módulos (TS) o `sys.path` real (Python)
3. resumen de contexto por IA más avanzado
4. tool-calling MCP en `propose_changes` (modo cambios), no solo en consultas
5. tool-calling MCP con Ollama (requiere un modelo local con soporte confiable)
6. auditoría extendida de decisiones y tracking de errores
7. mejora del workspace multi-repo con contexto cruzado entre repositorios
8. panel de métricas de análisis, compactación y tiempo de validación

---

## 14. Conclusión

AIRIX CLI es un sistema de agente de codificación con memoria persistente, validación controlada y flujo de revisión humana. Su fortaleza principal no está solo en la generación de código, sino en el conjunto de mecanismos que la hacen segura, trazable y operable en un repositorio real.

La combinación entre:

- gobernanza del agente,
- memoria técnica,
- contexto del repositorio,
- pruebas en copia temporal,
- diff visual y revisión humana,
- análisis incremental AST,

permite convertir la IA en una herramienta más útil para la ingeniería real, sin perder control sobre el código final.
