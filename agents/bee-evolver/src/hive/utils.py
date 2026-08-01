from pathlib import Path


def find_hive_root(start: Path | None = None) -> Path:
    """Find the Hive root — the OUTERMOST directory carrying hive-manifest.yaml.

    Every bee ships its own ``hive-manifest.yaml``, so returning the first match
    found walking upwards lands inside the agent instead of at the Hive root.
    For bee.Evolver that had two silent consequences:

    * the filesystem map it senses covered only its own directory (53 of 420
      files), so it could propose changes to nothing but itself;
    * the persona path, written relative to the repo root as
      ``agents/bee-evolver/prompts/bee_evolver.md``, resolved to a doubled path
      that does not exist — so the prompt fell back to a one-line default and
      every rule in the persona, including the unified-diff format contract,
      never reached the model.

    ``start`` exists so the search is testable; it defaults to this file.
    """
    p = (start or Path(__file__)).resolve()
    if not p.is_dir():
        p = p.parent
    outermost: Path | None = None

    for parent in [p] + list(p.parents):
        if (parent / "hive-manifest.yaml").exists():
            outermost = parent
        # The Macro-ATCG layout only exists at the repo root, so it is decisive.
        if (parent / "core").exists() and (parent / "api-gateway").exists():
            return parent

    if outermost is not None:
        return outermost
    return Path.cwd()
