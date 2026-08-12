"""
Resolve a dispute token into the receipt it names, and say whether it holds.

`make resolve-dispute TOKEN=…`

The counterparty holds a random per-decision token and nothing else — no
digest, no prefix, nothing derived from the decision (§3.4). This is the tool
that turns that citation into the decision an auditor can read.

The query itself lives in the persistence protein rather than here, so an
internal endpoint later is a second thin caller rather than a second
implementation.
"""

import argparse
import asyncio
import json
import sys
from typing import Any

from aura_core_gen.aura.core.v1 import DecisionReceipt
from aura_hive.config import get_settings
from aura_hive.hive.cortex import HiveCell
from aura_hive.hive.membrane.receipt import verify


def render(receipt: dict[str, Any] | None) -> tuple[str, int]:
    """
    The report and the exit code.

    A token nobody issued is an answer rather than a fault, so it exits 0. The
    tool failing to reach the database is a different thing and exits non-zero
    — that is the tool not answering, handled by the caller below.
    """
    if receipt is None:
        return ("not found — no decision was recorded under that token", 0)

    parsed = DecisionReceipt().from_dict(receipt)
    result = verify(parsed)

    lines = [
        f"decision_id    {parsed.decision_id}",
        f"request_id     {parsed.request_id}",
        f"issued_at      {parsed.issued_at}",
        f"outcome        {parsed.outcome}",
        f"outcome_gate   {parsed.outcome_gate or '—'}",
        f"override_scope {parsed.override_scope or '—'}",
        f"claim_hash     {parsed.claim_hash}",
        f"emission_hash  {parsed.emission_hash}",
        "",
        f"verify         {'ok' if result.ok else 'FAILED'}",
        f"               {'attested' if result.attested else 'not attested'}",
    ]
    for failure in result.failures:
        lines.append(f"  failure      {failure}")
    if result.unverifiable:
        lines.append(f"  unverifiable {', '.join(result.unverifiable)}")
    lines.append("")
    lines.append(json.dumps(receipt, indent=2, sort_keys=True))

    return ("\n".join(lines), 0 if result.ok else 1)


async def _lookup(token: str) -> dict[str, Any] | None:
    cell = HiveCell(get_settings())
    await cell._init_proteins()
    observation = await cell.registry.execute(
        "persistence", "find_receipt_by_dispute_token", {"dispute_token": token}
    )
    if not observation.success:
        if observation.error == "not_found":
            return None
        raise RuntimeError(observation.error)
    meta = observation.metadata.to_dict() if observation.metadata else {}
    receipt = meta.get("receipt")
    # An empty payload reads as "not found" rather than as a receipt.
    # Returning `{}` here would hand `render` an empty document, which then
    # reports a verification failure — telling an auditor the record is broken
    # when what actually happened is that nothing came back.
    return dict(receipt) if receipt else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("token", help="the dispute_token the counterparty cited")
    args = parser.parse_args()

    try:
        receipt = asyncio.run(_lookup(args.token))
    except Exception as e:
        print(f"could not reach the archive: {e}", file=sys.stderr)
        return 2

    report, code = render(receipt)
    print(report)
    return code


if __name__ == "__main__":
    sys.exit(main())
