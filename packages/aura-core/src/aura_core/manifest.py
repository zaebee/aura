"""
Manifest Loader - Reads hive-manifest.yaml for geography data.

Provides backward-compatible access to MACRO_ATCG_FOLDERS, ALLOWED_ROOT_FILES,
and ALLOWED_CHAMBERS from the language-agnostic YAML file.
"""

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_DEFAULT_MANIFEST: dict[str, Any] = {
    "macro_atcg_folders": [],
    "allowed_root_files": [],
    "allowed_chambers": {},
}


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
        logger.warning("hive-manifest.yaml not found at %s, using defaults", root)
        return _DEFAULT_MANIFEST

    try:
        with open(manifest_path) as f:
            data = yaml.safe_load(f)
            if data is None:
                logger.warning(
                    "hive-manifest.yaml at %s is empty or invalid, using defaults",
                    manifest_path,
                )
                return _DEFAULT_MANIFEST
            if not isinstance(data, dict):
                logger.warning(
                    "hive-manifest.yaml at %s has invalid format, using defaults",
                    manifest_path,
                )
                return _DEFAULT_MANIFEST
            return data
    except yaml.YAMLError as e:
        logger.warning(
            "Failed to parse hive-manifest.yaml at %s: %s, using defaults",
            manifest_path,
            e,
        )
        return _DEFAULT_MANIFEST


def get_macro_atcg_folders() -> list[str]:
    """Get the list of macro ATCG folders."""
    result: list[str] = _load_manifest().get("macro_atcg_folders", [])
    return result


def get_allowed_root_files() -> list[str]:
    """Get the list of allowed root files."""
    result: list[str] = _load_manifest().get("allowed_root_files", [])
    return result


def get_allowed_chambers() -> dict[str, str]:
    """Get the mapping of paths to chamber names."""
    result: dict[str, str] = _load_manifest().get("allowed_chambers", {})
    return result


# Backward-compatible aliases (call functions to get values)
MACRO_ATCG_FOLDERS = get_macro_atcg_folders()
ALLOWED_ROOT_FILES = get_allowed_root_files()
ALLOWED_CHAMBERS = get_allowed_chambers()
