from dataclasses import dataclass


@dataclass(frozen=True)
class GenerationConfig:
    output_formats: list[str]
    max_revisions: int = 2
    final_failures_as_warnings: bool = True
    strict_missing_data_policy: bool = False


DEFAULT_SECTION_KEYS = [
    "general_requirements",
    "governance",
    "strategy",
    "risk_management",
    "metrics_targets",
]


SECTION_TITLES = {
    "general_requirements": "General Requirements",
    "governance": "Governance",
    "strategy": "Strategy",
    "risk_management": "Risk Management",
    "metrics_targets": "Metrics and Targets",
}