"""
Tests for the membrane check script.

The script is deliberately not importable as a package — it loads determinism.py
off disk so the guard does not depend on the runtime it guards — so the tests
load it the same way.
"""

import importlib.util
from pathlib import Path
from typing import Any

import pytest
from aura_core.determinism import path_matches_prefix

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "membrane_check.py"


@pytest.fixture(scope="module")
def membrane() -> Any:
    spec = importlib.util.spec_from_file_location("_membrane_check", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestRootSprouts:
    def test_undeclared_root_file_is_flagged(self, membrane: Any) -> None:
        manifest = {"allowed_root_files": ["README.md"], "macro_atcg_folders": ["core"]}
        # This test file's own name is not on disk at the repo root, so use one
        # that is: the manifest itself, deliberately left out of allowed here.
        heresies = membrane.check_root_sprouts({"hive-manifest.yaml"}, manifest)
        assert len(heresies) == 1
        assert "Root Heresy" in heresies[0]

    def test_declared_root_file_is_fine(self, membrane: Any) -> None:
        manifest = {
            "allowed_root_files": ["hive-manifest.yaml"],
            "macro_atcg_folders": [],
        }
        assert membrane.check_root_sprouts({"hive-manifest.yaml"}, manifest) == []

    def test_a_deleted_root_file_is_not_a_sprout(self, membrane: Any) -> None:
        """A removed file still appears in the diff. It is leaving, not sprouting."""
        manifest = {"allowed_root_files": [], "macro_atcg_folders": []}
        assert membrane.check_root_sprouts({"file_that_was_deleted.py"}, manifest) == []

    def test_nested_paths_are_not_root_files(self, membrane: Any) -> None:
        manifest = {"allowed_root_files": [], "macro_atcg_folders": []}
        assert membrane.check_root_sprouts({"core/src/x.py"}, manifest) == []

    def test_empty_yaml_keys_do_not_crash(self, membrane: Any) -> None:
        """`allowed_root_files:` with nothing under it parses as None."""
        manifest: dict[str, Any] = {
            "allowed_root_files": None,
            "macro_atcg_folders": None,
        }
        assert membrane.check_root_sprouts({"core/src/x.py"}, manifest) == []


class TestProtectedSurface:
    MANIFEST = {
        "automated_authors": ["bee.Evolver", "github-actions[bot]"],
        "protected_paths": ["hive-manifest.yaml", "core/src/aura_hive/hive/membrane"],
    }

    def test_automated_author_touching_the_guard_is_blocked(
        self, membrane: Any
    ) -> None:
        heresies = membrane.check_protected_surface(
            {"hive-manifest.yaml"}, self.MANIFEST, "bee.Evolver", path_matches_prefix
        )
        assert len(heresies) == 1
        assert "Protected Surface" in heresies[0]

    def test_author_match_is_case_insensitive(self, membrane: Any) -> None:
        heresies = membrane.check_protected_surface(
            {"hive-manifest.yaml"}, self.MANIFEST, "BEE.EVOLVER", path_matches_prefix
        )
        assert len(heresies) == 1

    def test_human_author_is_not_blocked(self, membrane: Any) -> None:
        assert (
            membrane.check_protected_surface(
                {"hive-manifest.yaml"}, self.MANIFEST, "zaebee", path_matches_prefix
            )
            == []
        )

    def test_automated_author_elsewhere_is_fine(self, membrane: Any) -> None:
        assert (
            membrane.check_protected_surface(
                {"core/src/aura_hive/hive/connector/main.py"},
                self.MANIFEST,
                "bee.Evolver",
                path_matches_prefix,
            )
            == []
        )

    def test_sibling_of_a_protected_directory_does_not_match(
        self, membrane: Any
    ) -> None:
        """`membrane_bypass.py` is the name someone dodging the guard would pick."""
        assert (
            membrane.check_protected_surface(
                {"core/src/aura_hive/hive/membrane_bypass.py"},
                self.MANIFEST,
                "bee.Evolver",
                path_matches_prefix,
            )
            == []
        )

    def test_deleting_a_protected_file_still_counts(self, membrane: Any) -> None:
        """Removing the guard is the attack; deletions must not be filtered out."""
        heresies = membrane.check_protected_surface(
            {"core/src/aura_hive/hive/membrane/main.py"},
            self.MANIFEST,
            "bee.Evolver",
            path_matches_prefix,
        )
        assert len(heresies) == 1

    def test_no_author_means_no_check(self, membrane: Any) -> None:
        assert (
            membrane.check_protected_surface(
                {"hive-manifest.yaml"}, self.MANIFEST, None, path_matches_prefix
            )
            == []
        )

    def test_empty_yaml_keys_do_not_crash(self, membrane: Any) -> None:
        manifest: dict[str, Any] = {
            "automated_authors": None,
            "protected_paths": None,
        }
        assert (
            membrane.check_protected_surface(
                {"hive-manifest.yaml"}, manifest, "bee.Evolver", path_matches_prefix
            )
            == []
        )
