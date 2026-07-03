from dataclasses import dataclass, field
from typing import Any


@dataclass
class LoadedInputs:
    payloads: dict[str, Any]
    requirements: dict[str, Any]
    style_assets: dict[str, Any]


@dataclass
class SectionOutput:
    section_key: str
    markdown: str
    score: float | None = None
    status: str = "generated"
    revision_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationWarningData:
    stage: str
    warning_type: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationResult:
    final_markdown: str
    sections: dict[str, SectionOutput]
    warnings: list[GenerationWarningData]
    artifacts: dict[str, Any] = field(default_factory=dict)
    final_summary: dict[str, Any] = field(default_factory=dict)