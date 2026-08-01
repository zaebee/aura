# Metabolism instrumentation — design

**Status:** design, approved, not implemented (2026-08-01)
**Branch:** `feat/metabolism-instrumentation`
**Base:** `origin/main` @ 9d4f733

## Why

The Hive spends tokens and money and keeps no usable record of it.
`token_usage` exists as a proto field (`dna.proto:274`,
`metabolism.proto:340`) and is populated in both bees' Transformers, but:

- `bee.Keeper` appends it to `HIVE_STATE.md` truncated at `old_log[:5000]`
  characters and unstructured;
- `bee.Evolver` writes it into a Telegram message and persists nothing;
- there is no USD figure anywhere, and the only Prometheus counters
  (`negotiation_total`, `negotiation_accepted_total`, `heartbeat_total`) are
  not cost-related.

So the Hive cannot answer "what does one cycle cost?" — which is the
precondition for every downstream claim about efficiency.

This work is **Gate 0** of an external pre-registered experiment
(`codegraph-brain`, `docs/specs/2026-08-01-aura-autoevolution-poc.md` §6). That
gate requires ≥ 20 baseline cycles of `{prompt_tokens, completion_tokens, usd,
wall_clock}` before any comparison is run. Gate 0 costs **no additional LLM
spend** — it records what is already being spent.

The instrumentation is useful independently of whether that experiment ever
runs: a cost record is worth having on its own.

## Scope

**In:** per-cycle metabolic records for `bee.Keeper` and `bee.Evolver`;
artifact-based collection; a separate aggregation workflow; a dry-run mode for
`bee.Evolver`; first test coverage for both agents.

**Out:** the experiment itself; any change to what the bees decide or propose;
dashboards; core-service or gateway instrumentation; a `proto` message for the
record (see Decisions).

## Decisions

| # | decision | why |
|---|---|---|
| 1 | Instrument **both** bees | Same code; `bee.Keeper` accumulates cycles in days (PR + push + 18h cron) and validates the instrumentation long before `bee.Evolver` has enough data. |
| 2 | **Artifact** collection, not a repo commit from the agent | A commit to `main` per cycle would trigger `bee.Keeper` (it fires on push to `main`), so the instrument would drive the system it measures. `paths-ignore` suppresses that, but then baseline integrity rests on one line of config, and a future edit contaminates it **silently**. Artifacts need no write access at all. |
| 3 | Durability via a **separate aggregation workflow** | Splits collection (must not perturb) from durability (may commit freely, runs outside the measured loop). Also removes the artifact-expiry problem, since aggregation runs long before 90 days. |
| 4 | Record is written by the **Connector** | I/O is the Connector's declared job (`FOUNDATIONS.md` §2). Instrumentation that measures boundary compliance must not itself violate the boundary. |
| 5 | **Local Pydantic model + JSONL**, not a proto message | The record is never sent between services and never crosses NATS; its consumers are `jq` and one aggregation script. The Binary Bloodstream convention governs inter-service traffic; generating a proto for a local telemetry line would add a build step and buy nothing. *Deliberate deviation, called out for review.* |
| 6 | `bee.Evolver` gets a **dry-run** mode | At the cadence needed to collect a baseline, real runs would open a PR and issues per cycle. Beyond tracker noise, the Evolver's own PRs land in git history, which feeds its own Aggregator — the baseline would drift as a consequence of measuring it. |

## Architecture

One concept: a **metabolic record** — one JSONL line per cycle per bee.

```
Transformer  ──usage returned as data──►  metabolism.execute()
                                               │  monotonic() around the cycle
                                               │  try/finally
                                               ▼
                                    Connector.write_metabolic_record()
                                               │
                                               ▼
                                     $AURA_METABOLISM_LOG        (ephemeral, on the runner)
                                               │
                                        upload-artifact
                                               ▼
                            ───────── outside the measured loop ─────────
                              aggregation workflow: download → dedup → commit
```

The `try/finally` placement is load-bearing. A cycle can fail inside the
Transformer, and **failed cycles must still be recorded** — their tokens belong
in the numerator of any cost-per-success figure. Recording only successful
cycles would make "fail fast and cheap" look like an improvement.

`write_metabolic_record()` is a **separate Connector method, not called from
`act()`**. This matters for `outcome: "connector_error"`: if the record were
written inside `act()`, a failing `act()` would take the record down with it and
the one outcome class that most needs recording would be the one never recorded.
The `finally` block in `metabolism.execute()` calls the writer directly.

## Record schema

```json
{
  "ts": "2026-08-01T18:40:12Z",
  "bee": "evolver",
  "cycle_id": "20260801-184012",
  "git_sha": "abc1234",
  "model": "mistral/mistral-large-latest",
  "llm_calls": 1,
  "prompt_tokens": 3412,
  "completion_tokens": 688,
  "usd": 0.0141,
  "wall_clock_s": 47.3,
  "outcome": "success",
  "proposals": 3,
  "applied": 2,
  "dry_run": true
}
```

| field | notes |
|---|---|
| `model` | the model **actually used**, not the configured one — both bees have a fallback (`gpt-4o-mini`, ollama) with a different cost profile, and mixing them into one median measures a blend |
| `llm_calls` | **`bee.Keeper` makes more than one call per cycle** — `_summarize_diff` and `_call_llm`, plus a DSPy path that reports usage separately. Tokens are summed across calls; without this the Keeper's baseline is undercounted by construction |
| `prompt_tokens` / `completion_tokens` / `usd` | `null` when unknown — **never `0`** (see Error handling) |
| `outcome` | `success` \| `llm_error` \| `generator_error` \| `connector_error` — the denominator of any per-success figure |
| `proposals` / `applied` | Evolver only. `proposals` = `len(plan.improvements)`. **`applied` = patchable improvements that applied without landing in `apply_errors`** — deliberately *not* called "accepted": `bee.Evolver` runs no preflight today (no pytest/mypy/ruff anywhere in its source or workflow; that gating happens downstream in ordinary PR CI). Naming the field "accepted" would imply a check that does not exist. Recording what is genuinely available now keeps the format stable when a real preflight arrives. |
| `dry_run` | records the mode; samples from different modes must not be pooled |

`usd` comes from `litellm.completion_cost(...)`. Verified against the pinned
version: litellm 1.81.4 prices `mistral/mistral-large-latest` correctly. No new
dependency, no hand-maintained price table.

## Components

Note the **path asymmetry** — `bee.Keeper` was restructured under
`src/aura_keeper/`, `bee.Evolver` was not. Getting this wrong is the most likely
mechanical mistake in implementation.

| component | path | est. |
|---|---|---|
| `MetabolicRecord` model | `bee-keeper/src/aura_keeper/hive/records.py`<br>`bee-evolver/src/hive/records.py` | ~15 lines each |
| `write_metabolic_record()` | `bee-keeper/src/aura_keeper/hive/connector/__init__.py`<br>`bee-evolver/src/hive/connector/__init__.py` | ~30 lines each |
| usage capture (split + cost) | `bee-keeper/src/aura_keeper/hive/transformer/__init__.py`, `bee-evolver/src/hive/transformer/__init__.py` | ~6 lines each |
| timing + `try/finally` | `bee-keeper/src/aura_keeper/hive/metabolism.py`<br>`bee-evolver/src/hive/metabolism.py` | ~10 lines each |
| `EVOLVER_DRY_RUN` | `bee-evolver/src/hive/connector/__init__.py` + `config.py` | ~8 lines |
| artifact upload step | `.github/workflows/bee-keeper.yaml`, `bee-evolver.yaml` | 1 step each |
| aggregation workflow | `.github/workflows/metabolism-aggregate.yaml` | ~40 lines |
| tests | `agents/bee-{keeper,evolver}/tests/` + a line in `make test` | 6 tests |

## Error handling

**Swallow inside the bee, shout outside it.**

The writer is wrapped in `try/except`: on failure it logs a `structlog` warning
and the cycle continues. An instrument that crashes the organism is worse than
no instrument.

But a silently failing writer means weeks of empty collection discovered after
the fact. So the **workflow step fails the job if the log file is missing or
empty**. That check sits outside the agent, changes no behaviour, and converts
silent data loss into a red CI run.

**`null`, never `0`.** If `response.usage` is absent (it can be, on the fallback
path), writing `0` turns a paid cycle into a free one and **biases the median
downward** — i.e. silently in favour of whatever hypothesis is later tested.
Unknown is `null`. The aggregation excludes nulls and **must report how many it
excluded**; a large null fraction is a legitimate "data unusable, do not
proceed" outcome, not something to average around. Same rule for `usd` when
`completion_cost` cannot price a model.

**Dry-run must not change token consumption.** It disables only the Connector's
GitHub and Telegram calls. It does shorten `wall_clock_s`, which is why the mode
is recorded and why samples from different modes must never be pooled.

**Aggregation** deduplicates by `cycle_id` (an artifact can be downloaded
twice) and commits to `main` — so its output path must be added to
`bee-keeper.yaml`'s `paths-ignore`, or aggregation will wake the Keeper.
`HIVE_STATE.md` is already listed there for exactly this reason.

**Concurrency** needs no handling: each workflow run has its own workspace and
uploads its own artifact, so two runs cannot interleave into one file.

## Testing

`agents/` currently has **no tests at all** — no `test_*.py`, no pytest config,
and `make test` covers only `core/tests/` and `synapses/telegram-bot/tests/`.
This adds the first coverage those agents have had.

Six tests, chosen for what corrupts a baseline **silently**:

1. **`usage` absent → `null`, not `0`.** The single most important test here.
2. **Transformer raises → a record is still written with `outcome != "success"`.**
   Enforces "failed cycles count".
3. Writer appends rather than truncates.
4. Writer failure does not propagate to the caller.
5. `dry_run=True` → the Connector makes zero GitHub calls (mocked `httpx`).
6. Aggregation deduplicates by `cycle_id`.

Not tested: `litellm` itself; workflow YAML — verified by one live run.

## Rollout

1. Merge with `EVOLVER_DRY_RUN` unset — behaviour identical to today, records
   start accruing from `bee.Keeper` immediately.
2. Confirm on the first live Keeper run that the artifact exists and parses.
3. Only then raise `bee.Evolver` cadence with `dry_run` enabled for baseline
   collection.

## Risks

- **`bee.Keeper`'s DSPy path** reports usage differently from the litellm path
  (`transformer/__init__.py:99-106`). If a cycle goes through DSPy, the split
  may be unavailable — that is a `null` case, not a `0` case, and the aggregate
  null-rate will show it.
- **Artifact retention** is 90 days by default. Aggregation must run well inside
  that window; at the intended cadence it will.
- **This design was written against `origin/main` @ 9d4f733.** The local
  checkout was 65 commits behind when work started, and `bee.Keeper` had been
  restructured in between. Re-verify paths before implementing if time passes.
