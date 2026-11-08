"""Test harness that loads the APInex plugin against an offline ProviderProfile double."""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = REPO_ROOT / "apinex"
FIXTURE_PATH = Path(__file__).resolve().parent / "models_fixture.json"

CATALOG_FIXTURE = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
FIXTURE_MODEL_IDS = [entry["id"] for entry in CATALOG_FIXTURE["data"]]

ANTHROPIC_EXPECTED_MODELS = [
    "claude-fable-5.1",
    "claude-opus-5.5",
    "claude-sonnet-5.5",
    "free/claude-opus-4.6",
    "free/claude-sonnet-4.6",
]

OPENAI_EXPECTED_MODELS = [
    "deepseek-v4-flash",
    "deepseek-v4-pro",
    "deepseek-v4.1-flash",
    "free/deepseek-v4-flash-0731",
    "free/deepseek-v4-pro-0813",
    "free/deepseek-v4.1-flash",
    "free/gemini-3.1-pro",
    "free/gemini-3.8-flash",
    "free/glm-5.3",
    "free/glm-5.3-flash",
    "free/glm-5.3-flashx",
    "free/gpt-6-luna",
    "free/hy4",
    "free/kimi-k2.8",
    "free/kimi-k3",
    "free/mimo-v2.6-flash",
    "free/mimo-v2.6-pro",
    "free/minimax-m3",
    "free/minimax-m3.1-flash",
    "free/muse-spark-1.3",
    "free/qwen-3.8-max",
    "gemini-3.1-pro",
    "gemini-3.8-flash",
    "gemini-4-argon",
    "glm-5.3",
    "glm-5.3-flash",
    "gpt-6-astra",
    "gpt-6-luna",
    "gpt-6.1-sol",
    "gpt-6.1-terra",
    "grok-4.7",
    "hy4-preview",
    "kimi-k3.1-pro",
    "muse-spark-1.3",
]


@dataclass
class FakeProviderProfile:
    """Minimal stand-in for Hermes' ``providers.base.ProviderProfile``."""

    name: str
    api_mode: str = "chat_completions"
    aliases: tuple = ()
    display_name: str = ""
    description: str = ""
    signup_url: str = ""
    env_vars: tuple = ()
    base_url: str = ""
    models_url: str = ""
    auth_type: str = "api_key"
    supports_vision: bool = False
    fallback_models: tuple = ()
    hostname: str = ""
    default_headers: dict = field(default_factory=dict)
    default_aux_model: str = ""
    unsupported_response_formats: tuple = ()
    model_capabilities: dict = field(default_factory=dict)

    MOCK_UPSTREAM_IDS = None

    def fetch_models(self, *, api_key=None, base_url=None, timeout=8.0):
        self.recorded_fetches = getattr(self, "recorded_fetches", [])
        self.recorded_fetches.append(
            {"api_key": api_key, "base_url": base_url, "timeout": timeout}
        )
        upstream = FakeProviderProfile.MOCK_UPSTREAM_IDS
        return list(upstream) if upstream is not None else None


def import_apinex_plugin():
    """Import ``apinex/__init__.py`` with a fresh stub ``providers`` registry."""
    registered_profiles: list = []
    providers_mod = types.ModuleType("providers")
    providers_mod.register_provider = registered_profiles.append
    base_mod = types.ModuleType("providers.base")
    base_mod.ProviderProfile = FakeProviderProfile
    providers_mod.base = base_mod

    prior_modules = {k: sys.modules.get(k) for k in ("providers", "providers.base")}
    sys.modules["providers"] = providers_mod
    sys.modules["providers.base"] = base_mod
    try:
        spec = importlib.util.spec_from_file_location(
            "apinex_plugin_test_target",
            PACKAGE_DIR / "__init__.py",
            submodule_search_locations=[str(PACKAGE_DIR)],
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        for mod_name, original in prior_modules.items():
            if original is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = original
    return module, registered_profiles
