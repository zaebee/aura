import asyncio
import sys
from pathlib import Path

# Ensure src/ is on the path so sub-modules can resolve shared imports
# (mirrors bee-keeper's runtime layout under uv run)
_src = Path(__file__).parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

import structlog  # noqa: E402
from config import EvolverSettings  # noqa: E402
from hive.metabolism import EvolverMetabolism  # noqa: E402

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
)
logger = structlog.get_logger(__name__)


async def main() -> None:
    logger.info("bee_evolver_starting")

    settings = EvolverSettings()

    metabolism = EvolverMetabolism(settings)
    try:
        observation = await metabolism.execute()
    except Exception as e:
        logger.error("bee_evolver_critical_error", error=str(e), exc_info=True)
        sys.exit(1)

    if not observation.success and not observation.plan:
        logger.error("bee_evolver_cycle_failed", errors=observation.errors)
        sys.exit(1)

    logger.info(
        "bee_evolver_done",
        pr_url=observation.pr_url,
        issues=len(observation.issue_urls),
        telegram_sent=observation.telegram_sent,
    )


if __name__ == "__main__":
    asyncio.run(main())
