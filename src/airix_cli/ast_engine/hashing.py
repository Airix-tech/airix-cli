# src/airix_cli/ast_engine/hashing.py
import hashlib
from pathlib import Path

def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()