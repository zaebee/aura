import asyncio
import json
import time
import nats
from pathlib import Path
import sys
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

# Add core to path
sys.path.append(str(Path(__file__).parent.parent))

async def main():
    # Use nats:4222 as default for Hive internal networking
    nats_url = "nats://nats:4222"
    topic = "aura.hive.events.NegotiationAccepted"

    payload = {
        "success": True,
        "event_type": "NegotiationAccepted",
        "timestamp": time.time(),
        "session_token": "manual-pulse-token"
    }

    logger.info("connecting_to_nats", url=nats_url)
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
