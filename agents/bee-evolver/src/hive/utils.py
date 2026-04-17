from pathlib import Path


def find_hive_root() -> Path:
    """Find the repository root by searching upwards for hive-manifest.yaml."""
    p = Path(__file__).resolve()
    for parent in [p] + list(p.parents):
        if (parent / "hive-manifest.yaml").exists():
            return parent
        if (parent / "core").exists() and (parent / "api-gateway").exists():
            return parent
    return Path.cwd()
