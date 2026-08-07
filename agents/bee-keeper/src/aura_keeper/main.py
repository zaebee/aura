import asyncio
import sys

import nats
import nats.errors
import structlog

from aura_keeper.config import KeeperSettings
from aura_keeper.hive.metabolism import BeeMetabolism

# Configure logging
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
)
logger = structlog.get_logger(__name__)


async def audit_once() -> None:
    """
    Run a single metabolic cycle and exit.

    CI needs an audit, not a daemon: `main()` below subscribes to NATS and
    blocks in `async for msg in sub.messages` forever, so a workflow calling it
    would hang until the job timeout. One cycle is A -> T -> C -> G and touches
    no message bus.

    The event name comes from settings rather than the environment directly —
    bee.Keeper flags raw environment reads as a Pattern Heresy, and it should
    not break its own rule. `execute()` skips the LLM audit for `schedule`,
    which keeps heartbeat runs from spending honey.
    """
    settings = KeeperSettings()
    event_name = settings.github_event_name or "manual"
    logger.info("bee_keeper_audit_once", trigger_event=event_name)

    metabolism = BeeMetabolism(settings)
    try:
        await metabolism.execute(event_name=event_name)
    except Exception as e:
        logger.error("bee_keeper_audit_failed", error=str(e), exc_info=True)
        sys.exit(1)
    finally:
        if metabolism.connector:
            await metabolism.connector.close()


async def main() -> None:
    logger.info("bee_keeper_agent_starting")

    # 0. Load Settings
    settings = KeeperSettings()

    metabolism = None
    nc = None
    sub = None
    try:
        # 1. Initialize Metabolism
        metabolism = BeeMetabolism(settings)

        # 1.5 Sanity Check: Test Brain Connectivity
        if not await metabolism.transformer.test_brain_connectivity():
            logger.error("Brain connectivity test failed. Check AURA_LLM__API_KEY.")
            # We don't exit here to allow for intermittent connectivity
            # sys.exit(1)

        # 2. Connect to NATS Bloodstream
        nc = await nats.connect(settings.nats_url)
        logger.info("connected_to_nats", url=settings.nats_url)

        # 3. Subscribe to Error Events
        error_subject = "aura.hive.events.error"
        sub = await nc.subscribe(error_subject)
        logger.info("subscribed_to_errors", subject=error_subject)

        # 4. Metabolic Loop (Continuous)
        async for msg in sub.messages:
            try:
                logger.info("error_signal_detected", subject=msg.subject)
                # Execute one complete metabolic cycle for each error
                await metabolism.execute(event_name="error_diagnosis")
            except Exception as e:
                logger.error("cycle_failure", error=str(e))

    except Exception as e:
        logger.error("bee_keeper_agent_critical_error", error=str(e), exc_info=True)
        sys.exit(1)
    finally:
        # Cleanup
        if sub:
            try:
                await sub.unsubscribe()
                logger.info("nats_unsubscribed")
            except Exception as e:  # nosec B110
                logger.warning("nats_unsubscribe_failed", error=str(e))
        if nc:
            try:
                await nc.close()
                logger.info("nats_connection_closed")
            except Exception as e:  # nosec B110
                logger.warning("nats_close_failed", error=str(e))
        if metabolism and metabolism.connector:
            await metabolism.connector.close()


if __name__ == "__main__":
    if "--once" in sys.argv:
        asyncio.run(audit_once())
    else:
        asyncio.run(main())
