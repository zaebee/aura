"""
Utilities for safely building serializable protobuf.Struct objects.

betterproto v2.0b7 bugs fixed by this module:

Bug 1 — Struct.from_dict() stores raw Python values instead of Value wrappers,
causing `TypeError: string argument without an encoding` when bytes(msg) is called
during NATS/gRPC serialization.

Bug 2 — Message.__getattribute__() raises AttributeError when accessing an
inactive oneof member (e.g. `context.hive` when `data=asset`). This also
breaks betterproto's own dump() → __eq__ path: the dataclass-generated __eq__
for a nested message (e.g. NegotiationObservation) accesses all oneof fields
during comparison, crashing bytes(observation) with
`AttributeError: 'result' is set to 'rejected', not 'accepted'`.

This module:
1. Provides make_struct() — builds Struct with correct Value wrappers.
2. Patches Struct.to_dict() globally so it unwraps Values back to plain Python.
3. Patches Message.__getattribute__() to return None (instead of raising) for
   inactive oneof members, making oneof access safe everywhere — including
   betterproto's internal dump/equality path.
"""

from typing import Any

import betterproto
from aura_core_gen.aura.core.google import protobuf

# ---------------------------------------------------------------------------
# Value <-> Python conversion helpers
# ---------------------------------------------------------------------------


def _to_value(v: Any) -> protobuf.Value:
    """Wrap a plain Python value in the appropriate protobuf.Value."""
    if v is None:
        return protobuf.Value(null_value=protobuf.NullValue(0))
    if isinstance(v, bool):
        return protobuf.Value(bool_value=v)
    if isinstance(v, int | float):
        return protobuf.Value(number_value=float(v))
    if isinstance(v, str):
        return protobuf.Value(string_value=v)
    if isinstance(v, dict):
        return protobuf.Value(struct_value=make_struct(v))
    if isinstance(v, list | tuple):
        return protobuf.Value(
            list_value=protobuf.ListValue(values=[_to_value(item) for item in v])
        )
    raise TypeError(
        f"Unsupported type for protobuf.Value: {type(v).__name__}. "
        "Convert to a supported type (dict, list, str, int, float, bool, None)."
    )


def _from_value(v: Any) -> Any:
    """Unwrap a protobuf.Value (or raw Python value) to plain Python."""
    if not isinstance(v, protobuf.Value):
        return v  # already a raw Python value (pre-fix compat)
    name, val = betterproto.which_one_of(v, "kind")
    if name == "null_value":
        return None
    if name == "bool_value":
        return val
    if name == "number_value":
        return val
    if name == "string_value":
        return val
    if name == "struct_value" and val is not None:
        return {k: _from_value(vv) for k, vv in val.fields.items()}
    if name == "list_value" and val is not None:
        return [_from_value(item) for item in val.values]
    return None


# ---------------------------------------------------------------------------
# Global patch: Struct.to_dict() → flat Python dict
# ---------------------------------------------------------------------------


def _struct_to_dict_fixed(
    self: protobuf.Struct,
    casing: betterproto.Casing = betterproto.Casing.CAMEL,
    include_default_values: bool = False,
) -> dict[str, Any]:
    """
    Fixed Struct.to_dict() that unwraps Value wrappers to plain Python values.

    betterproto's default implementation calls Value.to_dict() on each field,
    which returns the protobuf JSON representation (e.g. {'numberValue': 1.5})
    instead of the plain Python value (e.g. 1.5).
    """
    return {k: _from_value(v) for k, v in self.fields.items()}


# Apply the patch at import time so all Struct instances benefit.
protobuf.Struct.to_dict = _struct_to_dict_fixed  # type: ignore[method-assign]


# ---------------------------------------------------------------------------
# Global patch: Message.__getattribute__() → None for inactive oneof members
# ---------------------------------------------------------------------------

_orig_message_getattribute = betterproto.Message.__getattribute__


def _safe_message_getattribute(self: betterproto.Message, name: str) -> Any:
    """
    Return None instead of raising AttributeError for inactive oneof members.

    betterproto intentionally raises AttributeError when code accesses a oneof
    field that is not the currently-active member.  This is correct for user
    code but breaks betterproto's own serialization path: dump() compares a
    nested message with its default using `==`, which calls the dataclass-
    generated __eq__.  That __eq__ accesses every field in the tuple, including
    inactive oneof members, causing an unhandled AttributeError inside dump().

    Returning None is safe because:
    - dump() already has `if value is None: continue` immediately after getattr,
      so None-valued fields are silently skipped during serialization.
    - User-level guards (`if context.hive:`) evaluate None as falsy — correct.
    - which_one_of() is unaffected (it uses a different code path).
    """
    try:
        return _orig_message_getattribute(self, name)
    except AttributeError as exc:
        # Only intercept betterproto's own "wrong oneof member" error.
        # Its message format is: "'<group>' is set to '<active>', not '<name>'"
        if "' is set to '" in str(exc) and "', not '" in str(exc):
            return None
        raise


betterproto.Message.__getattribute__ = _safe_message_getattribute  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def make_struct(d: dict[str, Any]) -> protobuf.Struct:
    """
    Safely build a serializable protobuf.Struct from a plain Python dict.

    betterproto's Struct.from_dict() stores raw Python values which cannot be
    serialized to bytes. This helper wraps each value in the correct
    protobuf.Value type, fixing the TypeError during NATS/gRPC transport.

    The global Struct.to_dict() patch (above) ensures that reading metadata
    via .to_dict() still returns flat Python values as before.
    """
    return protobuf.Struct(fields={k: _to_value(v) for k, v in d.items()})
