"""Tests for lazy provider exports from mlpcopilot.providers."""

from __future__ import annotations

import importlib
import sys


def test_importing_providers_package_is_lazy(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "mlpcopilot.providers", raising=False)
    monkeypatch.delitem(sys.modules, "mlpcopilot.providers.anthropic_provider", raising=False)
    monkeypatch.delitem(sys.modules, "mlpcopilot.providers.openai_compat_provider", raising=False)
    monkeypatch.delitem(sys.modules, "mlpcopilot.providers.openai_codex_provider", raising=False)
    monkeypatch.delitem(sys.modules, "mlpcopilot.providers.github_copilot_provider", raising=False)
    monkeypatch.delitem(sys.modules, "mlpcopilot.providers.azure_openai_provider", raising=False)
    monkeypatch.delitem(sys.modules, "mlpcopilot.providers.bedrock_provider", raising=False)

    providers = importlib.import_module("mlpcopilot.providers")

    assert "mlpcopilot.providers.anthropic_provider" not in sys.modules
    assert "mlpcopilot.providers.openai_compat_provider" not in sys.modules
    assert "mlpcopilot.providers.openai_codex_provider" not in sys.modules
    assert "mlpcopilot.providers.github_copilot_provider" not in sys.modules
    assert "mlpcopilot.providers.azure_openai_provider" not in sys.modules
    assert "mlpcopilot.providers.bedrock_provider" not in sys.modules
    assert providers.__all__ == [
        "LLMProvider",
        "LLMResponse",
        "AnthropicProvider",
        "OpenAICompatProvider",
        "OpenAICodexProvider",
        "GitHubCopilotProvider",
        "AzureOpenAIProvider",
        "BedrockProvider",
    ]


def test_explicit_provider_import_still_works(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "mlpcopilot.providers", raising=False)
    monkeypatch.delitem(sys.modules, "mlpcopilot.providers.anthropic_provider", raising=False)

    namespace: dict[str, object] = {}
    exec("from mlpcopilot.providers import AnthropicProvider", namespace)

    assert namespace["AnthropicProvider"].__name__ == "AnthropicProvider"
    assert "mlpcopilot.providers.anthropic_provider" in sys.modules


def test_openai_codex_supports_progress_deltas() -> None:
    from mlpcopilot.providers.openai_codex_provider import OpenAICodexProvider

    assert OpenAICodexProvider.supports_progress_deltas is True
