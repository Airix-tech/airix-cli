# src/airix_cli/agent/client.py
import json
import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import anthropic
from google import genai
from google.genai import types

from airix_cli.agent.mcp_manager import McpManager, get_mcp_manager

_client: genai.Client | None = None
_anthropic_client: anthropic.Anthropic | None = None

DEFAULT_PROVIDER = "gemini"
DEFAULT_MODEL = "gemini-flash-latest"
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_DEFAULT_MODEL = "qwen-coder-fast"
PROVIDER_MODELS = {
    "gemini": [
        "gemini-flash-latest",
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-2.0-flash",
    ],
    "anthropic": [
        "claude-sonnet-5",
        "claude-opus-5",
        "claude-haiku-4-5",
        "claude-fable-5-1",
    ],
    "ollama": [OLLAMA_DEFAULT_MODEL],
}
MAX_OUTPUT_TOKENS = 8000
OLLAMA_CONTEXT_TOKENS = 32768

# Proveedores con tool-calling soportado para MCP en esta iteración. Ollama
# (qwen2.5-coder:7b) no tiene tool-calling nativo confiable, así que queda
# fuera: sigue el path de completions normal sin importar qué MCP tools
# haya configuradas.
MCP_TOOL_CALLING_PROVIDERS = ("gemini", "anthropic")
MAX_TOOL_ITERATIONS = 5


def _config_path() -> Path:
    path = Path(".airix/llm_config.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def normalize_model_config(config: dict | None = None) -> dict:
    provider = (config or {}).get("provider", DEFAULT_PROVIDER).lower()
    provider = provider if provider in PROVIDER_MODELS else DEFAULT_PROVIDER
    models = PROVIDER_MODELS[provider]
    default_model = OLLAMA_DEFAULT_MODEL if provider == "ollama" else DEFAULT_MODEL
    model = (config or {}).get("model", default_model)
    if provider == "ollama":
        model = model or OLLAMA_DEFAULT_MODEL
    elif model not in models:
        model = models[0] if models else DEFAULT_MODEL
    return {"provider": provider, "model": model}


def load_model_config(path: Path | None = None) -> dict:
    target = path or _config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        cfg = normalize_model_config({"provider": DEFAULT_PROVIDER, "model": DEFAULT_MODEL})
        save_model_config(cfg, target)
        return cfg
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        cfg = normalize_model_config({"provider": DEFAULT_PROVIDER, "model": DEFAULT_MODEL})
        save_model_config(cfg, target)
        return cfg
    normalized = normalize_model_config(raw)
    if normalized != raw:
        save_model_config(normalized, target)
    return normalized


def save_model_config(config: dict, path: Path | None = None) -> dict:
    target = path or _config_path()
    normalized = normalize_model_config(config)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
    return normalized


def set_model_config(provider: str, model: str | None = None, path: Path | None = None) -> dict:
    provider_name = provider.lower()
    if provider_name not in PROVIDER_MODELS:
        raise ValueError(f"Proveedor no soportado: {provider}. Disponibles: {', '.join(PROVIDER_MODELS)}")
    candidates = PROVIDER_MODELS[provider_name]
    selected_model = model or (OLLAMA_DEFAULT_MODEL if provider_name == "ollama" else candidates[0])
    if provider_name != "ollama" and selected_model not in candidates:
        raise ValueError(f"Modelo no soportado para {provider_name}: {selected_model}")
    return save_model_config({"provider": provider_name, "model": selected_model}, path)


def get_available_models(provider: str = DEFAULT_PROVIDER) -> list[str]:
    provider_name = provider.lower()
    if provider_name == "ollama":
        return _fetch_ollama_models() or [OLLAMA_DEFAULT_MODEL]
    return list(PROVIDER_MODELS.get(provider_name, PROVIDER_MODELS[DEFAULT_PROVIDER]))


def _fetch_ollama_models() -> list[str] | None:
    try:
        request = Request(f"{OLLAMA_BASE_URL}/api/tags", method="GET")
        with urlopen(request, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return [item["name"] for item in payload.get("models", []) if item.get("name")]
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None


def get_provider_status() -> list[dict[str, object]]:
    """Devuelve disponibilidad y tipo de cada proveedor configurado."""
    has_gemini_key = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    has_anthropic_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    ollama_models = _fetch_ollama_models()
    return [
        {
            "name": "gemini",
            "kind": "nube",
            "available": has_gemini_key,
            "detail": "API key configurada" if has_gemini_key else "falta GEMINI_API_KEY o GOOGLE_API_KEY",
        },
        {
            "name": "anthropic",
            "kind": "nube",
            "available": has_anthropic_key,
            "detail": "API key configurada" if has_anthropic_key else "falta ANTHROPIC_API_KEY",
        },
        {
            "name": "ollama",
            "kind": "local",
            "available": ollama_models is not None,
            "detail": (
                f"{len(ollama_models)} modelo(s) en {OLLAMA_BASE_URL}"
                if ollama_models is not None
                else f"sin respuesta en {OLLAMA_BASE_URL}"
            ),
        },
    ]


def get_active_model_config() -> dict:
    env_provider = os.environ.get("AIRIX_LLM_PROVIDER")
    env_model = os.environ.get("AIRIX_LLM_MODEL")
    if env_provider or env_model:
        cfg = {"provider": env_provider or DEFAULT_PROVIDER, "model": env_model or DEFAULT_MODEL}
        return normalize_model_config(cfg)
    return load_model_config()


def get_model_name() -> str:
    return get_active_model_config()["model"]


SYSTEM_PROMPT_TEMPLATE = """\
Eres un agente de codificación operando dentro de un repositorio real.
Tu proveedor activo es `{provider}` y tu modelo activo es `{model}`.

{governance}

{memory_context}

{workspace_context}

Responde ÚNICAMENTE con un JSON válido (sin texto adicional antes o después, \
sin bloques de markdown ```), con exactamente esta forma:

{{
  "files": [
    {{"path": "ruta/relativa/al/archivo.py", "content": "contenido COMPLETO del archivo"}}
  ],
    "rationale": "respuesta final al usuario o explicación breve de los cambios"
}}

Reglas estrictas:
- "content" debe ser el archivo COMPLETO, nunca un fragmento, diff o snippet parcial.
- Las rutas son siempre relativas a la raíz del repositorio, nunca absolutas ni con "..".
- Si la instrucción es una pregunta o conversación y no requiere cambios, devuelve "files": [] y responde directamente al usuario usando "rationale" como respuesta final.
- Nunca escribas en "rationale" frases como "no se requieren cambios", "no hay cambios" o "no se modificaron archivos" si el usuario pidió una respuesta.
- Ejemplo: si el usuario dice "responde con un ok", responde exactamente con {{"files": [], "rationale": "OK"}}.
- No describas el proceso interno ni si se requiere un cambio. Responde el contenido solicitado.
- Si preguntan qué modelo eres, indica que eres un asistente de codificación usando el proveedor y modelo activos.
"""

ANSWER_PROMPT_TEMPLATE = """\
Eres un asistente de codificación operando dentro de un repositorio real.
Tu proveedor activo es `{provider}` y tu modelo activo es `{model}`.

{governance}

{memory_context}

{workspace_context}

Modo consulta: el usuario pide un análisis, una revisión o una explicación, NO cambios.
- Responde directamente en texto (puedes usar Markdown), en el idioma del usuario.
- No devuelvas JSON ni propongas archivos para escribir: nada de esta respuesta se guarda en disco.
- Si revisas código, cita el archivo y la función o línea concreta, explica cada problema y \
sugiere cómo resolverlo. Incluye solo los fragmentos de código necesarios, nunca el archivo completo.
- Si preguntan qué modelo eres, indica que eres un asistente de codificación usando el proveedor y modelo activos.
"""

# Cuánto de la transcripción se manda a resumir. Se prioriza lo más reciente
# (ver `_render_transcript`) porque el umbral de compactación (100k tokens,
# ver context/compactor.py) es mucho mayor que el contexto de un LLM local
# (32768 tokens aquí); mandar la sesión completa desbordaría a Ollama.
SUMMARY_MAX_TRANSCRIPT_CHARS = 16_000

SUMMARY_SYSTEM_PROMPT = """\
Eres el encargado de resumir el historial de una sesión de trabajo entre un \
desarrollador y un agente de codificación, para que la siguiente sesión pueda \
continuar sin perder el hilo.

Responde ÚNICAMENTE con un JSON válido (sin texto adicional antes o después, \
sin bloques de markdown ```), con exactamente esta forma:

{
  "summary": "resumen narrativo breve (3 a 6 líneas) de qué se hizo y por qué",
  "key_decisions": ["decisión técnica concreta 1", "decisión técnica concreta 2"],
  "active_tasks": ["tarea pendiente o en curso 1"],
  "unresolved_issues": ["error o problema sin resolver 1"],
  "affected_files": ["ruta/relativa/uno.py"]
}

Reglas:
- Cada elemento de las listas es una frase corta y concreta, nunca un párrafo ni la \
transcripción copiada literal.
- Si una categoría no aplica, devuelve una lista vacía: nunca inventes decisiones, \
tareas o archivos que no aparezcan en la transcripción.
- Los mensajes de rol "system" ya son resúmenes de compactaciones anteriores: \
intégralos como contexto previo, no los repitas tal cual.
"""


def _render_transcript(messages: list[dict], *, max_chars: int = SUMMARY_MAX_TRANSCRIPT_CHARS) -> str:
    """
    Arma la transcripción a resumir. Si no entra completa en `max_chars`,
    conserva los mensajes más recientes (los más relevantes para continuar el
    trabajo) y deja constancia de cuántos quedaron afuera, en vez de cortar a
    la mitad el mensaje más antiguo.
    """
    kept: list[str] = []
    used = 0
    cursor = len(messages)
    for message in reversed(messages):
        role = message.get("role", "user")
        content = message.get("content", "")
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        line = f"[{role}] {content}"
        if kept and used + len(line) > max_chars:
            break
        kept.append(line)
        used += len(line)
        cursor -= 1
    kept.reverse()
    if cursor > 0:
        kept.insert(0, f"[...{cursor} mensaje(s) más antiguos omitidos por espacio...]")
    return "\n\n".join(kept)


def summarize_conversation(messages: list[dict]) -> dict:
    """
    Pide al proveedor activo un resumen estructurado de la conversación, en
    vez de la extracción por palabras clave de `compactor.build_session_summary`:
    entiende el texto en lugar de solo buscar coincidencias literales de
    "TypeError" o "decisión".

    Deja propagar cualquier error (proveedor caído, JSON inválido, etc.);
    quien llama decide si cae de vuelta a la heurística
    (ver `context.compactor.summarize_session`).
    """
    empty = {
        "summary": "",
        "key_decisions": [],
        "active_tasks": [],
        "unresolved_issues": [],
        "affected_files": [],
    }
    if not messages:
        return {**empty, "last_updated": datetime.now(timezone.utc).isoformat()}

    transcript = _render_transcript(messages)
    raw = _raw_complete(SUMMARY_SYSTEM_PROMPT, transcript, json_mode=True)
    summary = _extract_json(raw)
    result = {**empty, **summary, "last_updated": datetime.now(timezone.utc).isoformat()}
    return result


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Falta la variable de entorno GEMINI_API_KEY (o GOOGLE_API_KEY). "
                "Expórtala antes de correr `airix run`, ej:\n"
                "  export GEMINI_API_KEY=AIza..."
            )
        _client = genai.Client(api_key=api_key)
    return _client


def _get_anthropic_client() -> anthropic.Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Falta la variable de entorno ANTHROPIC_API_KEY. "
                "Expórtala antes de correr `airix run`, ej:\n"
                "  export ANTHROPIC_API_KEY=sk-ant-..."
            )
        _anthropic_client = anthropic.Anthropic(api_key=api_key)
    return _anthropic_client


def _chat_with_anthropic(
    model: str,
    instruction: str,
    system_prompt: str,
    *,
    on_chunk: Callable[[str], None] | None = None,
) -> str:
    client = _get_anthropic_client()
    try:
        if on_chunk is not None:
            chunks: list[str] = []
            with client.messages.stream(
                model=model,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=system_prompt,
                messages=[{"role": "user", "content": instruction}],
            ) as stream:
                for text in stream.text_stream:
                    chunks.append(text)
                    on_chunk(text)
            text_out = "".join(chunks)
        else:
            response = client.messages.create(
                model=model,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=system_prompt,
                messages=[{"role": "user", "content": instruction}],
            )
            text_out = "".join(block.text for block in response.content if block.type == "text")
    except anthropic.APIStatusError as exc:
        raise RuntimeError(f"Error de la API de Anthropic: {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise RuntimeError("No se pudo conectar con la API de Anthropic.") from exc

    if not text_out:
        raise RuntimeError("Claude devolvió una respuesta vacía.")
    return text_out


def _chat_with_ollama(
    model: str,
    instruction: str,
    system_prompt: str,
    *,
    json_mode: bool,
    on_chunk: Callable[[str], None] | None = None,
) -> str:
    stream = on_chunk is not None
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": instruction},
        ],
        "stream": stream,
        "options": {
            "num_predict": MAX_OUTPUT_TOKENS,
            "num_ctx": OLLAMA_CONTEXT_TOKENS,
        },
    }
    if json_mode:
        payload["format"] = "json"
    request = Request(
        f"{OLLAMA_BASE_URL}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        if not stream:
            with urlopen(request, timeout=300) as response:
                result = json.loads(response.read().decode("utf-8"))
            content = result.get("message", {}).get("content")
            if not content:
                raise RuntimeError(f"Ollama devolvió una respuesta sin contenido: {result}")
            return content

        # Modo streaming: Ollama devuelve un objeto JSON por línea con un
        # fragmento en `message.content`, hasta uno final con `done: true`. Se
        # entrega cada fragmento tal cual llega para que la terminal muestre
        # texto de inmediato en vez de esperar la respuesta completa.
        chunks: list[str] = []
        with urlopen(request, timeout=300) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue
                obj = json.loads(line)
                delta = obj.get("message", {}).get("content", "")
                if delta:
                    chunks.append(delta)
                    on_chunk(delta)
        content = "".join(chunks)
        if not content:
            raise RuntimeError("Ollama devolvió una respuesta sin contenido.")
        return content
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"No se pudo conectar con Ollama en {OLLAMA_BASE_URL}. "
            "Comprueba que `ollama serve` está ejecutándose y que el modelo existe."
        ) from exc


def _extract_json(raw_text: str) -> dict:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"El agente no devolvió JSON válido: {e}\n\nRespuesta cruda:\n{raw_text}"
        ) from e


def _raw_complete(
    system_prompt: str,
    instruction: str,
    *,
    json_mode: bool,
    on_chunk: Callable[[str], None] | None = None,
) -> str:
    """
    Envía `system_prompt` + `instruction` al proveedor activo tal cual, sin
    plantilla de por medio, y devuelve el texto crudo de la respuesta. Si se
    pasa `on_chunk`, se invoca con cada fragmento a medida que llega
    (streaming), para que el CLI muestre texto sin esperar a que termine toda
    la generación.
    """
    config = get_active_model_config()

    if config["provider"] == "ollama":
        return _chat_with_ollama(
            config["model"], instruction, system_prompt, json_mode=json_mode, on_chunk=on_chunk
        )
    if config["provider"] == "anthropic":
        return _chat_with_anthropic(config["model"], instruction, system_prompt, on_chunk=on_chunk)

    client = _get_client()
    generation_config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )

    if on_chunk is not None:
        chunks: list[str] = []
        for event in client.models.generate_content_stream(
            model=config["model"], contents=instruction, config=generation_config
        ):
            if event.text:
                chunks.append(event.text)
                on_chunk(event.text)
        text = "".join(chunks)
    else:
        response = client.models.generate_content(
            model=config["model"], contents=instruction, config=generation_config
        )
        text = response.text or ""

    if not text:
        raise RuntimeError(
            "Gemini devolvió una respuesta vacía "
            f"(posible corte por max_output_tokens={MAX_OUTPUT_TOKENS} o filtro de seguridad)."
        )
    return text


def _complete(
    template: str,
    instruction: str,
    governance: str,
    memory_context: str,
    workspace_context: str,
    *,
    json_mode: bool,
    on_chunk: Callable[[str], None] | None = None,
) -> str:
    """Rellena `template` con el contexto del repo y delega en `_raw_complete`."""
    config = get_active_model_config()
    system_prompt = template.format(
        provider=config["provider"],
        model=config["model"],
        governance=governance or "(no se encontró AGENT.md en este repositorio)",
        memory_context=memory_context,
        workspace_context=workspace_context or "(no se cargó el contexto de archivos)",
    )
    return _raw_complete(system_prompt, instruction, json_mode=json_mode, on_chunk=on_chunk)


def propose_changes(
    instruction: str,
    governance: str,
    memory_context: str,
    workspace_context: str = "",
) -> dict:
    """
    Pide al agente propuestas de archivo (JSON con `files` y `rationale`) para
    la instrucción del usuario y el contexto del repositorio.
    """
    raw = _complete(
        SYSTEM_PROMPT_TEMPLATE, instruction, governance, memory_context, workspace_context, json_mode=True
    )
    return _extract_json(raw)


def _call_mcp_tool_safe(manager: McpManager, qualified_name: str, arguments: dict) -> str:
    """
    Ejecuta una tool MCP y nunca deja propagar la excepción: un error de
    ejecución (timeout, tool inexistente, servidor caído) se devuelve como
    texto de error para que el modelo pueda decidir cómo seguir, en vez de
    romper el loop de tool-calling completo.
    """
    try:
        return manager.call_tool(qualified_name, arguments)
    except Exception as exc:
        return f"[error ejecutando {qualified_name}] {exc}"


def _answer_with_tools_gemini(
    instruction: str, system_prompt: str, model: str, tools: list[dict], manager: McpManager
) -> str:
    client = _get_client()
    declarations = [
        types.FunctionDeclaration(
            name=t["qualified_name"],
            description=t["description"],
            parameters_json_schema=t["input_schema"] or {"type": "object", "properties": {}},
        )
        for t in tools
    ]
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        tools=[types.Tool(function_declarations=declarations)],
    )
    contents: list[types.Content] = [types.Content(role="user", parts=[types.Part(text=instruction)])]

    last_text = ""
    for _ in range(MAX_TOOL_ITERATIONS):
        response = client.models.generate_content(model=model, contents=contents, config=config)
        candidate_content = response.candidates[0].content
        parts = candidate_content.parts or []
        function_calls = [p.function_call for p in parts if p.function_call]

        if not function_calls:
            last_text = "".join(p.text for p in parts if p.text) or response.text or ""
            return last_text

        contents.append(candidate_content)
        response_parts = []
        for call in function_calls:
            result_text = _call_mcp_tool_safe(manager, call.name, dict(call.args or {}))
            response_parts.append(types.Part.from_function_response(name=call.name, response={"result": result_text}))
        contents.append(types.Content(role="user", parts=response_parts))

    return last_text or "(se alcanzó el límite de llamadas a herramientas MCP sin una respuesta final)"


def _answer_with_tools_anthropic(
    instruction: str, system_prompt: str, model: str, tools: list[dict], manager: McpManager
) -> str:
    client = _get_anthropic_client()
    anthropic_tools = [
        {
            "name": t["qualified_name"],
            "description": t["description"],
            "input_schema": t["input_schema"] or {"type": "object", "properties": {}},
        }
        for t in tools
    ]
    messages: list[dict] = [{"role": "user", "content": instruction}]

    last_text = ""
    for _ in range(MAX_TOOL_ITERATIONS):
        response = client.messages.create(
            model=model,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=system_prompt,
            tools=anthropic_tools,
            messages=messages,
        )

        if response.stop_reason != "tool_use":
            last_text = "".join(block.text for block in response.content if block.type == "text")
            return last_text

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result_text = _call_mcp_tool_safe(manager, block.name, block.input or {})
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result_text,
                "is_error": result_text.startswith("[error"),
            })
        messages.append({"role": "user", "content": tool_results})

    return last_text or "(se alcanzó el límite de llamadas a herramientas MCP sin una respuesta final)"


def answer_question(
    instruction: str,
    governance: str,
    memory_context: str,
    workspace_context: str = "",
    *,
    on_chunk: Callable[[str], None] | None = None,
    on_status: Callable[[str], None] | None = None,
) -> str:
    """
    Responde una consulta (análisis, revisión, explicación) en texto libre.
    No hay esquema de `files`, así que el modelo no tiene dónde proponer
    archivos y nada termina en `.tmp/`.

    Con `on_chunk`, la respuesta se transmite en streaming: cada fragmento se
    entrega en cuanto llega en vez de esperar a que el modelo termine de
    generar todo el texto.

    Si hay servidores MCP conectados y el proveedor activo soporta
    tool-calling (`gemini`/`anthropic`), la consulta puede resolverse
    invocando esas herramientas en un loop acotado; ese path no soporta
    streaming (se pierde `on_chunk`), así que se avisa una vez vía
    `on_status` antes de bloquear hasta la respuesta final. Sin tools
    conectadas, o con Ollama, el comportamiento es exactamente el de antes.
    """
    config = get_active_model_config()
    manager = get_mcp_manager()
    tools = manager.list_tools() if manager.is_started() else []

    if tools and config["provider"] in MCP_TOOL_CALLING_PROVIDERS:
        if on_status is not None:
            on_status("Consultando herramientas MCP...")
        system_prompt = ANSWER_PROMPT_TEMPLATE.format(
            provider=config["provider"],
            model=config["model"],
            governance=governance or "(no se encontró AGENT.md en este repositorio)",
            memory_context=memory_context,
            workspace_context=workspace_context or "(no se cargó el contexto de archivos)",
        )
        if config["provider"] == "gemini":
            return _answer_with_tools_gemini(instruction, system_prompt, config["model"], tools, manager).strip()
        return _answer_with_tools_anthropic(instruction, system_prompt, config["model"], tools, manager).strip()

    raw = _complete(
        ANSWER_PROMPT_TEMPLATE,
        instruction,
        governance,
        memory_context,
        workspace_context,
        json_mode=False,
        on_chunk=on_chunk,
    )
    return raw.strip()