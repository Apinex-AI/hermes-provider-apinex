"""APInex gateway provider profiles for Hermes Agent.

Registers two Hermes model providers backed by a single ``APINEX_API_KEY``:

- ``apinex``: routes Claude models (``claude-*`` and ``free/claude-*``) over
  APInex's native Anthropic Messages endpoint (``https://api.apinex.bond/v1/messages``),
  preserving Hermes' native Anthropic prompt-cache breakpoints and extended thinking.
- ``apinex-openai``: routes GPT-6.1, Gemini 4 Argon, DeepSeek V4.1, GLM 5.3,
  Qwen 3.8, Kimi K3.1, Grok 4.7 and 17 Free-tier chat models over APInex's
  OpenAI-compatible Chat Completions endpoint (``https://api.apinex.bond/v1``).

This module performs no network I/O of its own, reads no local files or
environment variables directly, adds no custom HTTP headers, and starts no
background threads or child processes. Model discovery delegates to Hermes'
built-in ``ProviderProfile.fetch_models()`` against ``https://api.apinex.bond/v1/models``.
"""

from __future__ import annotations

from urllib.parse import urlparse

from providers import register_provider
from providers.base import ProviderProfile

__version__ = "0.1.0"

ANTHROPIC_PROVIDER_NAME = "apinex"
OPENAI_PROVIDER_NAME = "apinex-openai"
APINEX_KEY_ENV = "APINEX_API_KEY"

GATEWAY_API_HOST = "api.apinex.bond"
ANTHROPIC_GATEWAY_URL = "https://api.apinex.bond"
OPENAI_GATEWAY_URL = "https://api.apinex.bond/v1"
GATEWAY_MODELS_ENDPOINT = "https://api.apinex.bond/v1/models"
APINEX_REGISTER_URL = "https://apinex.bond/register?utm_source=hermes&utm_medium=plugin"

ANTHROPIC_ID_PREFIXES = ("claude-", "free/claude-")
MEDIA_MODEL_TOKENS = (
    "image",
    "banana",
    "seedance",
    "video",
    "embed",
    "whisper",
    "tts",
    "stt",
)
# Catalog entries on https://apinex.bond/api/public/models with supportsTools=False.
NON_TOOL_MODELS = frozenset({"drex-v2.0", "jev-1.13", "free/jev-1.13"})


def build_capability_spec(context_tokens: int, vision_enabled: bool, family_tag: str) -> dict:
    """Construct a Hermes model_capabilities entry."""
    return {
        "supports_tools": True,
        "supports_reasoning": True,
        "supports_vision": vision_enabled,
        "context_window": context_tokens,
        "model_family": family_tag,
    }


# Per-model metadata verified against https://apinex.bond/api/public/models.
ANTHROPIC_CAPABILITY_MATRIX = {
    model_id: build_capability_spec(1_000_000, True, "claude")
    for model_id in (
        "claude-fable-5.1",
        "claude-opus-5.5",
        "claude-sonnet-5.5",
        "free/claude-opus-4.6",
        "free/claude-sonnet-4.6",
    )
}

OPENAI_CAPABILITY_MATRIX = {
    **{
        model_id: build_capability_spec(1_000_000, True, "gpt")
        for model_id in (
            "gpt-6.1-sol",
            "gpt-6.1-terra",
            "gpt-6-astra",
            "gpt-6-luna",
            "free/gpt-6-luna",
        )
    },
    **{
        model_id: build_capability_spec(1_000_000, True, "gemini")
        for model_id in (
            "gemini-4-argon",
            "gemini-3.8-flash",
            "gemini-3.1-pro",
            "free/gemini-3.8-flash",
            "free/gemini-3.1-pro",
        )
    },
    "deepseek-v4.1-flash": build_capability_spec(1_000_000, True, "deepseek"),
    "free/deepseek-v4.1-flash": build_capability_spec(1_000_000, True, "deepseek"),
    "deepseek-v4-flash": build_capability_spec(1_000_000, False, "deepseek"),
    "deepseek-v4-pro": build_capability_spec(1_000_000, False, "deepseek"),
    "free/deepseek-v4-flash-0731": build_capability_spec(1_000_000, False, "deepseek"),
    "free/deepseek-v4-pro-0813": build_capability_spec(1_000_000, False, "deepseek"),
    "glm-5.3-flash": build_capability_spec(1_000_000, True, "glm"),
    "free/glm-5.3-flash": build_capability_spec(1_000_000, True, "glm"),
    "free/glm-5.3-flashx": build_capability_spec(1_000_000, True, "glm"),
    "glm-5.3": build_capability_spec(1_000_000, False, "glm"),
    "free/glm-5.3": build_capability_spec(1_000_000, False, "glm"),
    "free/qwen-3.8-max": build_capability_spec(1_000_000, True, "qwen"),
    "kimi-k3.1-pro": build_capability_spec(1_000_000, True, "kimi"),
    "free/kimi-k3": build_capability_spec(1_000_000, True, "kimi"),
    "free/kimi-k2.8": build_capability_spec(1_000_000, True, "kimi"),
    "grok-4.7": build_capability_spec(500_000, True, "grok"),
    "free/minimax-m3": build_capability_spec(1_000_000, True, "minimax"),
    "free/minimax-m3.1-flash": build_capability_spec(1_000_000, True, "minimax"),
    "free/mimo-v2.6-flash": build_capability_spec(1_000_000, True, "mimo"),
    "free/mimo-v2.6-pro": build_capability_spec(1_000_000, True, "mimo"),
    "muse-spark-1.3": build_capability_spec(1_000_000, True, "muse"),
    "free/muse-spark-1.3": build_capability_spec(1_000_000, True, "muse"),
    "hy4-preview": build_capability_spec(1_000_000, True, "hunyuan"),
    "free/hy4": build_capability_spec(1_000_000, True, "hunyuan"),
}


def is_anthropic_model(model_id: str) -> bool:
    """Return True when the model ID belongs to the Claude family on APInex."""
    return model_id.lower().startswith(ANTHROPIC_ID_PREFIXES)


def is_agentic_chat_model(candidate: object, *, anthropic_wire: bool) -> bool:
    """Check whether a raw model ID belongs in the requested provider's picker."""
    if not isinstance(candidate, str) or not candidate or any(ch.isspace() for ch in candidate):
        return False
    normalized = candidate.lower()
    if normalized in NON_TOOL_MODELS:
        return False
    if any(token in normalized for token in MEDIA_MODEL_TOKENS):
        return False
    return is_anthropic_model(normalized) == anthropic_wire


def filter_gateway_models(raw_ids: list, *, anthropic_wire: bool) -> list[str]:
    """Deduplicate and sort tool-capable model IDs for one wire protocol."""
    matched = {
        item
        for item in raw_ids
        if is_agentic_chat_model(item, anthropic_wire=anthropic_wire)
    }
    return sorted(matched, key=str.lower)


class ApinexGatewayProfile(ProviderProfile):
    """ProviderProfile that partitions APInex's /v1/models list by wire protocol."""

    def fetch_models(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 8.0,
    ) -> list[str] | None:
        """Fetch models via Hermes' standard /v1/models call and filter by protocol.

        When the caller overrides ``base_url`` to a third-party host or local proxy,
        the upstream list is returned untouched. Returning ``None`` on empty or
        failed responses instructs Hermes to display ``fallback_models``.
        """
        discovered = super().fetch_models(api_key=api_key, base_url=base_url, timeout=timeout)
        override_url = (base_url or "").strip()
        if override_url and (urlparse(override_url).hostname or "").lower() != GATEWAY_API_HOST:
            return discovered
        if not discovered:
            return None
        use_anthropic = self.api_mode == "anthropic_messages"
        filtered = filter_gateway_models(discovered, anthropic_wire=use_anthropic)
        return filtered or None


apinex_anthropic_profile = ApinexGatewayProfile(
    name=ANTHROPIC_PROVIDER_NAME,
    display_name="APInex",
    description="APInex Claude models (native Anthropic Messages API)",
    signup_url=APINEX_REGISTER_URL,
    env_vars=(APINEX_KEY_ENV,),
    base_url=ANTHROPIC_GATEWAY_URL,
    models_url=GATEWAY_MODELS_ENDPOINT,
    auth_type="api_key",
    api_mode="anthropic_messages",
    default_aux_model="free/claude-sonnet-4.6",
    fallback_models=(
        "claude-sonnet-5.5",
        "claude-opus-5.5",
        "claude-fable-5.1",
        "free/claude-sonnet-4.6",
        "free/claude-opus-4.6",
    ),
    model_capabilities=dict(ANTHROPIC_CAPABILITY_MATRIX),
)

apinex_openai_profile = ApinexGatewayProfile(
    name=OPENAI_PROVIDER_NAME,
    display_name="APInex (OpenAI-compatible)",
    description="APInex GPT, Gemini, DeepSeek, GLM, Qwen, Kimi, Grok and Free-tier models (OpenAI-compatible)",
    signup_url=APINEX_REGISTER_URL,
    env_vars=(APINEX_KEY_ENV,),
    base_url=OPENAI_GATEWAY_URL,
    auth_type="api_key",
    api_mode="chat_completions",
    default_aux_model="free/deepseek-v4.1-flash",
    unsupported_response_formats=("json_schema",),
    fallback_models=(
        "free/deepseek-v4.1-flash",
        "free/glm-5.3-flash",
        "free/qwen-3.8-max",
        "free/gemini-3.8-flash",
        "free/gpt-6-luna",
        "gpt-6.1-sol",
        "gpt-6.1-terra",
        "gemini-4-argon",
        "deepseek-v4.1-flash",
        "glm-5.3-flash",
        "kimi-k3.1-pro",
        "grok-4.7",
    ),
    model_capabilities=dict(OPENAI_CAPABILITY_MATRIX),
)

register_provider(apinex_anthropic_profile)
register_provider(apinex_openai_profile)
