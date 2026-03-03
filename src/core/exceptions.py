"""Custom exception hierarchy for the trader project."""


class TraderError(Exception):
    """Base exception for all trader errors."""


class ConfigError(TraderError):
    """Configuration loading or validation error."""


class DataProviderError(TraderError):
    """Data provider fetch or connection error."""


class PredictionError(TraderError):
    """Prediction model training or inference error."""


class PersistenceError(TraderError):
    """Database or storage operation error."""


class EnrichmentError(TraderError):
    """Enrichment processing error."""


class NotificationError(TraderError):
    """Notification sending error."""
