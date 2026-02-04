"""
Manifest Loader - Reads hive-manifest.yaml for geography data.

Provides backward-compatible access to MACRO_ATCG_FOLDERS, ALLOWED_ROOT_FILES,
and ALLOWED_CHAMBERS from the language-agnostic YAML file.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


def find_hive_root() -> Path:
    """Find the repository root by searching upwards for markers."""
    p = Path(__file__).resolve()
    for parent in [p] + list(p.parents):
        # Check for hive-manifest.yaml first (new standard)
        if (parent / "hive-manifest.yaml").exists():
            return parent
        # Fallback: Monorepo markers
        if (parent / "core").exists() and (parent / "api-gateway").exists():
            return parent
    return Path.cwd()


@lru_cache(maxsize=1)
def _load_manifest() -> dict[str, Any]:
    """Load and cache the hive manifest."""
    root = find_hive_root()
    manifest_path = root / "hive-manifest.yaml"

    if not manifest_path.exists():
        # Return defaults if manifest doesn't exist
        return {
            "macro_atcg_folders": [],
            "allowed_root_files": [],
            "allowed_chambers": {},
        }

    with open(manifest_path) as f:
        return yaml.safe_load(f)


def get_macro_atcg_folders() -> list[str]:
    """Get the list of macro ATCG folders."""
    return _load_manifest().get("macro_atcg_folders", [])


def get_allowed_root_files() -> list[str]:
    """Get the list of allowed root files."""
    return _load_manifest().get("allowed_root_files", [])


def get_allowed_chambers() -> dict[str, str]:
    """Get the mapping of paths to chamber names."""
    return _load_manifest().get("allowed_chambers", {})


# Backward-compatible aliases (call functions to get values)
MACRO_ATCG_FOLDERS = get_macro_atcg_folders()
ALLOWED_ROOT_FILES = get_allowed_root_files()
ALLOWED_CHAMBERS = get_allowed_chambers()
