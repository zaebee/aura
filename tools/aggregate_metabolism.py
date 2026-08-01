"""Merge per-run metabolic records into one deduplicated JSONL file.

Runs outside the measured loop, so it may commit freely.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def aggregate(lines: list[str]) -> tuple[list[str], int, int]:
    """Deduplicate by cycle_id, preserving first-seen order.

    Returns (deduplicated_lines, unknown_usage_count, malformed_count). Both
    counts must be reported rather than absorbed: rows with unknown usage cannot
    enter a cost baseline, and a large share of either means the data is
    unusable rather than merely noisy.
    """
    seen: set[str] = set()
    kept: list[str] = []
    unknown = 0
    malformed = 0

    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            malformed += 1
            continue
        cycle_id = record.get("cycle_id")
        if not cycle_id:
            # A record with no cycle_id cannot be deduplicated. Letting None
            # into `seen` would make the first such row swallow every later
            # one — silent loss, which is the failure mode this file exists to
            # avoid. Drop it, but count it.
            malformed += 1
            continue
        if cycle_id in seen:
            continue
        seen.add(cycle_id)
        kept.append(raw)
        if record.get("prompt_tokens") is None:
            unknown += 1

    return kept, unknown, malformed


def main() -> int:
    out = Path(sys.argv[1])
    sources = [Path(p) for p in sys.argv[2:]]

    lines: list[str] = []
    if out.exists():
        lines.extend(out.read_text(encoding="utf-8").splitlines())
    for source in sources:
        lines.extend(source.read_text(encoding="utf-8").splitlines())

    kept, unknown, malformed = aggregate(lines)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(kept) + "\n", encoding="utf-8")

    total = len(kept)
    share = (unknown / total * 100) if total else 0.0
    sys.stdout.write(
        f"records={total} unknown_usage={unknown} ({share:.1f}%) "
        f"malformed={malformed}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
