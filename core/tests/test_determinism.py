"""Tests for the determinism rule: non-determinism belongs to the Transformer alone."""

import pytest
from aura_core import (
    check_determinism,
    is_exempt,
    is_python_source,
    is_transformer_path,
    path_matches_prefix,
)
from aura_core.determinism import (
    ENTROPY_PATTERNS,
    LLM_PATTERNS,
    iter_added_lines,
    iter_changed_files,
)

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
            "import random",
            "from random import randint",
            "from numpy import random",
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
        [
            "tools/test_discovery.py",
            "core/tests/test_x.py",
            "tests/test_y.py",
            "core/scripts/invivo_solana_test.py",
        ],
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


class TestPrefixBoundaries:
    """A prefix must end at a directory boundary, or a guard is trivially dodged."""

    @pytest.mark.parametrize(
        "path",
        [
            "core/src/aura_hive/config_bypass.py",
            "core/tests_backup/helper.py",
            "toolshed/script.py",
        ],
    )
    def test_sibling_names_are_not_exempt(self, path: str) -> None:
        assert not is_exempt(path, EXEMPT + ("tools",))

    def test_the_prefix_itself_matches(self) -> None:
        assert path_matches_prefix("tools/membrane_check.py", "tools/membrane_check.py")
        assert path_matches_prefix("core/tests/x.py", "core/tests")

    def test_a_sibling_of_a_protected_file_does_not_match(self) -> None:
        """`membrane_bypass.py` is the name someone dodging a guard would pick."""
        assert not path_matches_prefix(
            "core/src/aura_hive/hive/membrane_bypass.py",
            "core/src/aura_hive/hive/membrane",
        )
        assert not path_matches_prefix(
            "tools/membrane_check.py.bak", "tools/membrane_check.py"
        )

    def test_trailing_slash_and_backslashes_normalise(self) -> None:
        assert path_matches_prefix("core/tests/x.py", "core/tests/")
        assert path_matches_prefix("core\\tests\\x.py", "core/tests")


class TestDiffParsing:
    def test_added_line_beginning_with_plus_plus_is_not_lost(self) -> None:
        """`++x` in the source shows up as `+++x`; it must not read as a header."""
        diff = (
            "--- a/core/src/aura_hive/hive/membrane/main.py\n"
            "+++ b/core/src/aura_hive/hive/membrane/main.py\n"
            "@@ -1,0 +2,2 @@\n"
            "+++x = 1\n"
            "+import litellm\n"
        )
        seen = list(iter_added_lines(diff))
        assert ("core/src/aura_hive/hive/membrane/main.py", "++x = 1") in seen
        assert ("core/src/aura_hive/hive/membrane/main.py", "import litellm") in seen

    def test_content_lines_inside_a_hunk_are_not_headers(self) -> None:
        """A deleted `-- x` renders as `--- x`, an added `++ y` as `+++ y`.

        Treating those as a header pair reset the file path to garbage and
        dropped the added line silently — a model import walked straight past.
        """
        diff = (
            "--- a/core/src/aura_hive/hive/membrane/main.py\n"
            "+++ b/core/src/aura_hive/hive/membrane/main.py\n"
            "@@ -1,2 +1,2 @@\n"
            "--- x\n"
            "+++ import litellm\n"
        )
        assert list(iter_added_lines(diff)) == [
            ("core/src/aura_hive/hive/membrane/main.py", "++ import litellm")
        ]

    def test_multi_file_diff_keeps_paths_straight(self) -> None:
        diff = (
            "diff --git a/one.py b/one.py\n--- a/one.py\n+++ b/one.py\n"
            "@@ -0,0 +1 @@\n+import dspy\n"
            "diff --git a/two.py b/two.py\n--- a/two.py\n+++ b/two.py\n"
            "@@ -0,0 +1 @@\n+import random\n"
        )
        assert list(iter_added_lines(diff)) == [
            ("one.py", "import dspy"),
            ("two.py", "import random"),
        ]

    def test_deleted_files_are_skipped(self) -> None:
        diff = "--- a/gone.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-import dspy\n"
        assert list(iter_added_lines(diff)) == []

    def test_new_file_header_is_read(self) -> None:
        diff = "--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+import dspy\n"
        assert list(iter_added_lines(diff)) == [("new.py", "import dspy")]


class TestChangedFiles:
    """Deleting the guard is a change to it; additions alone are the wrong question."""

    def test_a_pure_deletion_is_reported(self) -> None:
        diff = (
            "diff --git a/hive-manifest.yaml b/hive-manifest.yaml\n"
            "--- a/hive-manifest.yaml\n"
            "+++ b/hive-manifest.yaml\n"
            "@@ -1,3 +1,2 @@\n"
            ' version: "1.0"\n'
            "-protected_paths:\n"
            "-  - hive-manifest.yaml\n"
        )
        assert iter_changed_files(diff) == {"hive-manifest.yaml"}
        assert list(iter_added_lines(diff)) == []

    def test_a_removed_file_is_reported(self) -> None:
        diff = "diff --git a/x.py b/x.py\n--- a/x.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-import dspy\n"
        assert iter_changed_files(diff) == {"x.py"}

    def test_prefixless_diffs_work(self) -> None:
        """diff.noprefix drops the a/ and b/, so they are stripped, not required."""
        diff = "--- one.py\n+++ one.py\n@@ -0,0 +1 @@\n+x = 1\n"
        assert iter_changed_files(diff) == {"one.py"}

    def test_hunk_content_is_not_mistaken_for_a_header(self) -> None:
        diff = (
            "--- a/m.py\n+++ b/m.py\n@@ -1,2 +1,2 @@\n"
            "--- not/a/path\n+++ neither/is/this\n"
        )
        assert iter_changed_files(diff) == {"m.py"}


class TestEntropyCoverage:
    @pytest.mark.parametrize(
        "call",
        [
            "random.getrandbits(32)",
            "random.randbytes(16)",
            "rng = random.SystemRandom()",
            "rng = random.Random(0)",
            "x = random.betavariate(1, 2)",
            "x = random.triangular(0, 1)",
            "state = random.getstate()",
        ],
    )
    def test_any_attribute_on_the_module_counts(self, call: str) -> None:
        """An enumeration of names missed 16 of 27 public callables."""
        assert check_determinism("core/src/aura_hive/hive/membrane/main.py", call, ())

    @pytest.mark.parametrize(
        "line",
        [
            "self.random.choice(x)",
            "obj.random.seed(1)",
            "randomiser.apply()",
        ],
    )
    def test_an_attribute_named_random_on_something_else_does_not(
        self, line: str
    ) -> None:
        assert (
            check_determinism("core/src/aura_hive/hive/membrane/main.py", line, ())
            is None
        )


def test_patterns_are_compiled_and_non_empty() -> None:
    assert LLM_PATTERNS and ENTROPY_PATTERNS
    assert all(hasattr(p, "search") for p in LLM_PATTERNS + ENTROPY_PATTERNS)
