"""
Utilities for safely building serializable protobuf.Struct objects.

betterproto v2.0b7 bug: Struct.from_dict() stores raw Python values in the
`fields` dict instead of proper protobuf.Value wrappers. This causes
`TypeError: string argument without an encoding` when bytes(struct) is called
during NATS/gRPC serialization.

This module:
1. Provides make_struct() — builds Struct with correct Value wrappers.
2. Patches Struct.to_dict() globally so it unwraps Values back to plain Python,
   preserving backward-compatible flat-dict reads across the entire codebase.
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
