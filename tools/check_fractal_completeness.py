#!/usr/bin/env python3
"""Fractal-completeness gate: measure ATCG-M nucleotide coverage per service.

Reads ``docs/ontology/patterns.yaml`` and enforces a BASELINE-LOCK on the
``fractal_completeness`` invariant (self-model rule ``fractal_completeness``):
a service must not lose a nucleotide it currently has. This is the repo-native,
CI-runnable measurement of what CGIS ``cgis_drift`` reports interactively — no
external MCP server required.

Exit status:
  0  every service still has its baseline nucleotides (drift flat or improved)
  1  regression: a declared-present nucleotide is missing on disk
  2  the patterns file is malformed or absent

Wired into ``make lint`` so the ``quality`` CI job runs it on every PR.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

PATTERNS = Path("docs/ontology/patterns.yaml")


def _module_exists(hive_root: Path, module: str) -> bool:
    """A nucleotide is present as a package dir or a single-file module."""
    base = hive_root / module
    if base.is_dir():
        return True
    return any(
        (hive_root / f"{module}{ext}").is_file()
        for ext in (".py", ".ts", ".tsx", ".js")
    )


def main(root: Path) -> int:
    patterns_path = root / PATTERNS
    if not patterns_path.is_file():
        print(f"FATAL: {PATTERNS} not found", file=sys.stderr)
        return 2

    try:
        spec = yaml.safe_load(patterns_path.read_text())
    except yaml.YAMLError as exc:  # pragma: no cover - defensive
        print(f"FATAL: cannot parse {PATTERNS}: {exc}", file=sys.stderr)
        return 2

    nucleotides = spec["nucleotides"]  # code -> {module, role}
    orchestrator_module = spec["orchestrator"]["module"]
    full_set = set(nucleotides)

    regressions: list[str] = []
    improvements: list[str] = []

    print("ATCG-M fractal completeness (baseline-lock)\n")
    for name, svc in spec["services"].items():
        hive_root = root / svc["hive_root"]
        present = set(svc["present"])

        # Baseline-lock: every declared-present nucleotide must exist on disk.
        missing = [
            code
            for code in present
            if not _module_exists(hive_root, nucleotides[code]["module"])
        ]
        for code in missing:
            regressions.append(
                f"{name}: nucleotide {code} ({nucleotides[code]['module']}) "
                f"is in the baseline but missing at {svc['hive_root']}"
            )

        # Drift-may-only-improve: a closed gap should tighten the baseline.
        gap = sorted(full_set - present)
        appeared = [
            code
            for code in gap
            if _module_exists(hive_root, nucleotides[code]["module"])
        ]
        for code in appeared:
            improvements.append(
                f"{name}: nucleotide {code} ({nucleotides[code]['module']}) now "
                f"exists — tighten `present` in {PATTERNS}"
            )

        if svc.get("orchestrator") and not (hive_root / orchestrator_module).is_dir():
            regressions.append(
                f"{name}: orchestrator ({orchestrator_module}) is in the baseline "
                f"but missing at {svc['hive_root']}"
            )

        coverage = f"{len(present)}/{len(full_set)}"
        status = "COMPLETE" if svc.get("complete") else f"gap: {','.join(gap) or '-'}"
        mark = "FAIL" if missing else "ok"
        print(f"  [{mark:>4}] {name:<12} {coverage}  {status}")

    # Synapse mini-metabolism: receptor -> translator -> effector (A -> T -> C·G).
    synapse_spec = spec.get("synapse_pattern")
    if synapse_spec:
        stages = list(synapse_spec["stages"])
        print(
            "\nSynapse mini-metabolism (receptor->translator->effector = A->T->C·G)\n"
        )
        for name, syn in synapse_spec.get("synapses", {}).items():
            syn_root = root / syn["root"]
            missing = [s for s in stages if not _module_exists(syn_root, s)]
            for stage in missing:
                regressions.append(
                    f"synapse {name}: stage {stage} missing at {syn['root']}"
                )
            mark = "FAIL" if missing else "ok"
            present_stages = ",".join(s for s in stages if s not in missing)
            print(f"  [{mark:>4}] {name:<12} {present_stages}")

    print()
    for line in improvements:
        print(f"  improved: {line}")
    for line in regressions:
        print(f"  REGRESSION: {line}", file=sys.stderr)

    if regressions:
        print(f"\nfractal_completeness FAILED: {len(regressions)} regression(s)")
        return 1
    print("\nfractal_completeness OK: no service dropped below its baseline")
    return 0


if __name__ == "__main__":
    # Resolve repo root relative to this file (tools/ -> repo root).
    sys.exit(main(Path(__file__).resolve().parent.parent))
