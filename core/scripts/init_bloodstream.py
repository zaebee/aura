#!/usr/bin/env python3
"""
init_bloodstream.py - Initialize NATS JetStream for the Hive's Binary Bloodstream.

This script creates the necessary JetStream streams and consumers for
persistent, binary proto message delivery across the Hive.

Streams:
- AURA_EVENTS: All hive events (aura.>) with 24h retention
- AURA_VITALS: System health metrics (aura.hive.vitals.>) with 1h retention
- AURA_AUDIT: Audit events (aura.hive.audit.>) with 7d retention

Usage:
    python core/scripts/init_bloodstream.py [--nats-url nats://localhost:4222]
"""

import argparse
import asyncio
import logging
import sys

import nats
from nats.js.api import (
    ConsumerConfig,
    DeliverPolicy,
    RetentionPolicy,
    StorageType,
    StreamConfig,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Stream definitions
STREAMS = [
    StreamConfig(
        name="AURA_EVENTS",
        description="All Hive events - negotiation, heartbeat, alerts",
        subjects=["aura.hive.events.>", "aura.hive.heartbeat"],
        retention=RetentionPolicy.LIMITS,
        max_age=24 * 60 * 60 * 1_000_000_000,  # 24 hours in nanoseconds
        storage=StorageType.FILE,
        num_replicas=1,
        discard="old",
        max_msgs=-1,
        max_bytes=1024 * 1024 * 100,  # 100MB
    ),
    StreamConfig(
        name="AURA_VITALS",
        description="System health metrics for proprioception",
        subjects=["aura.hive.vitals.>"],
        retention=RetentionPolicy.LIMITS,
        max_age=1 * 60 * 60 * 1_000_000_000,  # 1 hour in nanoseconds
        storage=StorageType.MEMORY,  # Fast access, ephemeral
        num_replicas=1,
        discard="old",
        max_msgs=10000,
        max_bytes=1024 * 1024 * 10,  # 10MB
    ),
    StreamConfig(
        name="AURA_AUDIT",
        description="Architectural audit events for the Keeper",
        subjects=["aura.hive.audit.>"],
        retention=RetentionPolicy.LIMITS,
        max_age=7 * 24 * 60 * 60 * 1_000_000_000,  # 7 days in nanoseconds
        storage=StorageType.FILE,
        num_replicas=1,
        discard="old",
        max_msgs=-1,
        max_bytes=1024 * 1024 * 50,  # 50MB
    ),
]

# Consumer definitions (durable consumers for reliable delivery)
CONSUMERS = [
    {
        "stream": "AURA_EVENTS",
        "config": ConsumerConfig(
            durable_name="core-processor",
            description="Core service event processor",
            deliver_policy=DeliverPolicy.NEW,
            ack_wait=30,  # 30 seconds to ack
            max_deliver=3,  # Retry 3 times
        ),
    },
    {
        "stream": "AURA_EVENTS",
        "config": ConsumerConfig(
            durable_name="keeper-watcher",
            description="BeeKeeper event watcher",
            deliver_policy=DeliverPolicy.NEW,
            filter_subject="aura.hive.events.negotiation_*",
            ack_wait=60,
            max_deliver=3,
        ),
    },
    {
        "stream": "AURA_VITALS",
        "config": ConsumerConfig(
            durable_name="monitor-aggregator",
            description="Monitor protein vitals aggregator",
            deliver_policy=DeliverPolicy.LAST,  # Only latest vitals
            ack_wait=10,
            max_deliver=1,
        ),
    },
    {
        "stream": "AURA_AUDIT",
        "config": ConsumerConfig(
            durable_name="chronicler",
            description="Audit event chronicler for HIVE_STATE.md",
            deliver_policy=DeliverPolicy.ALL,  # All audit history
            ack_wait=120,
            max_deliver=5,
        ),
    },
]


async def init_bloodstream(nats_url: str) -> bool:
    """Initialize JetStream streams and consumers."""
    logger.info(f"Connecting to NATS at {nats_url}")

    try:
        nc = await nats.connect(nats_url)
        js = nc.jetstream()
        logger.info("Connected to NATS, initializing JetStream...")

        # Create/update streams
        for stream_config in STREAMS:
            try:
                # Try to get existing stream
                await js.stream_info(stream_config.name)
                logger.info(f"Stream {stream_config.name} exists, updating...")
                await js.update_stream(config=stream_config)
            except nats.js.errors.NotFoundError:
                logger.info(f"Creating stream {stream_config.name}...")
                await js.add_stream(config=stream_config)

            logger.info(
                f"  ✓ Stream {stream_config.name}: subjects={stream_config.subjects}"
            )

        # Create/update consumers
        for consumer_def in CONSUMERS:
            stream_name = consumer_def["stream"]
            config = consumer_def["config"]
            try:
                await js.consumer_info(stream_name, config.durable_name)
                logger.info(f"Consumer {config.durable_name} exists on {stream_name}")
            except nats.js.errors.NotFoundError:
                logger.info(
                    f"Creating consumer {config.durable_name} on {stream_name}..."
                )
                await js.add_consumer(stream_name, config=config)

            logger.info(f"  ✓ Consumer {config.durable_name} on {stream_name}")

        await nc.close()
        logger.info("Bloodstream initialized successfully!")
        return True

    except nats.errors.NoServersError:
        logger.error(f"Cannot connect to NATS at {nats_url}")
        return False
    except Exception as e:
        logger.error(f"Failed to initialize bloodstream: {e}")
        return False


async def verify_bloodstream(nats_url: str) -> bool:
    """Verify JetStream is properly configured."""
    logger.info("Verifying bloodstream configuration...")

    try:
        nc = await nats.connect(nats_url)
        js = nc.jetstream()

        # Check all streams exist
        for stream_config in STREAMS:
            info = await js.stream_info(stream_config.name)
            logger.info(
                f"  ✓ Stream {stream_config.name}: {info.state.messages} messages"
            )

        # Check all consumers exist
        for consumer_def in CONSUMERS:
            stream_name = consumer_def["stream"]
            config = consumer_def["config"]
            info = await js.consumer_info(stream_name, config.durable_name)
            logger.info(
                f"  ✓ Consumer {config.durable_name}: pending={info.num_pending}"
            )

        await nc.close()
        logger.info("Bloodstream verification complete!")
        return True

    except Exception as e:
        logger.error(f"Bloodstream verification failed: {e}")
        return False


async def publish_test_event(nats_url: str) -> bool:
    """Publish a test binary event to verify the bloodstream."""
    logger.info("Publishing test event...")

    try:
        nc = await nats.connect(nats_url)
        js = nc.jetstream()

        # Import proto (generated)
        try:
            from hive.proto.aura.dna.v1 import dna_pb2

            # Create a test heartbeat event
            event = dna_pb2.Event()
            event.event_id = "test-001"
            event.topic = "aura.hive.heartbeat"
            event.heartbeat.service = "init_bloodstream"
            event.heartbeat.instance_id = "test"
            event.heartbeat.status = dna_pb2.VITALS_STATUS_OK

            # Serialize to binary
            binary_data = event.SerializeToString()
            logger.info(f"  Serialized event: {len(binary_data)} bytes")

            # Publish via JetStream
            ack = await js.publish("aura.hive.heartbeat", binary_data)
            logger.info(f"  ✓ Published to stream {ack.stream}, seq={ack.seq}")

        except ImportError:
            # Fallback to raw bytes if proto not generated
            logger.warning("Proto not generated, using raw test message")
            ack = await js.publish("aura.hive.heartbeat", b"test-heartbeat")
            logger.info(f"  ✓ Published raw test to stream {ack.stream}, seq={ack.seq}")

        await nc.close()
        return True

    except Exception as e:
        logger.error(f"Test publish failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Initialize NATS JetStream for Aura Hive"
    )
    parser.add_argument(
        "--nats-url",
        default="nats://localhost:4222",
        help="NATS server URL (default: nats://localhost:4222)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Only verify existing configuration",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Publish a test event after initialization",
    )
    args = parser.parse_args()

    if args.verify:
        success = asyncio.run(verify_bloodstream(args.nats_url))
    else:
        success = asyncio.run(init_bloodstream(args.nats_url))
        if success and args.test:
            asyncio.run(publish_test_event(args.nats_url))

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
