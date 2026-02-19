"""
Quantum State Wrapper - Organic Fuzzy Logic for Proto Messages

Implements quantum uncertainty handling for protocol buffer messages.
Instead of raising AttributeError for missing fields or oneof mismatches,
it returns GhostObjects with probability 0, separating signal from noise.
"""

from typing import Any

import betterproto
import structlog

logger = structlog.get_logger(__name__)


class GhostObject:
    """Null Object with probability 0 - represents quantum uncertainty"""

    def __init__(self, field_name: str):
        self._field_name = field_name
        self._probability = 0.0  # Quantum probability of existence

    def __getattr__(self, name: str) -> "GhostObject":
        """Recursive ghost object - any access returns another ghost"""
        return GhostObject(f"{self._field_name}.{name}")

    def __bool__(self) -> bool:
        return False

    def __str__(self) -> str:
        return f"GhostObject({self._field_name})"

    def __repr__(self) -> str:
        return f"GhostObject({self._field_name}, p=0)"

    @property
    def probability(self) -> float:
        return self._probability

    def __eq__(self, other: Any) -> bool:
        """Ghost objects are only equal to themselves"""
        return isinstance(other, GhostObject) and self._field_name == other._field_name

    def __hash__(self) -> int:
        return hash(("GhostObject", self._field_name))


class QuantumState:
    """Quantum wrapper for proto messages - implements fuzzy field access"""

    def __init__(self, proto_message: Any):
        self._proto = proto_message
        self._ghost_objects: set[GhostObject] = set()

    def __getattr__(self, name: str) -> Any:
        """Intercept field access with quantum logic"""
        try:
            # First try normal attribute access
            return getattr(self._proto, name)
        except AttributeError:
            # Check if it's a oneof field mismatch
            if hasattr(self._proto, "which_one_of"):
                try:
                    # Try to find which oneof field is set
                    oneof_name, oneof_value = betterproto.which_one_of(
                        self._proto, "data"
                    )
                    if oneof_name and oneof_name != name:
                        # This is a oneof mismatch - return ghost object
                        ghost = GhostObject(f"{name}_via_{oneof_name}")
                        self._ghost_objects.add(ghost)
                        logger.debug(
                            "quantum_oneof_mismatch",
                            requested=name,
                            actual=oneof_name,
                            message_type=type(self._proto).__name__,
                        )
                        return ghost
                except Exception as e:
                    # If which_one_of fails, continue to regular ghost handling
                    logger.debug(
                        "quantum_oneof_check_failed",
                        error=str(e),
                        field=name,
                        message_type=type(self._proto).__name__,
                    )

            # Regular missing field - return ghost object
            ghost = GhostObject(name)
            self._ghost_objects.add(ghost)
            logger.debug(
                "quantum_field_missing",
                field=name,
                message_type=type(self._proto).__name__,
            )
            return ghost

    def get_ghost_objects(self) -> set[GhostObject]:
        """Get all ghost objects created during access"""
        return self._ghost_objects

    def has_quantum_uncertainty(self) -> bool:
        """Check if any ghost objects were created"""
        return len(self._ghost_objects) > 0

    def __getitem__(self, key: str) -> Any:
        """Support dict-like access"""
        return getattr(self, key)

    def __contains__(self, key: str) -> bool:
        """Check if field exists without creating ghost objects"""
        try:
            return hasattr(self._proto, key)
        except Exception:
            return False

    def get_underlying_proto(self) -> Any:
        """Access the underlying proto message directly"""
        return self._proto

    def __str__(self) -> str:
        return f"QuantumState({type(self._proto).__name__})"

    def __repr__(self) -> str:
        uncertainty_count = len(self._ghost_objects)
        return f"QuantumState({type(self._proto).__name__}, uncertainty={uncertainty_count})"


def wrap_quantum(proto_message: Any) -> QuantumState:
    """Convenience function to wrap a proto message in QuantumState"""
    return QuantumState(proto_message)
