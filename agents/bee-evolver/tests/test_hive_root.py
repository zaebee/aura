"""The Hive root must be the repo, not the bee's own directory.

Getting this wrong is silent: the agent still runs, still proposes, still
reports success — it just cannot see the Hive and never receives its persona.
"""

from pathlib import Path

from hive.utils import find_hive_root


def _hive(tmp_path: Path) -> Path:
    """Build a miniature Hive with a per-bee manifest nested inside it."""
    repo = tmp_path / "aura"
    (repo / "core").mkdir(parents=True)
    (repo / "api-gateway").mkdir(parents=True)
    (repo / "hive-manifest.yaml").write_text("hive: root\n")

    bee = repo / "agents" / "bee-evolver"
    (bee / "src" / "hive").mkdir(parents=True)
    (bee / "hive-manifest.yaml").write_text("bee: evolver\n")
    (bee / "prompts").mkdir()
    (bee / "prompts" / "bee_evolver.md").write_text("persona")
    return repo


def test_root_is_the_repo_not_the_bee(tmp_path):
    repo = _hive(tmp_path)
    start = repo / "agents" / "bee-evolver" / "src" / "hive" / "utils.py"

    assert find_hive_root(start) == repo


def test_persona_path_resolves_from_that_root(tmp_path):
    """The transformer builds the persona path relative to the root. With the
    bee's own directory as root it doubled into agents/bee-evolver/agents/...
    and silently fell back to a one-line prompt."""
    repo = _hive(tmp_path)
    start = repo / "agents" / "bee-evolver" / "src" / "hive" / "utils.py"

    root = find_hive_root(start)
    persona = root / "agents/bee-evolver/prompts/bee_evolver.md"

    assert persona.exists(), f"persona should resolve, got {persona}"
    assert persona.read_text() == "persona"


def test_outermost_manifest_wins_without_the_macro_atcg_marker(tmp_path):
    """Fallback path: no core/ + api-gateway/ to key on, so the outermost
    manifest decides rather than the first one encountered."""
    repo = tmp_path / "aura"
    bee = repo / "agents" / "bee-evolver" / "src" / "hive"
    bee.mkdir(parents=True)
    (repo / "hive-manifest.yaml").write_text("hive: root\n")
    (repo / "agents" / "bee-evolver" / "hive-manifest.yaml").write_text("bee\n")

    assert find_hive_root(bee / "utils.py") == repo
