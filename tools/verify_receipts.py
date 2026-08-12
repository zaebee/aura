"""
Check the receipts a running Hive left in its log.

`verify` has existed since the receipt did, and until now it ran only in tests:
no receipts were persisted, so the function that checks them had nothing to
check. The `membrane_receipt` log line already fires on every decision, which
makes the log the store and this the reader.

Reports what could not be checked as prominently as what failed. Every receipt
lists `emission_content` — this tool reads receipts, never the decisions they
describe, so a clean run means "these documents are well-formed and attributable",
not "these decisions were correct".
"""

import json
import sys
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from aura_core_gen.aura.core.v1 import DecisionReceipt
from aura_hive.hive.membrane.receipt import verify

_EVENT = "membrane_receipt"


@dataclass
class Summary:
    checked: int = 0
    ok: int = 0
    attested: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)
    unverifiable: Counter[str] = field(default_factory=Counter)


def read_receipts(lines: Iterable[str]) -> Iterator[DecisionReceipt]:
    """
    Pull receipts out of a structlog JSONL stream.

    A malformed line is skipped rather than raised on. This reads a stream
    someone else writes: a truncated last line in a rotated file must not stop
    the audit of everything before it.
    """
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict) or record.get("event") != _EVENT:
            continue
        payload = record.get("receipt")
        if not isinstance(payload, dict):
            continue
        try:
            yield DecisionReceipt().from_dict(payload)
        except Exception:  # nosec B112
            # Same rule as the JSON parse above: a receipt shape betterproto
            # cannot load is a malformed line, not a reason to stop reading
            # everything after it in someone else's log.
            continue


def summarise(receipts: Iterable[DecisionReceipt]) -> Summary:
    """Verify each receipt and tally what held, what did not, and what was skipped."""
    summary = Summary()
    for receipt in receipts:
        summary.checked += 1
        result = verify(receipt)
        if result.ok:
            summary.ok += 1
        if result.attested:
            summary.attested += 1
        # The prefix is a handle for correlating with the log, not a commitment.
        handle = receipt.canonical_prefix or "<no prefix>"
        for reason in result.failures:
            summary.failures.append((handle, reason))
        summary.unverifiable.update(result.unverifiable)
    return summary


def render(summary: Summary) -> str:
    lines = [
        f"checked:     {summary.checked}",
        f"ok:          {summary.ok}",
        f"attested:    {summary.attested}",
        f"failed:      {len(summary.failures)}",
    ]
    if summary.failures:
        lines.append("")
        lines.append("failures")
        lines.extend(f"  {handle}: {reason}" for handle, reason in summary.failures)
    if summary.unverifiable:
        lines.append("")
        lines.append(
            "not checked (no verifier can establish these from a receipt alone)"
        )
        lines.extend(
            f"  {name}: {count}" for name, count in sorted(summary.unverifiable.items())
        )
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    """
    Read a log file named on the command line, or stdin when none is.

    Exits non-zero when any receipt failed, so this can gate a job. An empty
    stream is not a failure — it means nothing was decided, which is a fact
    about the log rather than about the receipts in it.
    """
    if len(argv) > 1 and argv[1] not in ("-", ""):
        lines: Iterable[str] = Path(argv[1]).read_text(encoding="utf-8").splitlines()
    else:
        lines = sys.stdin

    summary = summarise(read_receipts(lines))
    print(render(summary))
    return 1 if summary.failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
