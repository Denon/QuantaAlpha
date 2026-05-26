"""Regression tests for external factor usage in the mining prompt chain."""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_planning_module():
    """Load planning.py with lightweight stubs for optional project deps."""
    logger_module = types.ModuleType("quantaalpha.log")
    logger_module.logger = types.SimpleNamespace(warning=lambda *args, **kwargs: None)

    llm_package = types.ModuleType("quantaalpha.llm")
    llm_package.__path__ = []

    llm_client_module = types.ModuleType("quantaalpha.llm.client")

    class FailingAPIBackend:
        def build_messages_and_create_chat_completion(self, *args, **kwargs):
            raise AssertionError("single-direction planning should not call the LLM")

    llm_client_module.APIBackend = FailingAPIBackend

    old_modules = {
        name: sys.modules.get(name)
        for name in ("quantaalpha.log", "quantaalpha.llm", "quantaalpha.llm.client")
    }
    sys.modules["quantaalpha.log"] = logger_module
    sys.modules["quantaalpha.llm"] = llm_package
    sys.modules["quantaalpha.llm.client"] = llm_client_module

    spec = importlib.util.spec_from_file_location(
        "planning_under_test",
        PROJECT_ROOT / "quantaalpha" / "pipeline" / "planning.py",
    )
    module = importlib.util.module_from_spec(spec)
    try:
        assert spec.loader is not None
        spec.loader.exec_module(module)
    finally:
        for name, old_module in old_modules.items():
            if old_module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old_module
    return module


class TestExternalFactorMiningPrompts(unittest.TestCase):
    def test_single_planning_direction_preserves_user_direction_without_llm(self):
        planning = _load_planning_module()

        direction = "size and beta Factors Mining"
        result = planning.generate_parallel_directions(
            initial_direction=direction,
            n=1,
            prompt_file=PROJECT_ROOT / "missing-planning-prompts.yaml",
            use_llm=True,
            allow_fallback=True,
        )

        self.assertEqual(result, [direction])

    def test_size_beta_prompt_requires_existing_variables_not_proxies(self):
        prompt_text = (
            PROJECT_ROOT
            / "quantaalpha"
            / "factors"
            / "prompts"
            / "prompts.yaml"
        ).read_text(encoding="utf-8")

        self.assertIn("existing `$size` and `$beta`", prompt_text)
        self.assertIn("must include `$size` and/or `$beta` directly", prompt_text)
        self.assertIn("do not substitute proxies", prompt_text)


if __name__ == "__main__":
    unittest.main()
