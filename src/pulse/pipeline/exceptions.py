"""Pipeline exceptions."""


class PipelineError(Exception):
    """Base class for reasoning pipeline errors."""


class EmptyCorpusError(PipelineError):
    """Raised when no reviews remain after scrubbing."""


class ClusteringError(PipelineError):
    """Raised when clustering cannot produce themes."""


class LlmBudgetExceededError(PipelineError):
    """Raised when Groq token or request limits would be exceeded."""


class GroqApiError(PipelineError):
    """Raised when Groq API calls fail after retries."""


class MissingGroqApiKeyError(PipelineError):
    """Raised when GROQ_API_KEY is required but not set."""
