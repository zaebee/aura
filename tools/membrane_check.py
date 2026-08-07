#!/usr/bin/env python3
"""
The membrane check: the deterministic half of the Hive audit.

bee.Keeper mixes two very different things in one job — mechanical structural
rules, and an LLM reading the diff for architectural opinions. Only the first
can carry a guarantee, so only the first belongs in a blocking check.

This script runs that half and nothing else. It deliberately depends on no
project code: it loads `determinism.py` straight off disk and parses the manifest
with PyYAML. A guard that has to import the runtime it guards is not a guard —
it fails whenever the thing it is checking fails to build.

Usage:
    python tools/membrane_check.py --base origin/main
    python tools/membrane_check.py --diff-file some.patch
    python tools/membrane_check.py --base origin/main --author "bee.Evolver"

Exit codes: 0 clean, 1 heresies found, 2 could not run.
"""

from __future__ import annotations

import argparse
import importlib.util
import shutil

# Fixed argument lists, never a shell; see _git below.
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "hive-manifest.yaml"
DETERMINISM = ROOT / "packages" / "aura-core" / "src" / "aura_core" / "determinism.py"


def load_determinism() -> Any:
    """Load determinism.py directly, without importing the aura_core package."""
    spec = importlib.util.spec_from_file_location("_determinism", DETERMINISM)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"cannot load {DETERMINISM}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def str_list(manifest: dict[str, Any], key: str) -> list[str]:
    """
    Read a list-of-strings key, refusing anything else.

    Silently skipping an unreadable entry is the wrong failure for a guard: a
    `protected_paths` item that parses as None would stop protecting that path
    and say nothing. Fail where someone will see it.
    """
    value = manifest.get(key) or []
    if not isinstance(value, list):
        raise SystemExit(f"hive-manifest.yaml: `{key}` must be a list")
    bad = [item for item in value if not isinstance(item, str)]
    if bad:
        raise SystemExit(f"hive-manifest.yaml: `{key}` has non-string entries: {bad!r}")
    return value


def load_manifest() -> dict[str, Any]:
    with open(MANIFEST, encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return data if isinstance(data, dict) else {}


def _git(*args: str) -> str:
    """
    Run git with a fixed argument list. No shell, so a hostile ref name cannot
    escape into a command; the worst it can do is make git report an error.
    """
    git = shutil.which("git")
    if git is None:
        raise SystemExit("git not found on PATH")
    # Absolute path, list arguments, shell=False.
    result = subprocess.run(  # nosec B603
        [git, *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def read_diff(base: str | None, diff_file: str | None) -> str:
    if diff_file:
        return Path(diff_file).read_text(encoding="utf-8")
    if not base:
        raise SystemExit("one of --base or --diff-file is required")
    return _git("diff", "--unified=0", f"{base}...HEAD")


def changed_files(
    base: str | None, diff_file: str | None, determinism: Any
) -> set[str]:
    if diff_file:
        diff = Path(diff_file).read_text(encoding="utf-8")
        # Every touched file, not only those that gained a line: deleting the
        # guard is a change to it.
        return determinism.iter_changed_files(diff)
    if not base:
        raise SystemExit("one of --base or --diff-file is required")
    listing = _git("diff", "--name-only", f"{base}...HEAD")
    return {line.strip() for line in listing.splitlines() if line.strip()}


def check_root_sprouts(files: set[str], manifest: dict[str, Any]) -> list[str]:
    """A new file at the repository root must be declared in the manifest."""
    allowed = set(str_list(manifest, "allowed_root_files"))
    macro = set(str_list(manifest, "macro_atcg_folders"))
    heresies = []
    for path in sorted(files):
        if "/" in path or path.startswith("."):
            continue
        # A deleted or renamed-away root file still shows up in the diff. It is
        # leaving, not sprouting.
        if not (ROOT / path).exists():
            continue
        if path not in allowed and path not in macro:
            heresies.append(
                f"Root Heresy: `{path}` is a new sprout in the repository root. "
                f"Move it into a nucleotide, or declare it in `allowed_root_files`."
            )
    return heresies


def check_protected_surface(
    files: set[str], manifest: dict[str, Any], author: str | None, matches: Any
) -> list[str]:
    """An automated author may not edit the membrane that checks it."""
    if not author:
        return []
    automated = {a.lower() for a in str_list(manifest, "automated_authors")}
    if author.lower() not in automated:
        return []
    protected = str_list(manifest, "protected_paths")
    touched = sorted(f for f in files if any(matches(f, p) for p in protected))
    if not touched:
        return []
    listing = "\n".join(f"    - {f}" for f in touched)
    return [
        f"Protected Surface: author `{author}` is automated and this change "
        f"touches the membrane's own surface:\n{listing}\n"
        f"    The loop may not widen its permissions or weaken its guard. "
        f"A human must author this change."
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", help="base ref to diff against, e.g. origin/main")
    parser.add_argument("--diff-file", help="read a unified diff from a file instead")
    parser.add_argument("--author", help="pull request author login or git name")
    parser.add_argument(
        "--github-output",
        help="path to write protected_touched=true|false for a workflow step",
    )
    args = parser.parse_args()

    determinism = load_determinism()
    manifest = load_manifest()
    exempt = str_list(manifest, "determinism_exempt_paths")

    diff = read_diff(args.base, args.diff_file)
    files = changed_files(args.base, args.diff_file, determinism)

    heresies: list[str] = []
    for path, line in determinism.iter_added_lines(diff):
        heresy = determinism.check_determinism(path, line, exempt)
        if heresy:
            heresies.append(heresy)

    heresies.extend(check_root_sprouts(files, manifest))
    matches = determinism.path_matches_prefix
    heresies.extend(check_protected_surface(files, manifest, args.author, matches))

    if args.github_output:
        protected = str_list(manifest, "protected_paths")
        touched = any(any(matches(f, p) for p in protected) for f in files)
        with open(args.github_output, "a", encoding="utf-8") as handle:
            handle.write(f"protected_touched={str(touched).lower()}\n")

    # Same rule reported twice adds noise without adding information.
    unique = list(dict.fromkeys(heresies))

    if not unique:
        print(f"Membrane clean: {len(files)} changed file(s), no heresies.")
        return 0

    print(f"Membrane found {len(unique)} heresy/heresies:\n", file=sys.stderr)
    for heresy in unique:
        print(f"  - {heresy}\n", file=sys.stderr)
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # pragma: no cover - surfaced as an infra failure
        print(f"membrane check could not run: {exc}", file=sys.stderr)
        sys.exit(2)
