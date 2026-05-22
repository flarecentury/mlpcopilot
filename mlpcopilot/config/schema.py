"""Configuration schema using Pydantic."""

from pathlib import Path
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel
from pydantic_settings import BaseSettings

from mlpcopilot.cron.types import CronSchedule
from mlpcopilot.runtime.profiles import MLPCOPILOT_PROFILE, apply_runtime_profile_defaults

RuntimeProfile = Literal["default", "mlpcopilot"]


class Base(BaseModel):
    """Base model that accepts both camelCase and snake_case keys."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

class ChannelsConfig(Base):
    """Configuration for chat channels.

    Built-in and plugin channel configs are stored as extra fields (dicts).
    Each channel parses its own config in __init__.
    Per-channel "streaming": true enables streaming output (requires send_delta impl).
    """

    model_config = ConfigDict(extra="allow")

    send_progress: bool = True  # stream agent's text progress to the channel
    send_tool_hints: bool = False  # stream tool-call hints (e.g. read_file("…"))
    send_max_retries: int = Field(default=3, ge=0, le=10)  # Max delivery attempts (initial send included)
    transcription_provider: str = "groq"  # Voice transcription backend: "groq" or "openai"
    transcription_language: str | None = Field(default=None, pattern=r"^[a-z]{2,3}$")  # Optional ISO-639-1 hint for audio transcription


class DreamConfig(Base):
    """Dream memory consolidation configuration."""

    _HOUR_MS = 3_600_000

    interval_h: int = Field(default=2, ge=1)  # Every 2 hours by default
    cron: str | None = Field(default=None, exclude=True)  # Legacy compatibility override
    model_override: str | None = Field(
        default=None,
        validation_alias=AliasChoices("modelOverride", "model", "model_override"),
    )  # Optional Dream-specific model override
    max_batch_size: int = Field(default=20, ge=1)  # Max history entries per run
    # Bumped from 10 to 15 in #3212 (exp002: +30% dedup, no accuracy loss; >15 plateaus).
    max_iterations: int = Field(default=15, ge=1)  # Max tool calls per Phase 2
    # Per-line git-blame age annotation in Phase 1 prompt (see #3212). Default
    # on — set to False to feed MEMORY.md raw if a specific LLM reacts poorly
    # to the `← Nd` suffix or you want deterministic, git-independent prompts.
    annotate_line_ages: bool = True
    approval_required: bool = Field(
        default=False,
        validation_alias=AliasChoices("approvalRequired", "approval_required"),
    )  # Require ApprovalManager approval before Dream writes long-term memory/skills

    def build_schedule(self, timezone: str) -> CronSchedule:
        """Build the runtime schedule, preferring the legacy cron override if present."""
        if self.cron:
            return CronSchedule(kind="cron", expr=self.cron, tz=timezone)
        return CronSchedule(kind="every", every_ms=self.interval_h * self._HOUR_MS)

    def describe_schedule(self) -> str:
        """Return a human-readable summary for logs and startup output."""
        if self.cron:
            return f"cron {self.cron} (legacy)"
        hours = self.interval_h
        return f"every {hours}h"


class AgentDefaults(Base):
    """Default agent configuration."""

    workspace: str = "~/.mlpcopilot/workspace"
    model: str = "anthropic/claude-opus-4-5"
    provider: str = (
        "auto"  # Provider name (e.g. "anthropic", "openrouter") or "auto" for auto-detection
    )
    max_tokens: int = 8192
    context_window_tokens: int = 65_536
    context_block_limit: int | None = None
    temperature: float = 0.1
    max_tool_iterations: int = 200
    max_tool_result_chars: int = 16_000
    provider_retry_mode: Literal["standard", "persistent"] = "standard"
    reasoning_effort: str | None = None  # low / medium / high / adaptive - enables LLM thinking mode
    timezone: str = "UTC"  # IANA timezone, e.g. "Asia/Shanghai", "America/New_York"
    unified_session: bool = False  # Share one session across all channels (single-user multi-device)
    disabled_skills: list[str] = Field(default_factory=list)  # Skill names to exclude from loading (e.g. ["summarize", "skill-creator"])
    session_ttl_minutes: int = Field(
        default=0,
        ge=0,
        validation_alias=AliasChoices("idleCompactAfterMinutes", "sessionTtlMinutes"),
        serialization_alias="idleCompactAfterMinutes",
    )  # Auto-compact idle threshold in minutes (0 = disabled)
    max_messages: int = Field(
        default=120,
        ge=0,
    )  # Max messages to replay from session history (0 = use default 120, respects token budget)
    consolidation_ratio: float = Field(
        default=0.5,
        ge=0.1,
        le=0.95,
        validation_alias=AliasChoices("consolidationRatio"),
        serialization_alias="consolidationRatio",
    )  # Consolidation target ratio (0.5 = 50% of budget retained after compression)
    dream: DreamConfig = Field(default_factory=DreamConfig)


class AgentsConfig(Base):
    """Agent configuration."""

    defaults: AgentDefaults = Field(default_factory=AgentDefaults)


class ProviderConfig(Base):
    """LLM provider configuration."""

    api_key: str | None = None
    api_base: str | None = None
    extra_headers: dict[str, str] | None = None  # Custom headers (e.g. APP-Code for AiHubMix)
    extra_body: dict[str, Any] | None = None  # Extra fields merged into every request body


class BedrockProviderConfig(ProviderConfig):
    """AWS Bedrock Runtime provider configuration."""

    region: str | None = None  # AWS region, falls back to AWS_REGION/AWS_DEFAULT_REGION/profile
    profile: str | None = None  # Optional AWS shared config profile


class ProvidersConfig(Base):
    """Configuration for LLM providers."""

    custom: ProviderConfig = Field(default_factory=ProviderConfig)  # Any OpenAI-compatible endpoint
    azure_openai: ProviderConfig = Field(default_factory=ProviderConfig)  # Azure OpenAI (model = deployment name)
    bedrock: BedrockProviderConfig = Field(default_factory=BedrockProviderConfig)  # AWS Bedrock Converse
    anthropic: ProviderConfig = Field(default_factory=ProviderConfig)
    openai: ProviderConfig = Field(default_factory=ProviderConfig)
    openrouter: ProviderConfig = Field(default_factory=ProviderConfig)
    huggingface: ProviderConfig = Field(default_factory=ProviderConfig)
    deepseek: ProviderConfig = Field(default_factory=ProviderConfig)
    groq: ProviderConfig = Field(default_factory=ProviderConfig)
    zhipu: ProviderConfig = Field(default_factory=ProviderConfig)
    dashscope: ProviderConfig = Field(default_factory=ProviderConfig)
    vllm: ProviderConfig = Field(default_factory=ProviderConfig)
    ollama: ProviderConfig = Field(default_factory=ProviderConfig)  # Ollama local models
    lm_studio: ProviderConfig = Field(default_factory=ProviderConfig)  # LM Studio local models
    ovms: ProviderConfig = Field(default_factory=ProviderConfig)  # OpenVINO Model Server (OVMS)
    gemini: ProviderConfig = Field(default_factory=ProviderConfig)
    moonshot: ProviderConfig = Field(default_factory=ProviderConfig)
    minimax: ProviderConfig = Field(default_factory=ProviderConfig)
    minimax_anthropic: ProviderConfig = Field(default_factory=ProviderConfig)  # MiniMax Anthropic endpoint (thinking)
    mistral: ProviderConfig = Field(default_factory=ProviderConfig)
    stepfun: ProviderConfig = Field(default_factory=ProviderConfig)  # Step Fun (阶跃星辰)
    xiaomi_mimo: ProviderConfig = Field(default_factory=ProviderConfig)  # Xiaomi MIMO (小米)
    longcat: ProviderConfig = Field(default_factory=ProviderConfig)  # LongCat
    aihubmix: ProviderConfig = Field(default_factory=ProviderConfig)  # AiHubMix API gateway
    siliconflow: ProviderConfig = Field(default_factory=ProviderConfig)  # SiliconFlow (硅基流动)
    volcengine: ProviderConfig = Field(default_factory=ProviderConfig)  # VolcEngine (火山引擎)
    volcengine_coding_plan: ProviderConfig = Field(default_factory=ProviderConfig)  # VolcEngine Coding Plan
    byteplus: ProviderConfig = Field(default_factory=ProviderConfig)  # BytePlus (VolcEngine international)
    byteplus_coding_plan: ProviderConfig = Field(default_factory=ProviderConfig)  # BytePlus Coding Plan
    openai_codex: ProviderConfig = Field(default_factory=ProviderConfig, exclude=True)  # OpenAI Codex (OAuth)
    github_copilot: ProviderConfig = Field(default_factory=ProviderConfig, exclude=True)  # Github Copilot (OAuth)
    qianfan: ProviderConfig = Field(default_factory=ProviderConfig)  # Qianfan (百度千帆)


class HeartbeatConfig(Base):
    """Heartbeat service configuration."""

    enabled: bool = True
    interval_s: int = 30 * 60  # 30 minutes
    keep_recent_messages: int = 8


class ApiConfig(Base):
    """OpenAI-compatible API server configuration."""

    host: str = "127.0.0.1"  # Safer default: local-only bind.
    port: int = 8900
    timeout: float = 120.0  # Per-request timeout in seconds.
    api_key: str = Field(
        default="",
        validation_alias=AliasChoices("apiKey", "api_key"),
    )  # Optional Bearer key required for /v1/* routes when set.
    trust_proxy_auth: bool = Field(
        default=False,
        validation_alias=AliasChoices("trustProxyAuth", "trust_proxy_auth"),
    )  # Set only when a trusted reverse proxy performs API authentication.


class GatewayConfig(Base):
    """Gateway/server configuration."""

    host: str = "127.0.0.1"  # Safer default: local-only bind.
    port: int = 18790
    heartbeat: HeartbeatConfig = Field(default_factory=HeartbeatConfig)


def _default_campaign_status_paths() -> list[str]:
    return [
        "active_learning/status.json",
        "active_learning/status.md",
        "active_learning/status.txt",
        "campaign/status.json",
        "campaign/status.md",
        "campaign/status.txt",
    ]


class TuiConfig(Base):
    """Local TUI display configuration."""

    campaign_status_paths: list[str] = Field(default_factory=_default_campaign_status_paths)
    companion_stale_after_seconds: int = Field(
        default=3600,
        ge=0,
    )  # Mark Companion display documents stale after this age in seconds. 0 disables stale marking.
    keymap: dict[str, str | list[str]] = Field(
        default_factory=dict
    )  # Optional TUI key overrides by action, e.g. {"pager": "f7", "toolLog": ["f8"]}.


class CommandSurfaceConfig(Base):
    """Slash command visibility for one user-facing surface."""

    hide: list[str] = Field(default_factory=list)
    show: list[str] | None = None


class CommandsConfig(Base):
    """Slash command visibility policy."""

    gateway: CommandSurfaceConfig = Field(default_factory=CommandSurfaceConfig)
    tui: CommandSurfaceConfig = Field(default_factory=CommandSurfaceConfig)


class WebSearchConfig(Base):
    """Web search tool configuration."""

    provider: str = "duckduckgo"  # brave, tavily, duckduckgo, searxng, jina, kagi, olostep
    api_key: str = ""
    base_url: str = ""  # SearXNG base URL
    max_results: int = 5
    timeout: int = 30  # Wall-clock timeout (seconds) for search operations


class WebFetchConfig(Base):
    """Web fetch tool configuration."""

    use_jina_reader: bool = True


class WebToolsConfig(Base):
    """Web tools configuration."""

    enable: bool = True
    proxy: str | None = (
        None  # HTTP/SOCKS5 proxy URL, e.g. "http://127.0.0.1:7890" or "socks5://127.0.0.1:1080"
    )
    user_agent: str | None = None
    search: WebSearchConfig = Field(default_factory=WebSearchConfig)
    fetch: WebFetchConfig = Field(default_factory=WebFetchConfig)


class ExecToolConfig(Base):
    """Shell exec tool configuration."""

    enable: bool = True
    timeout: int = 60
    path_append: str = ""
    sandbox: str = ""  # sandbox backend: "" (none) or "bwrap"
    allowed_env_keys: list[str] = Field(default_factory=list)  # Env var names to pass through to subprocess (e.g. ["GOPATH", "JAVA_HOME"])
    allow_commands: list[str] = Field(default_factory=list)  # Exact shell commands that can run without approval.
    readonly_commands: list[str] = Field(default_factory=list)  # Command names that can run without approval when no shell mutation syntax is present.
    # Command names that default to background execution when no shell mutation syntax is present.
    background_commands: list[str] = Field(
        default_factory=lambda: ["cmatrix", "top", "htop", "btop", "watch"]
    )
    allow_patterns: list[str] = Field(default_factory=list)  # Legacy regex allowlist for hard command guards.
    require_allowlist: bool = False  # If true and approvals are off, block commands outside allow_commands/allow_patterns.
    approval_required: bool = True  # Require ApprovalManager approval before non-allowlisted command execution.

class MCPServerConfig(Base):
    """MCP server connection configuration (stdio or HTTP)."""

    type: Literal["stdio", "sse", "streamableHttp"] | None = None  # auto-detected if omitted
    command: str = ""  # Stdio: command to run (e.g. "npx")
    args: list[str] = Field(default_factory=list)  # Stdio: command arguments
    env: dict[str, str] = Field(default_factory=dict)  # Stdio: extra env vars
    url: str = ""  # HTTP/SSE: endpoint URL
    headers: dict[str, str] = Field(default_factory=dict)  # HTTP/SSE: custom headers
    tool_timeout: int = 120  # seconds before a tool call is cancelled
    enabled_tools: list[str] = Field(default_factory=lambda: ["*"])  # Only register these tools; accepts raw MCP names or wrapped mcp_<server>_<tool> names; ["*"] = all tools; [] = no tools

class MyToolConfig(Base):
    """Self-inspection tool configuration."""

    enable: bool = True  # register the `my` tool (agent runtime state inspection)
    allow_set: bool = False  # let `my` modify loop state (read-only if False)


class ToolsConfig(Base):
    """Tools configuration."""

    web: WebToolsConfig = Field(default_factory=WebToolsConfig)
    exec: ExecToolConfig = Field(default_factory=ExecToolConfig)
    my: MyToolConfig = Field(default_factory=MyToolConfig)
    restrict_to_workspace: bool = False  # restrict all tool access to workspace directory
    approval_required_for_tools: bool = False  # Require ApprovalManager for agent-side tool calls.
    approval_allowlist: list[str] = Field(default_factory=list)  # Exact tool names that can run without ApprovalManager.
    enabled_builtin_tools: list[str] | None = None  # Optional allowlist for built-in tool names.
    read_allowlist: list[str] = Field(default_factory=list)  # Optional extra read roots/files outside the workspace.
    write_allowlist: list[str] = Field(default_factory=list)  # Optional workspace-relative write roots/files.
    approval_gated_writes: bool = False  # Require ApprovalManager records for edits/overwrites.
    mcp_servers: dict[str, MCPServerConfig] = Field(default_factory=dict)
    ssrf_whitelist: list[str] = Field(default_factory=list)  # CIDR ranges to exempt from SSRF blocking (e.g. ["100.64.0.0/10"] for Tailscale)


def _api_bind_requires_auth(host: str) -> bool:
    normalized = (host or "").strip().lower()
    if not normalized:
        return False
    if normalized in {"localhost", "127.0.0.1", "::1"}:
        return False
    if normalized.startswith("127."):
        return False
    return True


def _telegram_enabled_without_allow_from(channels: ChannelsConfig) -> bool:
    telegram = getattr(channels, "telegram", None)
    if not isinstance(telegram, dict) or not telegram.get("enabled"):
        return False
    allow_from = telegram.get("allowFrom")
    if allow_from is None:
        allow_from = telegram.get("allow_from")
    return not bool(allow_from)


class Config(BaseSettings):
    """Root configuration for mlpcopilot."""

    runtime_profile: RuntimeProfile = MLPCOPILOT_PROFILE
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    tui: TuiConfig = Field(default_factory=TuiConfig)
    commands: CommandsConfig = Field(default_factory=CommandsConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)

    @model_validator(mode="after")
    def apply_profile_defaults(self) -> "Config":
        """Apply runtime-profile policy defaults after config parsing."""
        if self.runtime_profile == MLPCOPILOT_PROFILE:
            apply_runtime_profile_defaults(self)
            if _api_bind_requires_auth(self.api.host) and not (
                self.api.api_key or self.api.trust_proxy_auth
            ):
                raise ValueError(
                    "mlpcopilot public API bind requires api.apiKey or api.trustProxyAuth=true"
                )
            if _telegram_enabled_without_allow_from(self.channels):
                raise ValueError("mlpcopilot telegram requires channels.telegram.allowFrom")
            if not self.tools.restrict_to_workspace:
                raise ValueError("mlpcopilot requires tools.restrictToWorkspace=true")
            if not self.tools.approval_gated_writes:
                raise ValueError("mlpcopilot requires tools.approvalGatedWrites=true")
            if not self.tools.approval_required_for_tools:
                raise ValueError("mlpcopilot requires tools.approvalRequiredForTools=true")
            if self.tools.exec.enable:
                if not self.tools.exec.require_allowlist or not self.tools.exec.approval_required:
                    raise ValueError(
                        "mlpcopilot exec requires requireAllowlist=true and approvalRequired=true"
                    )
                enabled = self.tools.enabled_builtin_tools or []
                if "exec" not in enabled:
                    raise ValueError(
                        "mlpcopilot exec requires tools.enabledBuiltinTools to include 'exec'"
                    )
        return self

    @property
    def workspace_path(self) -> Path:
        """Get expanded workspace path."""
        return Path(self.agents.defaults.workspace).expanduser()

    def _match_provider(
        self, model: str | None = None
    ) -> tuple["ProviderConfig | None", str | None]:
        """Match provider config and its registry name. Returns (config, spec_name)."""
        from mlpcopilot.providers.registry import PROVIDERS, find_by_name

        forced = self.agents.defaults.provider
        if forced != "auto":
            spec = find_by_name(forced)
            if spec:
                p = getattr(self.providers, spec.name, None)
                return (p, spec.name) if p else (None, None)
            return None, None

        model_lower = (model or self.agents.defaults.model).lower()
        model_normalized = model_lower.replace("-", "_")
        model_prefix = model_lower.split("/", 1)[0] if "/" in model_lower else ""
        normalized_prefix = model_prefix.replace("-", "_")

        def _kw_matches(kw: str) -> bool:
            kw = kw.lower()
            return kw in model_lower or kw.replace("-", "_") in model_normalized

        # Explicit provider prefix wins — prevents `github-copilot/...codex` matching openai_codex.
        for spec in PROVIDERS:
            p = getattr(self.providers, spec.name, None)
            if p and model_prefix and normalized_prefix == spec.name:
                if spec.is_oauth or spec.is_local or spec.is_direct or p.api_key:
                    return p, spec.name

        # Match by keyword (order follows PROVIDERS registry)
        for spec in PROVIDERS:
            p = getattr(self.providers, spec.name, None)
            if p and any(_kw_matches(kw) for kw in spec.keywords):
                if spec.is_oauth or spec.is_local or spec.is_direct or p.api_key:
                    return p, spec.name

        # Fallback: configured local providers can route models without
        # provider-specific keywords (for example plain "llama3.2" on Ollama).
        # Prefer providers whose detect_by_base_keyword matches the configured api_base
        # (e.g. Ollama's "11434" in "http://localhost:11434") over plain registry order.
        local_fallback: tuple[ProviderConfig, str] | None = None
        for spec in PROVIDERS:
            if not spec.is_local:
                continue
            p = getattr(self.providers, spec.name, None)
            if not (p and p.api_base):
                continue
            if spec.detect_by_base_keyword and spec.detect_by_base_keyword in p.api_base:
                return p, spec.name
            if local_fallback is None:
                local_fallback = (p, spec.name)
        if local_fallback:
            return local_fallback

        # Fallback: gateways first, then others (follows registry order)
        # OAuth providers are NOT valid fallbacks — they require explicit model selection
        for spec in PROVIDERS:
            if spec.is_oauth:
                continue
            p = getattr(self.providers, spec.name, None)
            if p and p.api_key:
                return p, spec.name
        return None, None

    def get_provider(self, model: str | None = None) -> ProviderConfig | None:
        """Get matched provider config (api_key, api_base, extra_headers). Falls back to first available."""
        p, _ = self._match_provider(model)
        return p

    def get_provider_name(self, model: str | None = None) -> str | None:
        """Get the registry name of the matched provider (e.g. "deepseek", "openrouter")."""
        _, name = self._match_provider(model)
        return name

    def get_api_key(self, model: str | None = None) -> str | None:
        """Get API key for the given model. Falls back to first available key."""
        p = self.get_provider(model)
        return p.api_key if p else None

    def get_api_base(self, model: str | None = None) -> str | None:
        """Get API base URL for the given model, falling back to the provider default when present."""
        from mlpcopilot.providers.registry import find_by_name

        p, name = self._match_provider(model)
        if p and p.api_base:
            return p.api_base
        if name:
            spec = find_by_name(name)
            if spec and spec.default_api_base:
                return spec.default_api_base
        return None

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        env_prefix="MLPCOPILOT_",
        env_nested_delimiter="__",
    )
