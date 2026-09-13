# src/airix_cli/memory/schema.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Literal

class ArchitecturalProfile(BaseModel):
    language: str | None = None
    frameworks: list[str] = Field(default_factory=list)
    detected_patterns: list[str] = Field(default_factory=list)  # ej. "hexagonal", "MVC"
    entrypoints: list[str] = Field(default_factory=list)
    test_command: str | None = None  # ej. "pytest -q", "npm test"
    last_scanned: datetime | None = None

class TechnicalDecision(BaseModel):
    timestamp: datetime
    summary: str
    rationale: str
    affected_files: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

class ResolvedError(BaseModel):
    timestamp: datetime
    error_signature: str        # hash o mensaje normalizado del error
    root_cause: str
    solution: str
    affected_files: list[str] = Field(default_factory=list)

class MemoryFile(BaseModel):
    schema_version: Literal[1] = 1
    profile: ArchitecturalProfile = Field(default_factory=ArchitecturalProfile)
    decisions: list[TechnicalDecision] = Field(default_factory=list)
    resolved_errors: list[ResolvedError] = Field(default_factory=list)