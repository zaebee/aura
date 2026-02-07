import asyncio
import os

import structlog
from config import Settings as CoreSettings
from fastmcp import FastMCP  # type: ignore
from hive.cortex import HiveCell

from effector import MCPEffector
from receptor import MCPReceptor
from translator import MCPTranslator

# Setup logging
log_format = os.getenv("AURA_LOG_FORMAT", "json").lower()
renderer = (
    structlog.dev.ConsoleRenderer()
    if log_format == "console"
    else structlog.processors.JSONRenderer()
)

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        renderer,
    ]
)
logger = structlog.get_logger("mcp-synapse")

mcp = FastMCP(
    name="Aura",
    version="1.0.0",
)


async def main() -> None:
    logger.info("starting_mcp_synapse")

    # 1. Initialize Metabolism (The Cell)
    core_config = CoreSettings()
    cell = HiveCell(core_config)
    metabolism = await cell.build_organism()
    logger.info("metabolism_initialized")

    # 2. Initialize Synaptic Components
    translator = MCPTranslator()
    _ = MCPReceptor(mcp, metabolism, translator)
    effector = MCPEffector()  # No NATS for now in MCP

    # 3. Start background tasks
    asyncio.create_task(effector.run())

    # 4. Run MCP Server
    # FastMCP.run() is typically used for stdio-based MCP servers
    # It might take over the event loop.
    logger.info("mcp_server_running")
    mcp.run()


if __name__ == "__main__":
    # Note: FastMCP.run() might handle its own loop,
    # but we need metabolism to be initialized first.
    asyncio.run(main())
