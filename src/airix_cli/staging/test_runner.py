# src/airix_cli/staging/test_runner.py
import shutil
import subprocess
import tempfile
from pathlib import Path

def run_tests_against_staging(repo_root: Path, tmp_dir: Path, test_command: list[str]) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as shadow:
        shadow_path = Path(shadow)
        # 1. Copiar el repo real (excluyendo .git, .airix, .tmp, venv, node_modules...)
        shutil.copytree(
            repo_root, shadow_path, dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(".git", ".airix", ".tmp", "node_modules", ".venv"),
        )
        # 2. Superponer los archivos propuestos en .tmp/
        for f in tmp_dir.rglob("*"):
            if f.is_file():
                rel = f.relative_to(tmp_dir)
                dest = shadow_path / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)
        # 3. Ejecutar la suite real del proyecto en el overlay
        return subprocess.run(test_command, cwd=shadow_path, capture_output=True, text=True)