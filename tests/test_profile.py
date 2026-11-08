"""Unit tests for the APInex Hermes model-provider profiles."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import (  # noqa: E402
    ANTHROPIC_EXPECTED_MODELS,
    FIXTURE_MODEL_IDS,
    OPENAI_EXPECTED_MODELS,
    FakeProviderProfile,
    import_apinex_plugin,
)

DUMMY_KEY = "sk-apx-unit-test-placeholder"


class ApinexProfileConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.module, self.profiles = import_apinex_plugin()
        by_id = {p.name: p for p in self.profiles}
        self.claude_profile = by_id["apinex"]
        self.openai_profile = by_id["apinex-openai"]

    def test_registers_dual_gateway_profiles(self):
        self.assertEqual([p.name for p in self.profiles], ["apinex", "apinex-openai"])
        for profile in self.profiles:
            self.assertEqual(type(profile).__name__, "ApinexGatewayProfile")

    def test_anthropic_wire_configuration(self):
        self.assertEqual(self.claude_profile.api_mode, "anthropic_messages")
        self.assertEqual(self.claude_profile.base_url, "https://api.apinex.bond")
        self.assertEqual(self.claude_profile.models_url, "https://api.apinex.bond/v1/models")

    def test_openai_wire_configuration(self):
        self.assertEqual(self.openai_profile.api_mode, "chat_completions")
        self.assertEqual(self.openai_profile.base_url, "https://api.apinex.bond/v1")
        self.assertEqual(self.openai_profile.models_url, "")

    def test_auxiliary_models_use_zero_cost_routes(self):
        self.assertEqual(self.claude_profile.default_aux_model, "free/claude-sonnet-4.6")
        self.assertEqual(self.openai_profile.default_aux_model, "free/deepseek-v4.1-flash")
        self.assertEqual(self.openai_profile.unsupported_response_formats, ("json_schema",))
        self.assertEqual(self.claude_profile.unsupported_response_formats, ())

    def test_shared_credential_environment_variable(self):
        for profile in self.profiles:
            self.assertEqual(profile.env_vars, ("APINEX_API_KEY",))
            self.assertEqual(profile.auth_type, "api_key")

    def test_zero_custom_headers_and_per_model_vision(self):
        for profile in self.profiles:
            self.assertEqual(profile.default_headers, {})
            self.assertFalse(profile.supports_vision)

    def test_signup_url_contains_hermes_utm(self):
        for profile in self.profiles:
            parsed = urlparse(profile.signup_url)
            self.assertEqual((parsed.scheme, parsed.netloc, parsed.path), ("https", "apinex.bond", "/register"))
            self.assertEqual(parse_qs(parsed.query), {"utm_source": ["hermes"], "utm_medium": ["plugin"]})

    def test_fallback_lists_match_capability_matrices(self):
        for profile, expected in (
            (self.claude_profile, ANTHROPIC_EXPECTED_MODELS),
            (self.openai_profile, OPENAI_EXPECTED_MODELS),
        ):
            fallbacks = list(profile.fallback_models)
            self.assertTrue(fallbacks)
            self.assertEqual(len(fallbacks), len(set(fallbacks)))
            for model_id in [*fallbacks, profile.default_aux_model]:
                self.assertIn(model_id, expected)

    def test_capability_matrix_integrity(self):
        valid_keys = {
            "supports_tools",
            "supports_reasoning",
            "supports_vision",
            "context_window",
            "model_family",
        }
        for profile, expected in (
            (self.claude_profile, ANTHROPIC_EXPECTED_MODELS),
            (self.openai_profile, OPENAI_EXPECTED_MODELS),
        ):
            self.assertEqual(set(profile.model_capabilities), set(expected))
            for model_id, spec in profile.model_capabilities.items():
                self.assertEqual(set(spec), valid_keys, model_id)
                self.assertIsInstance(spec["context_window"], int)
                self.assertGreaterEqual(spec["context_window"], 500_000, model_id)
                self.assertTrue(spec["supports_tools"], model_id)
                self.assertTrue(spec["supports_reasoning"], model_id)
                self.assertIsInstance(spec["supports_vision"], bool)

    def test_specific_model_context_and_vision_flags(self):
        merged = {**self.claude_profile.model_capabilities, **self.openai_profile.model_capabilities}
        self.assertEqual(merged["claude-sonnet-5.5"]["context_window"], 1_000_000)
        self.assertEqual(merged["grok-4.7"]["context_window"], 500_000)
        self.assertEqual(merged["gemini-4-argon"]["context_window"], 1_000_000)
        self.assertFalse(merged["deepseek-v4-pro"]["supports_vision"])
        self.assertTrue(merged["deepseek-v4.1-flash"]["supports_vision"])


class ApinexCatalogFilteringTests(unittest.TestCase):
    def setUp(self):
        self.module, _ = import_apinex_plugin()

    def test_partitions_live_catalog_into_anthropic_and_openai_lists(self):
        self.assertEqual(
            self.module.filter_gateway_models(FIXTURE_MODEL_IDS, anthropic_wire=True),
            ANTHROPIC_EXPECTED_MODELS,
        )
        self.assertEqual(
            self.module.filter_gateway_models(FIXTURE_MODEL_IDS, anthropic_wire=False),
            OPENAI_EXPECTED_MODELS,
        )

    def test_only_non_tool_models_are_omitted_from_catalog(self):
        kept = set(ANTHROPIC_EXPECTED_MODELS) | set(OPENAI_EXPECTED_MODELS)
        omitted = sorted(set(FIXTURE_MODEL_IDS) - kept)
        self.assertEqual(omitted, ["drex-v2.0", "free/jev-1.13", "jev-1.13"])

    def test_rejects_non_tool_and_media_endpoints(self):
        check = self.module.is_agentic_chat_model
        for bad in (
            "drex-v2.0",
            "jev-1.13",
            "free/jev-1.13",
            "flux-image-pro",
            "seedance-video-v1",
            "text-embedding-3-small",
            "whisper-v3",
            "invalid model id",
            "",
            None,
            123,
        ):
            self.assertFalse(check(bad, anthropic_wire=False), f"should reject {bad!r}")
            self.assertFalse(check(bad, anthropic_wire=True), f"should reject {bad!r}")

    def test_wire_protocol_separation(self):
        check = self.module.is_agentic_chat_model
        self.assertTrue(check("claude-sonnet-5.5", anthropic_wire=True))
        self.assertTrue(check("free/claude-sonnet-4.6", anthropic_wire=True))
        self.assertFalse(check("claude-sonnet-5.5", anthropic_wire=False))
        self.assertTrue(check("gpt-6.1-sol", anthropic_wire=False))
        self.assertFalse(check("gpt-6.1-sol", anthropic_wire=True))


class ApinexFetchModelsDelegationTests(unittest.TestCase):
    def setUp(self):
        _, profiles = import_apinex_plugin()
        by_id = {p.name: p for p in profiles}
        self.claude_profile = by_id["apinex"]
        self.openai_profile = by_id["apinex-openai"]
        FakeProviderProfile.MOCK_UPSTREAM_IDS = list(FIXTURE_MODEL_IDS)

    def tearDown(self):
        FakeProviderProfile.MOCK_UPSTREAM_IDS = None

    def test_delegates_to_super_and_splits_by_protocol(self):
        self.assertEqual(
            self.claude_profile.fetch_models(api_key=DUMMY_KEY, base_url="https://api.apinex.bond"),
            ANTHROPIC_EXPECTED_MODELS,
        )
        self.assertEqual(
            self.openai_profile.fetch_models(api_key=DUMMY_KEY, base_url="https://api.apinex.bond/v1"),
            OPENAI_EXPECTED_MODELS,
        )
        self.assertEqual(
            self.claude_profile.recorded_fetches,
            [{"api_key": DUMMY_KEY, "base_url": "https://api.apinex.bond", "timeout": 8.0}],
        )

    def test_returns_none_when_upstream_list_is_empty(self):
        for empty_value in (None, []):
            FakeProviderProfile.MOCK_UPSTREAM_IDS = empty_value
            self.assertIsNone(self.claude_profile.fetch_models(api_key=DUMMY_KEY))
            self.assertIsNone(self.openai_profile.fetch_models(api_key=DUMMY_KEY))

    def test_preserves_unfiltered_models_for_custom_proxy_host(self):
        FakeProviderProfile.MOCK_UPSTREAM_IDS = ["custom-proxy-model", "drex-v2.0"]
        out = self.openai_profile.fetch_models(
            api_key=DUMMY_KEY,
            base_url="https://my-gateway.internal.example/v1",
        )
        self.assertEqual(out, ["custom-proxy-model", "drex-v2.0"])


if __name__ == "__main__":
    unittest.main()
