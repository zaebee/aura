"""
Loads and versions the guard's declared rules.

The digest is taken over the parsed structure rather than the file bytes. That
distinction is the whole reason this module exists: hashing the source would
mint a new rule-set version every time a comment was reflowed, and a version
that changes without the rules changing is noise a verifier learns to ignore —
which is exactly when it stops catching the change that mattered.

See docs/DECISION_RECEIPT.md §3.3 for how the version string reaches a receipt.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# The only substitute strategy. Kept as a set rather than a bare string so an
# unrecognised value reads as "a rule set claiming behaviour the engine has no
# implementation for" — the same failure as an undeclared gate.
SAFE_PRICE_STRATEGIES = frozenset({"safe_offer"})

_RULESET_PATH = Path(__file__).with_name("ruleset.yaml")

# Length of the digest carried in a version string. Sixteen hex characters is
# the receipt's canonical-prefix width (§3.7) — long enough that an accidental
# collision between two rule sets is not a practical concern, short enough to
# read in a log line.
_DIGEST_CHARS = 16


class RulesetError(Exception):
    """A rule set that cannot be trusted to describe what the engine does."""


@dataclass(frozen=True)
class Gate:
    """One declared rule, in the order it is evaluated."""

    id: str
    code: str
    consumes: tuple[str, ...]


@dataclass(frozen=True)
class Clause:
    """One conjunct of the post-condition, in the order it is evaluated."""

    id: str
    expr: str
    consumes: tuple[str, ...]


@dataclass(frozen=True)
class Postcondition:
    """
    What the rule set guarantees about an emitted decision.

    `expr` is prose for a human reader and for the digest, never evaluated: an
    expression evaluator in the guard would be a second implementation of the
    rules, and the point of declaring them once is to not have that.
    """

    id: str
    clauses: tuple[Clause, ...]


@dataclass(frozen=True)
class Ruleset:
    family: str
    version: str
    safe_price: str
    postcondition: Postcondition
    gates: tuple[Gate, ...]
    digest: str

    @property
    def version_string(self) -> str:
        """`guard/negotiation@2.0.0+9c1de4a70b3f5821` — family, semver, digest."""
        return f"{self.family}@{self.version}+{self.digest}"

    def validate_against(self, gates: set[str], clauses: set[str]) -> None:
        """
        Confirm the declaration and the implementation describe the same rules.

        Both directions are errors, for gates and for post-condition clauses
        alike. A declared rule with no predicate would never fire while the rule
        set advertises that it does; an implemented predicate that is not
        declared runs outside anything a receipt can account for. Either way the
        version string would name behaviour that is not the behaviour.
        """
        for kind, declared, implemented in (
            ("gates", {gate.id for gate in self.gates}, gates),
            (
                "postcondition clauses",
                {c.id for c in self.postcondition.clauses},
                clauses,
            ),
        ):
            undeclared = sorted(implemented - declared)
            if undeclared:
                raise RulesetError(
                    f"{kind} implemented but not declared in ruleset.yaml: {undeclared}"
                )

            unimplemented = sorted(declared - implemented)
            if unimplemented:
                raise RulesetError(
                    f"{kind} declared in ruleset.yaml but not implemented: {unimplemented}"
                )


def _canonical(mapping: dict[str, Any]) -> bytes:
    """
    Byte form the digest is taken over.

    Keys are sorted so that a reordered mapping hashes the same; list order is
    preserved because gate order decides which reason a decision is refused
    under, and is therefore part of the rules.
    """
    return json.dumps(mapping, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _clauses_from(raw_postcondition: Any) -> tuple[str, tuple[Clause, ...]]:
    """Parse the postcondition block, rejecting anything malformed."""
    if not isinstance(raw_postcondition, dict):
        raise RulesetError("ruleset key 'postcondition' must be a mapping")

    for key in ("id", "clauses"):
        if key not in raw_postcondition:
            raise RulesetError(f"postcondition is missing required key: {key!r}")

    raw_clauses = raw_postcondition["clauses"]
    if not isinstance(raw_clauses, list) or not raw_clauses:
        raise RulesetError("postcondition key 'clauses' must be a non-empty list")

    clauses: list[Clause] = []
    seen: set[str] = set()
    for position, raw in enumerate(raw_clauses):
        if not isinstance(raw, dict):
            raise RulesetError(f"clause at position {position} must be a mapping")
        for key in ("id", "expr", "consumes"):
            if key not in raw:
                raise RulesetError(f"clause at position {position} is missing {key!r}")
        if not isinstance(raw["consumes"], list):
            raise RulesetError(
                f"clause at position {position} declares 'consumes' as "
                f"{type(raw['consumes']).__name__}, expected a list"
            )
        clause_id = str(raw["id"])
        if clause_id in seen:
            raise RulesetError(f"duplicate clause id in postcondition: {clause_id!r}")
        seen.add(clause_id)
        clauses.append(
            Clause(
                id=clause_id,
                expr=str(raw["expr"]),
                consumes=tuple(str(key) for key in raw["consumes"]),
            )
        )

    return str(raw_postcondition["id"]), tuple(clauses)


def ruleset_from_mapping(mapping: dict[str, Any]) -> Ruleset:
    """Build a Ruleset from already-parsed YAML, rejecting anything malformed."""
    for key in ("family", "version", "safe_price", "postcondition", "gates"):
        if key not in mapping:
            raise RulesetError(f"ruleset is missing required key: {key!r}")

    strategy = str(mapping["safe_price"])
    if strategy not in SAFE_PRICE_STRATEGIES:
        raise RulesetError(
            f"ruleset declares unknown safe_price strategy {strategy!r}; "
            f"expected one of {sorted(SAFE_PRICE_STRATEGIES)}"
        )

    postcondition_id, clauses = _clauses_from(mapping["postcondition"])

    raw_gates = mapping["gates"]
    if not isinstance(raw_gates, list) or not raw_gates:
        raise RulesetError("ruleset key 'gates' must be a non-empty list")

    gates: list[Gate] = []
    seen: set[str] = set()
    for position, raw in enumerate(raw_gates):
        # Shape is checked before anything is read out of it, so a malformed
        # file reads as a bad rule set rather than a TypeError from somewhere
        # deeper — the caller has one exception type to handle either way.
        if not isinstance(raw, dict):
            raise RulesetError(f"gate at position {position} must be a mapping")

        for key in ("id", "code", "consumes"):
            if key not in raw:
                raise RulesetError(f"gate at position {position} is missing {key!r}")

        # Refused rather than ignored: this key is what a stale pre-collapse
        # ruleset.yaml still carries, and ignoring it would load a file that
        # describes two strategies into an engine that implements one.
        if "safe_price" in raw:
            raise RulesetError(
                f"gate at position {position} declares a per-gate 'safe_price'; "
                "the strategy is declared once for the set"
            )

        if not isinstance(raw["consumes"], list):
            raise RulesetError(
                f"gate at position {position} declares 'consumes' as "
                f"{type(raw['consumes']).__name__}, expected a list"
            )

        gate_id = str(raw["id"])
        if gate_id in seen:
            raise RulesetError(f"duplicate gate id in ruleset: {gate_id!r}")
        seen.add(gate_id)

        gates.append(
            Gate(
                id=gate_id,
                code=str(raw["code"]),
                consumes=tuple(str(key) for key in raw["consumes"]),
            )
        )

    # Rebuilt from the validated fields rather than hashed off the raw mapping.
    # Same argument as not hashing the file bytes, one level up: a `description:`
    # someone adds for readers is not a rule, and minting a new version for it
    # teaches everyone that a changed version means nothing.
    family = str(mapping["family"])
    version = str(mapping["version"])
    canonical = {
        "family": family,
        "version": version,
        "safe_price": strategy,
        "postcondition": {
            "id": postcondition_id,
            "clauses": [
                {"id": c.id, "expr": c.expr, "consumes": list(c.consumes)}
                for c in clauses
            ],
        },
        "gates": [
            {"id": gate.id, "code": gate.code, "consumes": list(gate.consumes)}
            for gate in gates
        ],
    }

    return Ruleset(
        family=family,
        version=version,
        safe_price=strategy,
        postcondition=Postcondition(id=postcondition_id, clauses=clauses),
        gates=tuple(gates),
        digest=hashlib.sha256(_canonical(canonical)).hexdigest()[:_DIGEST_CHARS],
    )


def load_ruleset(path: Path | None = None) -> Ruleset:
    """Read the shipped ruleset.yaml, or another file for tests."""
    source = path or _RULESET_PATH
    try:
        parsed = yaml.safe_load(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        # Fail closed and loudly. A guard with no rules is not a permissive
        # guard, it is a guard whose absence nobody would notice at runtime.
        raise RulesetError(f"ruleset not found at {source}") from exc
    except yaml.YAMLError as exc:
        # Every other way of failing to get rules raises RulesetError; a syntax
        # error should not be the one case that surfaces an exception type the
        # caller has no reason to be catching.
        raise RulesetError(f"ruleset at {source} is not valid YAML: {exc}") from exc

    if not isinstance(parsed, dict):
        raise RulesetError(f"ruleset at {source} did not parse to a mapping")

    return ruleset_from_mapping(parsed)
