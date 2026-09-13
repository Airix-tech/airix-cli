import subprocess
from pathlib import Path


class GitReviewError(RuntimeError):
    pass


def _git(repo_root: Path, *args: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise GitReviewError(detail or f"git {' '.join(args)} falló")
    return result.stdout.strip()


def stage_for_visual_review(repo_root: Path, proposed_files: list[Path]) -> None:
    """Stage files locally for VS Code review without creating a commit or using a remote."""
    try:
        _git(repo_root, "rev-parse", "--git-dir")
    except GitReviewError as exc:
        raise GitReviewError("La revisión visual requiere un repositorio Git.") from exc

    repo_root = repo_root.resolve()
    for proposed_file in proposed_files:
        try:
            relative = proposed_file.resolve().relative_to(repo_root)
        except ValueError as exc:
            raise GitReviewError(
                f"'{proposed_file}' está fuera del repositorio {repo_root}; no se puede indexar."
            ) from exc
        _git(repo_root, "add", "--", relative.as_posix())