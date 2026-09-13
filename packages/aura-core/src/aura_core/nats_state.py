"""
NATS connection-state tracking, shared by core and gateway.

Three live connections exist (gateway vision client, core pulse provider,
core signal gateway), and today none is observed: a drop is silent until
something else fails. This tracker is the single place that names the
state, so `/health` output and logs agree across services.

States mirror what nats.py reports: CONNECTED (usable), DISCONNECTED
(drop seen, reconnect pending), RECONNECTING is folded into DISCONNECTED
— nats.py has no separate reconnecting callback, only disconnect then
reconnect — and CLOSED (terminal: `close()` called or reconnects
exhausted). A tracker that never connected reports DISCONNECTED: it has
no usable connection, and "starting" is the health layer's word, not the
socket's.
"""

import enum

import structlog

logger = structlog.get_logger(__name__)


class NatsConnectionState(str, enum.Enum):
    """Observable NATS connection state."""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    CLOSED = "closed"


class NatsConnectionTracker:
    """Tracks one NATS connection via nats.py lifecycle callbacks.

    Bind the bound methods as `disconnected_cb`, `reconnected_cb` and
    `closed_cb` on `nats.connect`, then call `mark_connected()` after a
    successful (re)connect — nats.py has no connected callback, so the
    caller states it. Every transition logs once, so a drop leaves a
    trail even where no probe is watching.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.state = NatsConnectionState.DISCONNECTED

    @property
    def connected(self) -> bool:
        """Whether the connection is currently usable."""
        return self.state is NatsConnectionState.CONNECTED

    def as_str(self) -> str:
        """The state word surfaced in `/health` output."""
        return self.state.value

    def mark_connected(self) -> None:
        """Record a successful (re)connect. Called by the owner."""
        self._transition(NatsConnectionState.CONNECTED)

    async def on_disconnected(self) -> None:
        """nats.py `disconnected_cb`: the socket dropped."""
        self._transition(NatsConnectionState.DISCONNECTED)

    async def on_reconnected(self) -> None:
        """nats.py `reconnected_cb`: the library re-established the socket."""
        self._transition(NatsConnectionState.CONNECTED)

    async def on_closed(self) -> None:
        """nats.py `closed_cb`: terminal, no more reconnects coming."""
        self._transition(NatsConnectionState.CLOSED)

    def _transition(self, state: NatsConnectionState) -> None:
        if state is self.state:
            return
        previous = self.state
        self.state = state
        logger.info(
            "nats_connection_state",
            connection=self.name,
            previous=previous.value,
            current=state.value,
        )
