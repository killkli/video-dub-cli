class ProjectError(Exception):
    """Base project exception."""


class BackendUnavailableError(ProjectError):
    """Raised when an optional backend dependency is unavailable."""


class InputValidationError(ProjectError):
    """Raised when a user-provided input path or option is invalid."""


class ASRProcessingError(ProjectError):
    """Raised when the ASR backend fails during transcription."""
