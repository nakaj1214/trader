"""LLM client abstraction for financial analysis.

Provides a pluggable interface for Claude and OpenAI backends,
with retry logic, caching, and token usage logging.
"""

from __future__ import annotations

import hashlib
import os
from abc import ABC, abstractmethod

import structlog
from cachetools import TTLCache
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.core.config import LLMConfig

logger = structlog.get_logger(__name__)

_llm_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
    reraise=True,
)


def _cache_key(prompt: str, system_prompt: str) -> str:
    """Generate a deterministic cache key from prompt content."""
    combined = f"{system_prompt}|||{prompt}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


class LLMClient(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, config: LLMConfig, cache_ttl: int = 3600) -> None:
        self._config = config
        self._cache: TTLCache[str, str] = TTLCache(maxsize=128, ttl=cache_ttl)

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the provider is configured and reachable."""

    @abstractmethod
    def _call_api(self, prompt: str, system_prompt: str) -> tuple[str, int]:
        """Call the LLM API and return (response_text, token_count)."""

    def generate(self, prompt: str, system_prompt: str = "") -> tuple[str, int]:
        """Generate a response from the LLM with caching.

        Args:
            prompt: The user prompt to send.
            system_prompt: Optional system prompt for role setting.

        Returns:
            Tuple of (response_text, token_count).
        """
        key = _cache_key(prompt, system_prompt)
        cached = self._cache.get(key)
        if cached is not None:
            logger.debug("llm_cache_hit", provider=self.name)
            return cached, 0

        response, token_count = self._call_api(prompt, system_prompt)
        self._cache[key] = response

        logger.info(
            "llm_call_complete",
            provider=self.name,
            model=self._config.model,
            token_count=token_count,
        )
        return response, token_count


class ClaudeClient(LLMClient):
    """Claude API client using the Anthropic SDK."""

    @property
    def name(self) -> str:
        return "claude"

    def is_available(self) -> bool:
        """Check if ANTHROPIC_API_KEY is set."""
        return bool(os.environ.get("ANTHROPIC_API_KEY"))

    @_llm_retry
    def _call_api(self, prompt: str, system_prompt: str) -> tuple[str, int]:
        """Call the Claude API."""
        import anthropic

        client = anthropic.Anthropic()
        kwargs: dict = {
            "model": self._config.model,
            "max_tokens": self._config.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        if self._config.temperature > 0:
            kwargs["temperature"] = self._config.temperature

        response = client.messages.create(**kwargs)
        text = response.content[0].text
        token_count = response.usage.input_tokens + response.usage.output_tokens
        return text, token_count


class OpenAIClient(LLMClient):
    """OpenAI API client."""

    @property
    def name(self) -> str:
        return "openai"

    def is_available(self) -> bool:
        """Check if OPENAI_API_KEY is set."""
        return bool(os.environ.get("OPENAI_API_KEY"))

    @_llm_retry
    def _call_api(self, prompt: str, system_prompt: str) -> tuple[str, int]:
        """Call the OpenAI API."""
        try:
            import openai
        except ImportError as exc:
            raise ImportError(
                "openai package is required for OpenAI provider. "
                "Install with: pip install trader[openai]"
            ) from exc

        client = openai.OpenAI()
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model=self._config.model,
            messages=messages,
            max_tokens=self._config.max_tokens,
            temperature=self._config.temperature,
        )
        text = response.choices[0].message.content or ""
        token_count = response.usage.total_tokens if response.usage else 0
        return text, token_count


def create_llm_client(config: LLMConfig) -> LLMClient:
    """Factory function to create the appropriate LLM client.

    Args:
        config: LLM configuration specifying provider and model.

    Returns:
        An LLMClient instance for the configured provider.

    Raises:
        ValueError: If the provider is not available (API key missing).
    """
    clients: dict[str, type[LLMClient]] = {
        "claude": ClaudeClient,
        "openai": OpenAIClient,
    }

    client_cls = clients.get(config.provider)
    if client_cls is None:
        raise ValueError(f"Unknown LLM provider: '{config.provider}'")

    client = client_cls(config)
    if not client.is_available():
        env_var = "ANTHROPIC_API_KEY" if config.provider == "claude" else "OPENAI_API_KEY"
        raise ValueError(
            f"LLM provider '{config.provider}' is not available. "
            f"Set the {env_var} environment variable."
        )

    return client
