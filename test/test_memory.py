# tests/test_memory.py
from datetime import datetime, timezone

from airix_cli.memory.schema import MemoryFile, TechnicalDecision, ResolvedError
from airix_cli.memory.store import save_memory, load_memory, append_decision, append_resolved_error


def test_memory_file_roundtrip(tmp_path):
    path = tmp_path / "memory.json"
    mem = MemoryFile()
    mem.decisions.append(
        TechnicalDecision(
            timestamp=datetime.now(timezone.utc),
            summary="Se eligió arquitectura hexagonal",
            rationale="Facilita testear sin infraestructura real",
            affected_files=["src/app.py"],
        )
    )
    save_memory(path, mem)

    loaded = load_memory(path)
    assert loaded.decisions[0].summary == "Se eligió arquitectura hexagonal"
    assert loaded.decisions[0].affected_files == ["src/app.py"]


def test_load_memory_initializes_if_missing(tmp_path):
    path = tmp_path / "subdir_no_existe" / "memory.json"
    path.parent.mkdir(parents=True)
    mem = load_memory(path)
    assert mem.schema_version == 1
    assert mem.decisions == []


def test_append_decision(tmp_path):
    path = tmp_path / "memory.json"
    append_decision(
        path,
        TechnicalDecision(
            timestamp=datetime.now(timezone.utc),
            summary="test",
            rationale="porque sí",
        ),
    )
    mem = load_memory(path)
    assert len(mem.decisions) == 1
    assert mem.decisions[0].summary == "test"


def test_append_resolved_error(tmp_path):
    path = tmp_path / "memory.json"
    append_resolved_error(
        path,
        ResolvedError(
            timestamp=datetime.now(timezone.utc),
            error_signature="TypeError: xyz",
            root_cause="Tipo incorrecto en el parámetro",
            solution="Se agregó validación de tipos",
        ),
    )
    mem = load_memory(path)
    assert len(mem.resolved_errors) == 1
    assert mem.resolved_errors[0].root_cause == "Tipo incorrecto en el parámetro"