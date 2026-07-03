class GenerationEngineError(Exception):
    """Base exception for the report generation engine."""


class PayloadLoadingError(GenerationEngineError):
    """Raised when payloads cannot be loaded or parsed."""


class RequirementsLoadingError(GenerationEngineError):
    """Raised when IFRS requirements cannot be loaded."""


class StyleLoadingError(GenerationEngineError):
    """Raised when style assets cannot be loaded."""


class EvidenceMappingError(GenerationEngineError):
    """Raised when evidence maps cannot be built."""


class SectionGenerationError(GenerationEngineError):
    """Raised when report section generation fails."""


class ValidationError(GenerationEngineError):
    """Raised when validation logic fails unexpectedly."""


class ReportAssemblyError(GenerationEngineError):
    """Raised when the final report cannot be assembled."""