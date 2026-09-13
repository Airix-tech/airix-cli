# src/airix_cli/ast_engine/cache.py
import json
from pathlib import Path
from airix_cli.ast_engine.hashing import sha256_of
from airix_cli.ast_engine.parser import parse_ts_file

CACHE_PATH = Path(".airix/ast_cache.json")


def load_cache() -> dict:
    if not CACHE_PATH.exists():
        return {}
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # Un caché corrupto solo cuesta un reanálisis; no debe romper el comando.
        return {}
    return data if isinstance(data, dict) else {}


def save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def analyze_file(path: Path, cache: dict) -> tuple[dict, bool]:
    """Devuelve (símbolos, hubo_reanalisis)."""
    key = str(path)
    current_hash = sha256_of(path)
    entry = cache.get(key)

    if isinstance(entry, dict) and entry.get("hash") == current_hash and "symbols" in entry:
        return entry["symbols"], False  # sin cambios → se omite el análisis

    symbols = parse_ts_file(path)
    cache[key] = {"hash": current_hash, "symbols": symbols}
    return symbols, True
