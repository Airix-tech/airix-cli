# src/airix_cli/commands/init.py
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import typer

from airix_cli.memory.store import init_memory_file, load_memory, save_memory
from airix_cli.memory.schema import ArchitecturalProfile

AGENT_MD_TEMPLATE = """\
# AGENT.md — Gobernanza operativa

## Alcance
Este agente opera exclusivamente dentro de este repositorio. No debe
modificar archivos fuera de la raíz del proyecto ni acceder a secretos
fuera de `.env` declarados explícitamente.

## Restricciones de seguridad
- Prohibido ejecutar comandos de red no aprobados (curl, wget) sin confirmación.
- Prohibido eliminar directorios `.git`, `.airix`, o archivos de configuración
  de CI sin aprobación explícita del usuario.
- Toda modificación de código debe pasar por el flujo `.tmp/` → tests → REPL.
- Prohibido escribir fragmentos parciales de archivo: todo archivo propuesto
  debe entregarse íntegro.

## Convenciones del proyecto
{project_conventions}

## Memoria
Antes de proponer cambios, este agente debe leer `.airix/memory.json` y
respetar las decisiones técnicas históricas allí registradas.
"""

IGNORED_DIRS = {".git", ".airix", ".tmp", "node_modules", ".venv", "__pycache__", "dist", "build"}

LANGUAGE_BY_EXTENSION = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".rb": "Ruby",
}

JS_FRAMEWORK_DEPS = ["react", "vue", "next", "express", "fastify", "@nestjs/core", "svelte"]
PY_FRAMEWORK_HINTS = ["fastapi", "django", "flask", "typer"]


def _detect_language(root: Path) -> str | None:
    # Solo cuenta extensiones de código fuente conocidas (LANGUAGE_BY_EXTENSION);
    # de lo contrario, archivos de metadata como package.json, .lock, .md, etc.
    # compiten por el conteo y pueden "ganar" el lenguaje dominante por error.
    ext_counter: Counter[str] = Counter()
    for f in root.rglob("*"):
        if (
            f.is_file()
            and f.suffix in LANGUAGE_BY_EXTENSION
            and not any(part in IGNORED_DIRS for part in f.parts)
        ):
            ext_counter[f.suffix] += 1
    if not ext_counter:
        return None
    top_ext, _ = ext_counter.most_common(1)[0]
    return LANGUAGE_BY_EXTENSION[top_ext]


def _detect_frameworks(root: Path) -> list[str]:
    frameworks: set[str] = set()

    pkg_json = root / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            frameworks.update(fw for fw in JS_FRAMEWORK_DEPS if fw in deps)
        except (json.JSONDecodeError, OSError):
            pass

    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text(encoding="utf-8")
        frameworks.update(fw for fw in PY_FRAMEWORK_HINTS if fw in content)

    if (root / "go.mod").exists():
        frameworks.add("Go modules")
    if (root / "Cargo.toml").exists():
        frameworks.add("Cargo (Rust)")
    if (root / "Gemfile").exists():
        frameworks.add("Bundler (Ruby)")

    return sorted(frameworks)


def _detect_test_command(root: Path) -> str | None:
    if (root / "pyproject.toml").exists() and ((root / "tests").is_dir() or (root / "test").is_dir()):
        return "pytest -q"
    pkg_json = root / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
            if "test" in pkg.get("scripts", {}):
                return "npm test"
        except (json.JSONDecodeError, OSError):
            pass
    if (root / "go.mod").exists():
        return "go test ./..."
    if (root / "Cargo.toml").exists():
        return "cargo test"
    return None


def detect_architectural_profile(root: Path) -> ArchitecturalProfile:
    return ArchitecturalProfile(
        language=_detect_language(root),
        frameworks=_detect_frameworks(root),
        entrypoints=[],
        test_command=_detect_test_command(root),
        last_scanned=datetime.now(timezone.utc),
    )


def init_repo() -> None:
    """Inicializa .airix/, detecta el perfil arquitectónico y crea AGENT.md."""
    root = Path.cwd()
    airix_dir = root / ".airix"
    airix_dir.mkdir(exist_ok=True)
    (airix_dir / "checkpoints").mkdir(exist_ok=True)

    memory_path = airix_dir / "memory.json"
    init_memory_file(memory_path)

    profile = detect_architectural_profile(root)
    mem = load_memory(memory_path)
    mem.profile = profile
    save_memory(memory_path, mem)

    if profile.language:
        conventions = f"Lenguaje detectado: {profile.language}."
        if profile.frameworks:
            conventions += f" Frameworks: {', '.join(profile.frameworks)}."
        if profile.test_command:
            conventions += f" Comando de tests: `{profile.test_command}`."
    else:
        conventions = "(no se detectó un lenguaje dominante; completar manualmente)"

    agent_md = root / "AGENT.md"
    if not agent_md.exists():
        agent_md.write_text(
            AGENT_MD_TEMPLATE.format(project_conventions=conventions), encoding="utf-8"
        )

    (airix_dir / "ast_cache.json").write_text("{}", encoding="utf-8")
    (airix_dir / "session.json").write_text("[]", encoding="utf-8")

    typer.secho("✔ Repositorio inicializado: AGENT.md + .airix/", fg=typer.colors.GREEN)
    if profile.language:
        typer.echo(f"  Perfil detectado: {profile.language}" + (f" ({', '.join(profile.frameworks)})" if profile.frameworks else ""))
    if profile.test_command:
        typer.echo(f"  Comando de tests: {profile.test_command}")
