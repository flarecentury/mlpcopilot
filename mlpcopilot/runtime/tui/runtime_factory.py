"""Runtime construction helpers for the interactive TUI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mlpcopilot.providers.base import LLMProvider, LLMResponse
from mlpcopilot.runtime.tui.common import _provider_unavailable_message


class TuiUnavailableProvider(LLMProvider):
    """Provider used when the TUI starts before model credentials are configured."""

    def __init__(self, model: str, reason: str):
        super().__init__(api_key=None, api_base=None)
        self._model = model
        self.reason = reason

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> LLMResponse:
        return LLMResponse(content=_provider_unavailable_message(self.reason))

    def get_default_model(self) -> str:
        return self._model


@dataclass(frozen=True, slots=True)
class TuiRuntimeBundle:
    agent_loop: Any
    provider_notice: str | None = None
    provider_notice_reason: str | None = None


def build_tui_agent_loop(
    *,
    config: Any,
    provider: LLMProvider | None,
    provider_error: str | None = None,
) -> TuiRuntimeBundle:
    """Build the AgentLoop and provider fallback used by the TUI."""
    from mlpcopilot.agent.loop import AgentLoop
    from mlpcopilot.bus.queue import MessageBus
    from mlpcopilot.cron.service import CronService

    provider_notice = None
    provider_notice_reason = None
    if provider is None:
        provider_notice_reason = provider_error or "No model provider is configured."
        provider = TuiUnavailableProvider(config.agents.defaults.model, provider_notice_reason)
        provider_notice = _provider_unavailable_message(provider_notice_reason)

    bus = MessageBus()
    cron = CronService(config.workspace_path / "cron" / "jobs.json")
    agent_loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.agents.defaults.model,
        max_iterations=config.agents.defaults.max_tool_iterations,
        context_window_tokens=config.agents.defaults.context_window_tokens,
        web_config=config.tools.web,
        context_block_limit=config.agents.defaults.context_block_limit,
        max_tool_result_chars=config.agents.defaults.max_tool_result_chars,
        provider_retry_mode=config.agents.defaults.provider_retry_mode,
        exec_config=config.tools.exec,
        cron_service=cron,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        mcp_servers=config.tools.mcp_servers,
        channels_config=config.channels,
        timezone=config.agents.defaults.timezone,
        unified_session=config.agents.defaults.unified_session,
        disabled_skills=config.agents.defaults.disabled_skills,
        session_ttl_minutes=config.agents.defaults.session_ttl_minutes,
        consolidation_ratio=config.agents.defaults.consolidation_ratio,
        max_messages=config.agents.defaults.max_messages,
        tools_config=config.tools,
        runtime_config=config,
    )
    return TuiRuntimeBundle(
        agent_loop=agent_loop,
        provider_notice=provider_notice,
        provider_notice_reason=provider_notice_reason,
    )
