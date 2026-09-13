# src/airix_cli/context/compactor.py
import json
import re
from pathlib import Path
from datetime import datetime, timezone

import tiktoken

from airix_cli.memory.store import append_decision
from airix_cli.memory.schema import TechnicalDecision

SESSION_PATH = Path(".airix/session.json")
REPL_HISTORY_PATH = Path(".airix/repl_history")
TOKEN_THRESHOLD = 100_000  # ajustable según el modelo usado

_encoder = None
_encoder_unavailable = False


def _get_encoder():
    """
    Carga perezosa del encoder de tiktoken, cacheada tras el primer intento.
    tiktoken descarga el archivo BPE de internet la primera vez que se pide
    un encoding; si no hay red (entorno corporativo, air-gapped, proxy que
    bloquea el dominio), esto lanza una excepción. En vez de reintentar la
    descarga en cada turno del REPL, se recuerda el fallo y se cae a una
    aproximación por caracteres.
    """
    global _encoder, _encoder_unavailable
    if _encoder is not None or _encoder_unavailable:
        return _encoder
    try:
        _encoder = tiktoken.get_encoding("cl100k_base")
    except Exception:
        _encoder_unavailable = True
    return _encoder


def _content_of(message: dict) -> str:
    """El contenido de un mensaje compactado puede ser un dict serializado."""
    content = message.get("content", "")
    return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)


def count_tokens(messages: list[dict]) -> int:
    enc = _get_encoder()
    contents = [_content_of(m) for m in messages]
    if enc is None:
        return sum(len(c) for c in contents) // 4
    return sum(len(enc.encode(c)) for c in contents)


def load_session() -> list[dict]:
    if not SESSION_PATH.exists():
        return []
    try:
        data = json.loads(SESSION_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # Una sesión corrupta no debe impedir arrancar el REPL.
        return []
    return data if isinstance(data, list) else []


def save_session(messages: list[dict]) -> None:
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    SESSION_PATH.write_text(json.dumps(messages, indent=2, ensure_ascii=False), encoding="utf-8")


def should_compact(messages: list[dict]) -> bool:
    return count_tokens(messages) >= TOKEN_THRESHOLD


def _extract_paths(text: str) -> list[str]:
    matches = re.findall(r"(?:src|tests|app|lib|packages|root)[A-Za-z0-9_./\\-]+(?:\.py|\.ts|\.tsx|\.js|\.jsx)", text)
    return sorted({m.replace('\\', '/') for m in matches})


def _extract_issues(text: str) -> list[str]:
    issues: list[str] = []
    for pattern in [r"(?:TypeError|ValueError|AttributeError|ImportError|NameError|SyntaxError)[^\n]+", r"error[^\n]+", r"fall[oa][^\n]+"]:
        for match in re.findall(pattern, text, flags=re.IGNORECASE):
            cleaned = match.strip()
            if cleaned and cleaned not in issues:
                issues.append(cleaned)
    return issues[:5]


def _infer_decisions(messages: list[dict]) -> list[str]:
    decisions: list[str] = []
    for message in messages:
        text = _content_of(message)
        if any(keyword in text.lower() for keyword in ["decisión", "decision", "usar", "elegir", "cambiar", "refactor", "cache", "resolver", "aplicar", "persist"]):
            if "?" not in text and len(text.strip()) > 10:
                decisions.append(text.strip())
    return decisions[:5]


def _extract_active_tasks(messages: list[dict]) -> list[str]:
    tasks: list[str] = []
    for message in messages:
        text = _content_of(message)
        if any(keyword in text.lower() for keyword in ["arreglar", "revisar", "refactorizar", "resolver", "mejorar", "implementar", "agregar", "corregir"]):
            tasks.append(text.strip())
    return tasks[:5]


def build_session_summary(messages: list[dict]) -> dict:
    """Construye un resumen estructurado útil para continuidad de sesión."""
    text = "\n".join(_content_of(m) for m in messages if m.get("role") != "system")
    decisions = _infer_decisions(messages)
    issues = _extract_issues(text)
    paths = _extract_paths(text)
    tasks = _extract_active_tasks(messages)

    summary = {
        "summary": text[:4000],
        "key_decisions": decisions,
        "active_tasks": tasks,
        "unresolved_issues": issues,
        "affected_files": paths,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }
    return summary


def summarize_with_llm(messages: list[dict]) -> dict:
    """
    Resumen de sesión usando el LLM activo en vez de la heurística por
    palabras clave de `build_session_summary`: entiende el texto en lugar de
    solo buscar coincidencias literales de "TypeError" o "decisión".

    El import de `agent.client` es perezoso a propósito: así este módulo
    sigue siendo puro y sin llamadas de red por defecto (lo que exige
    `compact_session`, y de lo que dependen sus tests), y solo paga el costo
    de la dependencia cuando alguien realmente pide un resumen por LLM.
    """
    from airix_cli.agent.client import summarize_conversation

    return summarize_conversation(messages)


def summarize_session(messages: list[dict]) -> dict:
    """
    Summarizer por defecto para las invocaciones reales de `compact_session`
    (REPL y `airix compact`): intenta un resumen inteligente vía LLM y, si el
    proveedor no está disponible o devuelve algo inválido, cae a la heurística
    por palabras clave en vez de perder la compactación por completo.
    """
    try:
        return summarize_with_llm(messages)
    except Exception:
        return build_session_summary(messages)


def clear_repl_history(history_path: Path = REPL_HISTORY_PATH) -> None:
    """Borra el historial de instrucciones del REPL (↑/↓, Ctrl+R)."""
    try:
        history_path.unlink()
    except FileNotFoundError:
        pass


def compact_session(
    memory_path: Path = Path(".airix/memory.json"),
    summarizer=None,
    *,
    clear_history: bool = True,
) -> None:
    """Genera un resumen estructurado y lo guarda como contenido de sesión."""
    messages = load_session()
    if not messages:
        return

    if summarizer is None:
        summary = build_session_summary(messages)
        key_decisions = summary["key_decisions"]
    else:
        summary = summarizer(messages)
        key_decisions = summary.get("key_decisions", [])

    for decision in key_decisions:
        append_decision(
            memory_path,
            TechnicalDecision(
                timestamp=datetime.now(timezone.utc),
                summary=decision,
                rationale="Extraído automáticamente durante compactación de contexto",
                affected_files=summary.get("affected_files", []),
            ),
        )

    save_session([
        {
            "role": "system",
            "content": json.dumps(summary, ensure_ascii=False, indent=2),
        }
    ])

    if clear_history:
        clear_repl_history(memory_path.parent / "repl_history")
