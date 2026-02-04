import asyncio
import json
import os
import time

import nats
import structlog

# Configure logging
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
)
logger = structlog.get_logger(__name__)


async def main():
    # Use AURA_NATS_URL or fallback to nats:4222 for Hive internal networking
    nats_url = os.environ.get("AURA_NATS_URL", "nats://nats:4222")
    topic = "aura.hive.events.NegotiationAccepted"

    payload = {
        "success": True,
        "event_type": "NegotiationAccepted",
        "timestamp": time.time(),
        "session_token": "manual-pulse-token",  # nosec
    }

    # Redact credentials for safe logging
    safe_url = nats_url
    if "@" in nats_url:
        parts = nats_url.split("@")
        protocol_parts = parts[0].split("//")
        safe_url = f"{protocol_parts[0]}//****@{parts[1]}"

    logger.info("connecting_to_nats", url=safe_url)
    try:
        nc = await nats.connect(nats_url)
        logger.info("publishing_to_nats", topic=topic)
        await nc.publish(topic, json.dumps(payload).encode())
        await nc.flush()
        await nc.close()
        logger.info("pulse_triggered_successfully")
    except Exception as e:
        logger.error("pulse_trigger_failed", error=str(e))
        logger.info("nats_unavailability_expected_note")


if __name__ == "__main__":
    asyncio.run(main())
