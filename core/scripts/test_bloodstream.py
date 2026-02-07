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

import structlog

# Add core/src to path for imports
sys.path.insert(0, "core/src")

from datetime import UTC, datetime
from typing import Any

import nats
from google.protobuf.timestamp_pb2 import Timestamp

logger = structlog.get_logger(__name__)


async def test_basic_nats(nats_url: str) -> bool:
    """Test binary proto publish/subscribe with basic NATS (no JetStream)."""
    logger.info("testing_binary_bloodstream_basic", nats_url=nats_url)

    try:
        # Import proto
        from hive.proto.aura.dna.v1 import dna_pb2

        logger.info("proto_module_imported")
    except ImportError as e:
        logger.error("proto_import_failed", error=str(e), hint="Run: make generate")
        return False

    try:
        # Connect to NATS
        nc = await nats.connect(nats_url)
        logger.info("connected_to_nats")
    except Exception as e:
        logger.error("nats_connection_failed", error=str(e))
        return False

    # Create a test event
    event = dna_pb2.Event()
    event.event_id = f"test-{uuid.uuid4().hex[:8]}"
    event.topic = "aura.test.heartbeat"

    ts = Timestamp()
    ts.FromDatetime(datetime.now(UTC))
    event.timestamp.CopyFrom(ts)

    event.trace.trace_id = uuid.uuid4().hex
    event.trace.span_id = uuid.uuid4().hex[:16]
    event.trace.trace_flags = "01"

    event.heartbeat.service = "test_bloodstream"
    event.heartbeat.instance_id = "test-001"
    event.heartbeat.status = dna_pb2.VITALS_STATUS_OK

    # Serialize to binary
    binary_data = event.SerializeToString()
    logger.info(
        "event_serialized",
        size_bytes=len(binary_data),
        event_id=event.event_id,
        trace_id=event.trace.trace_id,
    )

    # Set up subscriber first
    msg_queue: asyncio.Queue = asyncio.Queue()

    async def message_handler(msg: Any) -> Any:
        await msg_queue.put(msg)

    sub = await nc.subscribe("aura.test.>", cb=message_handler)
    logger.info("subscribed_to_topic", subject="aura.test.>")

    # Publish
    await nc.publish(event.topic, binary_data)
    await nc.flush()
    logger.info("published_binary_event", topic=event.topic)

    # Wait for message
    try:
        msg = await asyncio.wait_for(msg_queue.get(), timeout=2.0)
    except TimeoutError:
        logger.error("no_message_received")
        await nc.close()
        return False

    # Verify
    received_event = dna_pb2.Event()
    received_event.ParseFromString(msg.data)
    logger.info(
        "received_deserialized_event",
        event_id=received_event.event_id,
        topic=received_event.topic,
        heartbeat_service=received_event.heartbeat.service,
        heartbeat_status=dna_pb2.VitalsStatus.Name(received_event.heartbeat.status),
    )

    if received_event.event_id == event.event_id:
        logger.info("round_trip_verified", event_id=received_event.event_id)
        result = True
    else:
        logger.error(
            "round_trip_failed",
            expected_id=event.event_id,
            actual_id=received_event.event_id,
        )
        result = False

    await sub.unsubscribe()
    await nc.close()
    if result:
        logger.info("binary_bloodstream_test_passed")
    return result


async def test_jetstream(nats_url: str) -> bool:
    """Test binary proto publish/subscribe with JetStream."""
    logger.info("testing_binary_bloodstream_jetstream", nats_url=nats_url)

    try:
        from hive.proto.aura.dna.v1 import dna_pb2

        logger.info("proto_module_imported")
    except ImportError as e:
        logger.error("proto_import_failed", error=str(e))
        return False

    try:
        nc = await nats.connect(nats_url)
        js = nc.jetstream()
        logger.info("connected_to_nats_jetstream")
    except Exception as e:
        logger.error("nats_connection_failed", error=str(e))
        return False

    # Create test stream
    try:
        await js.stream_info("AURA_TEST")
        logger.info("test_stream_exists")
    except nats.js.errors.NotFoundError:
        logger.info("creating_test_stream")
        await js.add_stream(
            name="AURA_TEST",
            subjects=["aura.test.>"],
            max_age=60 * 1_000_000_000,
        )
        logger.info("test_stream_created")
    except Exception as e:
        logger.warning("jetstream_not_available", error=str(e))
        logger.info("falling_back_to_basic_nats")
        await nc.close()
        return await test_basic_nats(nats_url)

    # Create and publish event
    event = dna_pb2.Event()
    event.event_id = f"test-{uuid.uuid4().hex[:8]}"
    event.topic = "aura.test.heartbeat"

    ts = Timestamp()
    ts.FromDatetime(datetime.now(UTC))
    event.timestamp.CopyFrom(ts)

    event.heartbeat.service = "test_bloodstream"
    event.heartbeat.instance_id = "test-001"
    event.heartbeat.status = dna_pb2.VITALS_STATUS_OK

    binary_data = event.SerializeToString()
    logger.info("event_serialized", size_bytes=len(binary_data))

    try:
        ack = await js.publish(event.topic, binary_data)
        logger.info("published_to_jetstream", stream=ack.stream, seq=ack.seq)
    except Exception as e:
        logger.error("publish_failed", error=str(e))
        await nc.close()
        return False

    # Subscribe and verify
    try:
        sub = await js.subscribe("aura.test.>", stream="AURA_TEST")
        msg = await sub.next_msg(timeout=5)

        received_event = dna_pb2.Event()
        received_event.ParseFromString(msg.data)

        logger.info("received_deserialized_event", event_id=received_event.event_id)

        if received_event.event_id == event.event_id:
            logger.info("round_trip_verified")

        await msg.ack()
        await sub.unsubscribe()

    except Exception as e:
        logger.error("subscribe_read_failed", error=str(e))
        await nc.close()
        return False

    await nc.close()
    logger.info("binary_bloodstream_jetstream_test_passed")
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
