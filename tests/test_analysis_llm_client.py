"""Tests for LLM client abstraction layer."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from src.core.config import LLMConfig


class TestCacheKey:
    """Tests for the _cache_key helper function."""

    def test_deterministic(self):
        from src.analysis.llm_client import _cache_key

        key1 = _cache_key("prompt", "system")
        key2 = _cache_key("prompt", "system")
        assert key1 == key2

    def test_different_prompts_differ(self):
        from src.analysis.llm_client import _cache_key

        key1 = _cache_key("prompt_a", "system")
        key2 = _cache_key("prompt_b", "system")
        assert key1 != key2

    def test_different_system_prompts_differ(self):
        from src.analysis.llm_client import _cache_key

        key1 = _cache_key("prompt", "system_a")
        key2 = _cache_key("prompt", "system_b")
        assert key1 != key2


class TestLLMClientGenerate:
    """Tests for the LLMClient.generate caching behavior."""

    def test_cache_hit_returns_cached_value(self):
        from src.analysis.llm_client import LLMClient

        config = LLMConfig(provider="claude", model="test-model")

        class StubClient(LLMClient):
            @property
            def name(self) -> str:
                return "stub"

            def is_available(self) -> bool:
                return True

            def _call_api(self, prompt: str, system_prompt: str) -> tuple[str, int]:
                return "response", 100

        client = StubClient(config)

        # First call populates cache
        text1, tokens1 = client.generate("hello", "sys")
        assert text1 == "response"
        assert tokens1 == 100

        # Second call returns from cache with 0 tokens
        text2, tokens2 = client.generate("hello", "sys")
        assert text2 == "response"
        assert tokens2 == 0

    def test_different_prompts_call_api_again(self):
        from src.analysis.llm_client import LLMClient

        config = LLMConfig(provider="claude", model="test-model")
        call_count = 0

        class CountingClient(LLMClient):
            @property
            def name(self) -> str:
                return "counting"

            def is_available(self) -> bool:
                return True

            def _call_api(self, prompt: str, system_prompt: str) -> tuple[str, int]:
                nonlocal call_count
                call_count += 1
                return f"response_{call_count}", 50

        client = CountingClient(config)
        client.generate("a", "sys")
        client.generate("b", "sys")
        assert call_count == 2


class TestClaudeClient:
    """Tests for ClaudeClient."""

    def test_is_available_with_env(self):
        from src.analysis.llm_client import ClaudeClient

        config = LLMConfig(provider="claude", model="claude-sonnet-4-6")
        client = ClaudeClient(config)

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            assert client.is_available() is True

    def test_is_not_available_without_env(self):
        from src.analysis.llm_client import ClaudeClient

        config = LLMConfig(provider="claude", model="claude-sonnet-4-6")
        client = ClaudeClient(config)

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            assert client.is_available() is False

    def test_name(self):
        from src.analysis.llm_client import ClaudeClient

        config = LLMConfig(provider="claude", model="claude-sonnet-4-6")
        client = ClaudeClient(config)
        assert client.name == "claude"


class TestOpenAIClient:
    """Tests for OpenAIClient."""

    def test_is_available_with_env(self):
        from src.analysis.llm_client import OpenAIClient

        config = LLMConfig(provider="openai", model="gpt-4")
        client = OpenAIClient(config)

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            assert client.is_available() is True

    def test_name(self):
        from src.analysis.llm_client import OpenAIClient

        config = LLMConfig(provider="openai", model="gpt-4")
        client = OpenAIClient(config)
        assert client.name == "openai"


class TestCreateLLMClient:
    """Tests for the factory function."""

    def test_unknown_provider_rejected_by_config(self):
        """LLMConfig validation rejects unknown providers."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="provider"):
            LLMConfig(provider="unknown", model="test")

    def test_missing_api_key_raises(self):
        from src.analysis.llm_client import create_llm_client

        config = LLMConfig(provider="claude", model="claude-sonnet-4-6")
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            with pytest.raises(ValueError, match="not available"):
                create_llm_client(config)

    def test_claude_created_successfully(self):
        from src.analysis.llm_client import ClaudeClient, create_llm_client

        config = LLMConfig(provider="claude", model="claude-sonnet-4-6")
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = create_llm_client(config)
            assert isinstance(client, ClaudeClient)
