"""Packaging, manifest, documentation and AST security-surface tests."""

from __future__ import annotations

import ast
import re
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import PACKAGE_DIR, REPO_ROOT, import_apinex_plugin  # noqa: E402

PYTHON_FILES = sorted(PACKAGE_DIR.glob("*.py"))
EXPECTED_UTM = {"utm_source": ["hermes"], "utm_medium": ["plugin"]}
VALID_APINEX_PATHS = {
    "/",
    "/ru",
    "/zh",
    "/register",
    "/pricing",
    "/models",
    "/cli",
    "/resell",
    "/developers",
    "/privacy",
    "/terms",
    "/integrations/hermes",
    "/ru/integrations/hermes",
    "/zh/integrations/hermes",
}


def parse_plugin_yaml() -> dict:
    """Parse scalar fields and requires_env names from plugin.yaml using stdlib only."""
    parsed: dict = {}
    raw = (PACKAGE_DIR / "plugin.yaml").read_text(encoding="utf-8")
    for line in raw.splitlines():
        if line and not line[0].isspace() and ":" in line:
            key, _, val = line.partition(":")
            parsed[key.strip()] = val.strip().strip('"')
    parsed["requires_env"] = re.findall(r"^\s+- name: (\S+)$", raw, re.MULTILINE)
    return parsed


def collect_imported_modules(py_file: Path) -> set[str]:
    modules: set[str] = set()
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            modules.add(node.module or "")
    return modules


def load_pyproject_toml() -> dict:
    raw = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    if tomllib is not None:
        return tomllib.loads(raw)
    ver_match = re.search(r'^version\s*=\s*"([^"]+)"', raw, re.MULTILINE)
    return {"project": {"version": ver_match.group(1) if ver_match else "", "dependencies": []}}


class ApinexManifestAndPackagingTests(unittest.TestCase):
    def test_plugin_manifest_contract(self):
        manifest = parse_plugin_yaml()
        module, _ = import_apinex_plugin()
        self.assertEqual(manifest["name"], "apinex")
        self.assertEqual(manifest["kind"], "model-provider")
        self.assertEqual(manifest["requires_env"], [module.APINEX_KEY_ENV])
        self.assertEqual(manifest["requires_hermes"], ">=0.21.5")

    def test_version_synchronized_across_files(self):
        module, _ = import_apinex_plugin()
        pyproject = load_pyproject_toml()
        self.assertEqual(parse_plugin_yaml()["version"], module.__version__)
        self.assertEqual(pyproject["project"]["version"], module.__version__)
        self.assertIn(
            f"### {module.__version__}",
            (REPO_ROOT / "README.md").read_text(encoding="utf-8"),
        )

    def test_zero_external_python_dependencies(self):
        pyproject = load_pyproject_toml()
        self.assertEqual(pyproject["project"]["dependencies"], [])
        self.assertFalse((PACKAGE_DIR / "pyproject.toml").exists())
        self.assertNotIn("python_dependencies", parse_plugin_yaml())


class ApinexDocumentationTests(unittest.TestCase):
    def test_subdir_readme_is_identical_to_root_readme(self):
        self.assertEqual(
            (PACKAGE_DIR / "README.md").read_bytes(),
            (REPO_ROOT / "README.md").read_bytes(),
        )

    def test_markdown_links_use_https(self):
        readme_text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)]+)\)", readme_text):
            self.assertTrue(target.startswith("https://"), target)

    def test_apinex_web_links_include_utm_parameters(self):
        module, _ = import_apinex_plugin()
        documents = {
            "README.md": (REPO_ROOT / "README.md").read_text(encoding="utf-8"),
            "after-install.md": (PACKAGE_DIR / "after-install.md").read_text(encoding="utf-8"),
            "plugin.yaml": (PACKAGE_DIR / "plugin.yaml").read_text(encoding="utf-8"),
            "signup_url": module.APINEX_REGISTER_URL,
        }
        verified_count = 0
        for label, content in documents.items():
            for match in re.findall(r"https://apinex\.bond[^\s)\"'`>]*", content):
                parsed = urlparse(match)
                if parsed.path.startswith("/.well-known/skills") or parsed.path == "":
                    continue
                self.assertIn(parsed.path, VALID_APINEX_PATHS, f"{label}: {match}")
                self.assertEqual(parse_qs(parsed.query), EXPECTED_UTM, f"{label}: {match}")
                verified_count += 1
        self.assertGreaterEqual(verified_count, 8)

    def test_readme_contains_required_disclosures_and_multilingual_blocks(self):
        readme_text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        for expected_phrase in (
            "APINEX_API_KEY",
            "https://api.apinex.bond/v1/messages",
            "https://api.apinex.bond/v1/chat/completions",
            "GET https://api.apinex.bond/v1/models",
            "makes no network requests of its own",
            "No extra headers",
            "No analytics, telemetry",
            "never reads, writes, logs, caches or stores",
            "https://apinex.bond/privacy",
            "По-русски.",
            "简体中文。",
        ):
            self.assertIn(expected_phrase, readme_text)


class ApinexAstSecuritySurfaceTests(unittest.TestCase):
    def test_single_module_layout(self):
        self.assertEqual([p.name for p in PYTHON_FILES], ["__init__.py"])

    def test_imports_restricted_to_stdlib_urlparse_and_hermes_providers(self):
        allowed_imports = {"__future__", "urllib.parse", "providers", "providers.base"}
        for py_file in PYTHON_FILES:
            self.assertLessEqual(collect_imported_modules(py_file), allowed_imports, py_file.name)

    def test_ast_contains_no_network_io_subprocess_or_file_access(self):
        disallowed_calls = {
            "open",
            "exec",
            "eval",
            "compile",
            "__import__",
            "system",
            "popen",
            "getenv",
            "Popen",
            "run",
            "Thread",
            "setattr",
            "delattr",
            "urlopen",
            "Request",
            "get_secret",
        }
        for py_file in PYTHON_FILES:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    fn = node.func
                    call_name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", "")
                    self.assertNotIn(call_name, disallowed_calls, f"{py_file.name}:{node.lineno}")
                if isinstance(node, ast.Attribute):
                    self.assertNotEqual(node.attr, "environ", f"{py_file.name}:{node.lineno}")


if __name__ == "__main__":
    unittest.main()
