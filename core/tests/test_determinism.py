"""Tests for the determinism rule: non-determinism belongs to the Transformer alone."""

import pytest
from aura_core import (
    check_determinism,
    is_exempt,
    is_python_source,
    is_transformer_path,
)
from aura_core.determinism import ENTROPY_PATTERNS, LLM_PATTERNS

EXEMPT = (
    "core/scripts",
    "core/tests",
    "core/src/aura_hive/config",
    "core/src/aura_hive/hive/cortex.py",
)


class TestPathClassification:
    @pytest.mark.parametrize(
        "path",
        [
            "core/src/aura_hive/hive/transformer/__init__.py",
            "core/src/aura_hive/hive/transformer/llm/client.py",
            "agents/bee-keeper/src/aura_keeper/hive/transformer/signatures.py",
            "agents/bee-evolver/src/hive/transformer.py",
        ],
    )
    def test_transformer_paths_recognised(self, path: str) -> None:
        assert is_transformer_path(path)

    @pytest.mark.parametrize(
        "path",
        [
            "core/src/aura_hive/hive/membrane/main.py",
            "core/src/aura_hive/hive/aggregator/main.py",
            "core/src/aura_hive/hive/transformers_helper.py",
            "core/src/aura_hive/hive/connector/main.py",
        ],
    )
    def test_non_transformer_paths_rejected(self, path: str) -> None:
        assert not is_transformer_path(path)

    def test_exempt_prefixes_cover_subpaths(self) -> None:
        assert is_exempt("core/scripts/training/train_dspy.py", EXEMPT)
        assert not is_exempt("core/src/aura_hive/hive/membrane/main.py", EXEMPT)

    def test_windows_separators_normalised(self) -> None:
        assert is_transformer_path("core\\src\\aura_hive\\hive\\transformer\\main.py")


class TestViolations:
    @pytest.mark.parametrize(
        "line",
        [
            "response = await litellm.acompletion(model=m, messages=msgs)",
            "import dspy",
            "from openai import AsyncOpenAI",
            "client = mistralai.Mistral(api_key=key)",
            "resp = client.chat.completions.create(model=m)",
        ],
    )
    def test_model_calls_flagged_outside_transformer(self, line: str) -> None:
        heresy = check_determinism(
            "core/src/aura_hive/hive/membrane/main.py", line, EXEMPT
        )
        assert heresy is not None
        assert "Determinism Heresy" in heresy
        assert "membrane" in heresy

    @pytest.mark.parametrize(
        "line",
        [
            "noise = np.random.normal(0, 0.01, (7, 7))",
            "pick = random.choice(candidates)",
            "random.shuffle(offers)",
            "jitter = random.uniform(0.0, 0.5)",
        ],
    )
    def test_statistical_randomness_flagged(self, line: str) -> None:
        heresy = check_determinism(
            "core/src/aura_hive/hive/generator/main.py", line, EXEMPT
        )
        assert heresy is not None
        assert "cannot carry a guarantee" in heresy

    def test_the_coherence_engine_line_is_caught(self) -> None:
        """The line that motivated this rule, verbatim from coherence/engine.py."""
        line = (
            "noise = np.random.normal(0, 0.01, (7, 7)) "
            "+ 1j * np.random.normal(0, 0.01, (7, 7))"
        )
        assert check_determinism(
            "core/src/aura_hive/hive/proteins/coherence/engine.py", line, EXEMPT
        )


class TestPermitted:
    @pytest.mark.parametrize(
        "line",
        [
            "response = await litellm.acompletion(model=m, messages=msgs)",
            "import dspy",
            "seed = random.randint(0, 100)",
        ],
    )
    def test_anything_goes_inside_a_transformer(self, line: str) -> None:
        assert (
            check_determinism(
                "core/src/aura_hive/hive/transformer/main.py", line, EXEMPT
            )
            is None
        )

    @pytest.mark.parametrize(
        "line",
        [
            "event_id=str(uuid.uuid4()),",
            "timestamp=datetime.now(UTC),",
            "elapsed = time.time() - started",
            "nonce = secrets.token_bytes(32)",
            "signing_key = SigningKey.generate()",
        ],
    )
    def test_identity_time_and_crypto_entropy_are_load_bearing(self, line: str) -> None:
        """Pollen needs an id and a timestamp; Ed25519 needs real randomness."""
        assert (
            check_determinism("core/src/aura_hive/hive/generator/main.py", line, EXEMPT)
            is None
        )

    @pytest.mark.parametrize(
        "line",
        [
            "# we deliberately avoid litellm here",
            '"""Uses dspy under the hood."""',
            "",
            "   ",
        ],
    )
    def test_comments_and_blanks_ignored(self, line: str) -> None:
        assert (
            check_determinism("core/src/aura_hive/hive/membrane/main.py", line, EXEMPT)
            is None
        )

    def test_exempt_paths_allow_model_calls(self) -> None:
        assert check_determinism("core/scripts/seed.py", "import dspy", EXEMPT) is None
        assert (
            check_determinism(
                "core/src/aura_hive/hive/cortex.py", "import dspy", EXEMPT
            )
            is None
        )

    @pytest.mark.parametrize(
        "line",
        [
            "self.random_seed_config = settings.seed",
            "randomise_order = False",
            "transformer_client = registry.get('transformer')",
        ],
    )
    def test_no_false_positives_on_similar_identifiers(self, line: str) -> None:
        assert (
            check_determinism("core/src/aura_hive/hive/membrane/main.py", line, EXEMPT)
            is None
        )


class TestFileTypeFilter:
    @pytest.mark.parametrize(
        "path",
        [
            "uv.lock",
            "pyproject.toml",
            ".github/workflows/bee-evolver.yaml",
            "tools/evolver_colab.ipynb",
            "docs/DEPENDENCY_HEALTH_REPORT.md",
            "agents/bee-evolver/prompts/bee_evolver.md",
        ],
    )
    def test_non_python_files_ignored(self, path: str) -> None:
        """A lockfile naming litellm is not a call site."""
        assert not is_python_source(path)
        assert check_determinism(path, '{ name = "litellm" },', EXEMPT) is None

    @pytest.mark.parametrize(
        "path",
        ["tools/test_discovery.py", "core/tests/test_x.py", "tests/test_y.py"],
    )
    def test_test_modules_may_mock_models(self, path: str) -> None:
        assert not is_python_source(path)
        assert check_determinism(path, '@patch("dspy.configure")', EXEMPT) is None

    @pytest.mark.parametrize(
        "line",
        [
            "A lockfile, a pyproject or a workflow yaml may name `litellm` without ever",
            "names `litellm` inside a docstring reads as prose, including the prose above.",
            "invoking it, and test modules legitimately patch and mock model clients.",
            "Reasoning belongs to T alone; call it through the skill registry, or",
            "# openai is deliberately not used here",
        ],
    )
    def test_prose_naming_a_library_is_not_a_call_site(self, line: str) -> None:
        """The rule must not trip over its own documentation."""
        assert (
            check_determinism("core/src/aura_hive/hive/membrane/main.py", line, EXEMPT)
            is None
        )

    def test_ordinary_source_still_checked(self) -> None:
        assert is_python_source("core/src/aura_hive/hive/membrane/main.py")


def test_patterns_are_compiled_and_non_empty() -> None:
    assert LLM_PATTERNS and ENTROPY_PATTERNS
    assert all(hasattr(p, "search") for p in LLM_PATTERNS + ENTROPY_PATTERNS)
