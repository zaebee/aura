#!/usr/bin/env python3
"""
test_bloodstream.py - Verify binary proto publish/subscribe via NATS.

This script tests the Binary Bloodstream by:
1. Publishing a binary proto event
2. Subscribing and deserializing the event
3. Verifying the round-trip

Supports both basic NATS and JetStream modes.

Usage:
    python core/scripts/test_bloodstream.py [--nats-url nats://localhost:4222] [--jetstream]
"""

import argparse
import asyncio
import sys
import uuid
from datetime import UTC, datetime
from typing import Any

import nats


async def test_basic_nats(nats_url: str) -> bool:
    """Test binary proto publish/subscribe with basic NATS (no JetStream)."""
    print(f"🩸 Testing Binary Bloodstream (Basic NATS) at {nats_url}")

    try:
        # Import proto
        from aura_core.gen.aura.core.v1 import Event, HeartbeatEvent, Status

        print("  ✓ Proto module imported")
    except ImportError as e:
        print(f"  ✗ Failed to import proto: {e}")
        print("    Run: make generate")
        return False

    try:
        # Connect to NATS
        nc = await nats.connect(nats_url)
        print("  ✓ Connected to NATS")
    except Exception as e:
        print(f"  ✗ Failed to connect: {e}")
        return False

    # Create a test event
    event = Event(
        identifier=f"test-{uuid.uuid4().hex[:8]}",
        topic="aura.test.heartbeat",
        timestamp=datetime.now(UTC),
        heartbeat=HeartbeatEvent(
            service="test_bloodstream",
            instance_id="test-001",
            status=Status.STATUS_OK
        )
    )

    # Serialize to binary
    binary_data = bytes(event)
    print(f"  ✓ Event serialized: {len(binary_data)} bytes")
    print(f"    identifier: {event.identifier}")

    # Set up subscriber first
    msg_queue: asyncio.Queue = asyncio.Queue()

    async def message_handler(msg: Any) -> Any:
        await msg_queue.put(msg)

    _sub = await nc.subscribe("aura.test.>", cb=message_handler)
    print("  ✓ Subscribed to aura.test.>")

    # Publish
    await nc.publish(event.topic, binary_data)
    await nc.flush()
    print(f"  ✓ Published binary event to {event.topic}")

    # Wait for message
    try:
        msg = await asyncio.wait_for(msg_queue.get(), timeout=2.0)
    except asyncio.TimeoutError:
        print("  ✗ No message received")
        await nc.close()
        return False

    # Verify
    received_event = Event().parse(msg.data)
    print("  ✓ Received and deserialized event")
    print(f"    identifier: {received_event.identifier}")
    print(f"    topic: {received_event.topic}")
    print(f"    heartbeat.service: {received_event.heartbeat.service}")
    print(
        f"    heartbeat.status: {received_event.heartbeat.status.name}"
    )

    if received_event.identifier == event.identifier:
        print("  ✓ Round-trip verified: identifier matches")
        await nc.close()
        return True
    else:
        print("  ✗ Round-trip failed: identifier mismatch")
        await nc.close()
        return False


async def test_jetstream(nats_url: str) -> bool:
    """Test binary proto publish/subscribe with JetStream."""
    print(f"🩸 Testing Binary Bloodstream (JetStream) at {nats_url}")

    try:
        from aura_core.gen.aura.core.v1 import Event, HeartbeatEvent, Status

        print("  ✓ Proto module imported")
    except ImportError as e:
        print(f"  ✗ Failed to import proto: {e}")
        return False

    try:
        nc = await nats.connect(nats_url)
        js = nc.jetstream()
        print("  ✓ Connected to NATS JetStream")
    except Exception as e:
        print(f"  ✗ Failed to connect: {e}")
        return False

    # Create test stream
    try:
        await js.stream_info("AURA_TEST")
        print("  ✓ Test stream exists")
    except nats.js.errors.NotFoundError:
        print("  Creating test stream...")
        await js.add_stream(
            name="AURA_TEST",
            subjects=["aura.test.>"],
            # max_age=60 * 1_000_000_000,
        )
        print("  ✓ Test stream created")
    except Exception as e:
        print(f"  ✗ JetStream not available: {e}")
        print("    Falling back to basic NATS test...")
        await nc.close()
        return await test_basic_nats(nats_url)

    # Create and publish event
    event = Event(
        identifier=f"test-{uuid.uuid4().hex[:8]}",
        topic="aura.test.heartbeat",
        timestamp=datetime.now(UTC),
        heartbeat=HeartbeatEvent(
            service="test_bloodstream",
            instance_id="test-001",
            status=Status.STATUS_OK
        )
    )

    binary_data = bytes(event)
    print(f"  ✓ Event serialized: {len(binary_data)} bytes")

    try:
        ack = await js.publish(event.topic, binary_data)
        print(f"  ✓ Published to stream={ack.stream}, seq={ack.seq}")
    except Exception as e:
        print(f"  ✗ Publish failed: {e}")
        await nc.close()
        return False

    # Subscribe and verify
    try:
        sub = await js.subscribe("aura.test.>", stream="AURA_TEST")
        msg = await sub.next_msg(timeout=5)

        received_event = Event().parse(msg.data)

        print("  ✓ Received and deserialized event")
        print(f"    identifier: {received_event.identifier}")

        if received_event.identifier == event.identifier:
            print("  ✓ Round-trip verified")

        await msg.ack()
        await sub.unsubscribe()

    except Exception as e:
        print(f"  ✗ Subscribe/read failed: {e}")
        await nc.close()
        return False

    await nc.close()
    print("\n🩸 Binary Bloodstream (JetStream) test PASSED!")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Test Binary Bloodstream")
    parser.add_argument(
        "--nats-url",
        default="nats://localhost:4222",
        help="NATS server URL",
    )
    parser.add_argument(
        "--jetstream",
        action="store_true",
        help="Use JetStream (requires JetStream-enabled NATS)",
    )
    args = parser.parse_args()

    if args.jetstream:
        success = asyncio.run(test_jetstream(args.nats_url))
    else:
        success = asyncio.run(test_basic_nats(args.nats_url))

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
