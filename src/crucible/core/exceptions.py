class CrucibleError(Exception):
    """Base exception for Crucible."""


class ProviderError(CrucibleError):
    """Raised when a model provider cannot complete a request."""


class BudgetExhausted(CrucibleError):
    """Raised when an optimization run exceeds its configured budget."""


class InvalidRefinement(CrucibleError):
    """Raised when a refiner returns an unusable prompt proposal."""
