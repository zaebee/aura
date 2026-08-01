"""Per-cycle metabolic record — one JSONL line per metabolic cycle."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Literal

Outcome = Literal["success", "llm_error", "generator_error", "connector_error"]


@dataclass
class MetabolicRecord:
    """One cycle's cost. Unknown numeric fields are None, never 0."""

    ts: str
    bee: str
    cycle_id: str
    git_sha: str
    model: str | None
    llm_calls: int
    prompt_tokens: int | None
    completion_tokens: int | None
    usd: float | None
    wall_clock_s: float
    outcome: Outcome
    dry_run: bool
    proposals: int | None = None
    applied: int | None = None

    def to_json_line(self) -> str:
        """Serialise to a single newline-terminated JSON line."""
        return json.dumps(asdict(self), sort_keys=True) + "\n"
