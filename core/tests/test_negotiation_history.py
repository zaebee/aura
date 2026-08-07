"""
Negotiation history: the free phase gets to see its previous passes.

Until this existed `think()` passed `history: []` unconditionally, so every
round reasoned from scratch. The DSPy signature declared the field all along;
nothing ever filled it.

Grouping is by (agent_did, item_id) because the wire protocol carries no
conversation identifier. That is a deliberate approximation, and these tests
pin down both what it buys and what it costs.
"""

import json
from typing import Any

import pytest
from aura_hive.hive.proteins.persistence.engine import (
    RedisCache,
    negotiation_history_key,
)


class FakeRedis:
    """Enough of redis.asyncio for lists: rpush, ltrim, expire, lrange."""

    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}
        self.ttls: dict[str, int] = {}
        self._queued: list[tuple[str, tuple[Any, ...]]] = []

    def pipeline(self) -> "FakeRedis":
        return self

    def rpush(self, key: str, value: str) -> None:
        self._queued.append(("rpush", (key, value)))

    def ltrim(self, key: str, start: int, end: int) -> None:
        self._queued.append(("ltrim", (key, start, end)))

    def expire(self, key: str, ttl: int) -> None:
        self._queued.append(("expire", (key, ttl)))

    async def execute(self) -> None:
        for op, args in self._queued:
            if op == "rpush":
                self.lists.setdefault(args[0], []).append(args[1])
            elif op == "ltrim":
                key, start, end = args
                items = self.lists.get(key, [])
                self.lists[key] = items[start:] if end == -1 else items[start : end + 1]
            elif op == "expire":
                self.ttls[args[0]] = args[1]
        self._queued = []

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        items = self.lists.get(key, [])
        return items[start:] if end == -1 else items[start : end + 1]


@pytest.fixture
def cache() -> RedisCache:
    return RedisCache(FakeRedis())  # type: ignore[arg-type]


def turn(price: float, override: bool = False) -> dict[str, Any]:
    return {
        "action": "negotiation_counter",
        "price": price,
        "membrane_override": override,
    }


class TestKey:
    def test_the_same_pair_gives_the_same_key(self) -> None:
        a = negotiation_history_key("did:key:abc", "hotel_alpha")
        b = negotiation_history_key("did:key:abc", "hotel_alpha")
        assert a == b

    def test_different_pairs_differ(self) -> None:
        assert negotiation_history_key("did:a", "x") != negotiation_history_key(
            "did:b", "x"
        )
        assert negotiation_history_key("did:a", "x") != negotiation_history_key(
            "did:a", "y"
        )

    def test_a_delimiter_in_a_value_cannot_collide(self) -> None:
        """`a:b` + `c` and `a` + `b:c` interpolate to the same string."""
        assert negotiation_history_key("a:b", "c") != negotiation_history_key(
            "a", "b:c"
        )

    def test_the_key_is_bounded_regardless_of_input_length(self) -> None:
        long_did = "did:key:" + "f" * 4000
        assert len(negotiation_history_key(long_did, "x" * 4000)) < 64


class TestRoundTrip:
    @pytest.mark.asyncio
    async def test_turns_come_back_oldest_first(self, cache: RedisCache) -> None:
        for price in (900.0, 950.0, 975.0):
            await cache.append_negotiation_turn("did:a", "item", turn(price))

        history = await cache.get_negotiation_history("did:a", "item")
        assert [t["price"] for t in history] == [900.0, 950.0, 975.0]

    @pytest.mark.asyncio
    async def test_an_untouched_conversation_is_empty_not_an_error(
        self, cache: RedisCache
    ) -> None:
        assert await cache.get_negotiation_history("did:nobody", "item") == []

    @pytest.mark.asyncio
    async def test_only_the_last_cap_turns_are_kept(self, cache: RedisCache) -> None:
        """The history ends up inside a prompt; it has to be bounded."""
        for i in range(30):
            await cache.append_negotiation_turn("did:a", "item", turn(float(i)), cap=5)

        history = await cache.get_negotiation_history("did:a", "item")
        assert [t["price"] for t in history] == [25.0, 26.0, 27.0, 28.0, 29.0]

    @pytest.mark.asyncio
    async def test_a_ttl_is_set_on_every_append(self, cache: RedisCache) -> None:
        await cache.append_negotiation_turn("did:a", "item", turn(900.0), ttl=1800)
        key = negotiation_history_key("did:a", "item")
        assert cache.redis.ttls[key] == 1800  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_a_corrupt_entry_is_skipped_not_fatal(
        self, cache: RedisCache
    ) -> None:
        await cache.append_negotiation_turn("did:a", "item", turn(900.0))
        key = negotiation_history_key("did:a", "item")
        cache.redis.lists[key].append("{not json")  # type: ignore[attr-defined]
        cache.redis.lists[key].append(json.dumps(turn(950.0)))  # type: ignore[attr-defined]

        history = await cache.get_negotiation_history("did:a", "item")
        assert [t["price"] for t in history] == [900.0, 950.0]

    @pytest.mark.asyncio
    async def test_the_override_flag_survives_the_round_trip(
        self, cache: RedisCache
    ) -> None:
        """This is the field the eventual measurement reads."""
        await cache.append_negotiation_turn("did:a", "item", turn(500.0, override=True))
        history = await cache.get_negotiation_history("did:a", "item")
        assert history[0]["membrane_override"] is True


class TestGroupingApproximation:
    @pytest.mark.asyncio
    async def test_conversations_are_separated_by_item(self, cache: RedisCache) -> None:
        await cache.append_negotiation_turn("did:a", "hotel", turn(900.0))
        await cache.append_negotiation_turn("did:a", "villa", turn(100.0))

        assert len(await cache.get_negotiation_history("did:a", "hotel")) == 1
        assert len(await cache.get_negotiation_history("did:a", "villa")) == 1

    @pytest.mark.asyncio
    async def test_two_deals_for_the_same_item_merge(self, cache: RedisCache) -> None:
        """
        The known cost of this design, asserted rather than left implicit.

        With no conversation id on the wire, a second independent negotiation by
        the same agent over the same item continues the first one's transcript.
        The TTL bounds how long. Fixing it means adding conversation_id to the
        proto.
        """
        await cache.append_negotiation_turn("did:a", "hotel", turn(900.0))
        await cache.append_negotiation_turn("did:a", "hotel", turn(200.0))

        history = await cache.get_negotiation_history("did:a", "hotel")
        assert len(history) == 2
