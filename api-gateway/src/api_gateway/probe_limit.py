"""Probe rate limiting: stretch floor binary-search past price validity.

Each bid on one item is a probe: ~17 accept/reject answers recover a floor
at cent precision, and the safety guarantee makes acceptance informative
by construction — the channel cannot be closed. The only mitigation that
changes the picture is time: a sliding window per (counterparty, item)
that stretches 17 probes over longer than a price stays valid, so the
recovered number is stale by the time the prober holds it.

Explicitly NOT this (see DECISION_RECEIPT.md §3.4): stochastic refusal
near the floor (breaks the accept/reject proof at the cost of honest
revenue), or deterministic per-(item, counterparty) jitter (closes the
averaging channel, which is not the problem).

Storage is Redis (sorted set per pair), so the budget survives restarts
and does not split across replicas.
"""

import hashlib
import time
import uuid
from collections.abc import Collection
from typing import Any


class ProbeLimiter:
    """Sliding-window probe budget per (counterparty, item)."""

    def __init__(
        self,
        redis_client: Any,
        limit: int = 5,
        window_s: int = 3600,
        whitelist: Collection[str] = frozenset(),
        key_prefix: str = "probe_limit",
    ) -> None:
        self.redis = redis_client
        self.limit = limit
        self.window_s = window_s
        self.whitelist = frozenset(whitelist)
        self.key_prefix = key_prefix

    def _key(self, counterparty: str, item_id: str) -> str:
        # Hashed rather than interpolated: DIDs and item ids may contain
        # the delimiter, so `a:b` + `c` and `a` + `b:c` would otherwise
        # collide on one budget.
        digest = hashlib.sha256(f"{counterparty}\x00{item_id}".encode()).hexdigest()[
            :32
        ]
        return f"{self.key_prefix}:{digest}"

    async def check(
        self,
        counterparty: str,
        item_id: str,
        now: float | None = None,
    ) -> tuple[bool, float]:
        """Spend one probe from the pair's budget.

        Returns (allowed, retry_after_seconds). `retry_after` is 0 when
        allowed, otherwise the seconds until the oldest probe in the
        window expires. Whitelisted counterparties always pass with 0.
        `now` is injectable for tests; production passes nothing.
        """
        if counterparty in self.whitelist:
            return True, 0.0

        timestamp = now if now is not None else time.time()
        key = self._key(counterparty, item_id)
        cutoff = timestamp - self.window_s

        # Member is unique per probe: two probes in the same instant must
        # count twice, not overwrite each other in the set.
        member = f"{timestamp}:{uuid.uuid4().hex}"
        pipe = self.redis.pipeline()
        pipe.zremrangebyscore(key, 0, cutoff)
        pipe.zadd(key, {member: timestamp})
        pipe.zcard(key)
        pipe.expire(key, int(self.window_s) + 60)
        _, _, count, _ = await pipe.execute()

        if count <= self.limit:
            return True, 0.0

        # Blocked probes must not consume budget: without this removal a
        # client that keeps retrying would extend its own lockout forever
        # (every blocked probe counts) and bloat the set. The removal and
        # oldest-read ride one pipeline — no extra round trips.
        pipe = self.redis.pipeline()
        pipe.zrem(key, member)
        pipe.zrange(key, 0, 0, withscores=True)
        _, oldest = await pipe.execute()

        retry_after = (
            self.window_s - (timestamp - oldest[0][1]) if oldest else self.window_s
        )
        return False, max(retry_after, 0.0)
