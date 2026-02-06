"""
DNA - The Law of the Hive.

This module contains ONLY Protocols and TypeVars.
These define the contracts that all Hive components must follow.

For runtime implementations, see metabolism.py.
For geography (folders, chambers), see hive-manifest.yaml at the repo root.
"""

from typing import Any, Protocol, TypeVar, runtime_checkable

from .types import SystemVitals

# TypeVars for the metabolic steps
S_inv = TypeVar("S_inv", contravariant=True)  # Input Signal
C_cov = TypeVar("C_cov", covariant=True)  # Output Context
C_inv = TypeVar("C_inv", contravariant=True)  # Input Context
I_inv = TypeVar("I_inv", contravariant=True)  # Input Intent
O_cov = TypeVar("O_cov", covariant=True)  # Output Observation
E_cov = TypeVar("E_cov", covariant=True)  # Output Event
P_inv = TypeVar("P_inv", contravariant=True)  # Input Params
R_cov = TypeVar("R_cov", covariant=True)  # Output Result


@runtime_checkable
class Aggregator[S_inv, C_cov](Protocol):
    """Standard sensory organ. Turns Signal into Context."""

    async def perceive(self, signal: S_inv, **kwargs: Any) -> C_cov: ...

    async def get_vitals(self) -> SystemVitals: ...


@runtime_checkable
class Transformer[C_inv, I_inv](Protocol):
    """Standard reasoning organ. Turns Context into Intent."""

    async def think(self, context: C_inv, **kwargs: Any) -> I_inv: ...


@runtime_checkable
class SkillProtocol[T_settings, T_provider, P_inv, R_cov](Protocol):
    """Protocol for specialized Proteins used by the Connector."""

    def get_name(self) -> str: ...

    def get_capabilities(self) -> list[str]: ...

    def bind(self, settings: T_settings, provider: T_provider) -> None: ...

    async def initialize(self) -> bool: ...

    async def execute(self, intent: str, params: P_inv) -> R_cov: ...


@runtime_checkable
class Connector[I_inv, O_cov, C_inv](Protocol):
    """Standard motor organ. Turns Intent into Observation."""

    async def act(self, action: I_inv, context: C_inv) -> O_cov: ...


@runtime_checkable
class Generator[O_cov, E_cov](Protocol):
    """Standard pulse organ. Turns Observation into Events."""

    async def pulse(self, observation: O_cov) -> list[E_cov]: ...


@runtime_checkable
class Membrane[S_inv, I_inv, C_inv](Protocol):
    """Standard safety organ. Inspects Inbound and Outbound."""

    async def inspect_inbound(self, signal: S_inv) -> S_inv: ...

    async def inspect_outbound(self, decision: I_inv, context: C_inv) -> I_inv: ...
