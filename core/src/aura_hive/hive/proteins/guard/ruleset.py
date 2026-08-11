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

# How the Membrane prices a substitute offer when a gate fires. Kept closed:
# an unrecognised strategy is a rule set claiming behaviour the engine has no
# implementation for, which is the same failure as an undeclared gate.
SAFE_PRICE_STRATEGIES = frozenset({"margin", "floor_markup"})

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
    safe_price: str


@dataclass(frozen=True)
class Ruleset:
    family: str
    version: str
    gates: tuple[Gate, ...]
    digest: str

    @property
    def version_string(self) -> str:
        """`guard/negotiation@1.0.0+9c1de4a70b3f5821` — family, semver, digest."""
        return f"{self.family}@{self.version}+{self.digest}"

    def validate_against(self, implemented: set[str]) -> None:
        """
        Confirm the declaration and the implementation describe the same rules.

        Both directions are errors. A declared gate with no predicate would
        never fire while the rule set advertises that it does; an implemented
        predicate that is not declared is a rule running outside anything a
        receipt can account for. Either way the version string would be a claim
        about behaviour that is not the behaviour.
        """
        declared = {gate.id for gate in self.gates}

        undeclared = sorted(implemented - declared)
        if undeclared:
            raise RulesetError(
                f"gates implemented but not declared in ruleset.yaml: {undeclared}"
            )

        unimplemented = sorted(declared - implemented)
        if unimplemented:
            raise RulesetError(
                f"gates declared in ruleset.yaml but not implemented: {unimplemented}"
            )


def _canonical(mapping: dict[str, Any]) -> bytes:
    """
    Byte form the digest is taken over.

    Keys are sorted so that a reordered mapping hashes the same; list order is
    preserved because gate order decides which reason a decision is refused
    under, and is therefore part of the rules.
    """
    return json.dumps(mapping, sort_keys=True, separators=(",", ":")).encode("utf-8")


def ruleset_from_mapping(mapping: dict[str, Any]) -> Ruleset:
    """Build a Ruleset from already-parsed YAML, rejecting anything malformed."""
    for key in ("family", "version", "gates"):
        if key not in mapping:
            raise RulesetError(f"ruleset is missing required key: {key!r}")

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

        for key in ("id", "code", "consumes", "safe_price"):
            if key not in raw:
                raise RulesetError(f"gate at position {position} is missing {key!r}")

        if not isinstance(raw["consumes"], list):
            raise RulesetError(
                f"gate at position {position} declares 'consumes' as "
                f"{type(raw['consumes']).__name__}, expected a list"
            )

        gate_id = str(raw["id"])
        if gate_id in seen:
            raise RulesetError(f"duplicate gate id in ruleset: {gate_id!r}")
        seen.add(gate_id)

        strategy = str(raw["safe_price"])
        if strategy not in SAFE_PRICE_STRATEGIES:
            raise RulesetError(
                f"gate {gate_id!r} declares unknown safe_price strategy "
                f"{strategy!r}; expected one of {sorted(SAFE_PRICE_STRATEGIES)}"
            )

        gates.append(
            Gate(
                id=gate_id,
                code=str(raw["code"]),
                consumes=tuple(str(key) for key in raw["consumes"]),
                safe_price=strategy,
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
        "gates": [
            {
                "id": gate.id,
                "code": gate.code,
                "consumes": list(gate.consumes),
                "safe_price": gate.safe_price,
            }
            for gate in gates
        ],
    }

    return Ruleset(
        family=family,
        version=version,
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
