"""
Mock MCP implementation for development and testing.

This allows the Aura MCP Server to run even without the official MCP SDK installed.
"""

import asyncio
import json
import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("aura-mcp-server")


class Tool:
    """Mock MCP Tool class."""

    def __init__(
        self, name: str, description: str, parameters: Dict[str, Any], func: Callable
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.func = func


class FastMCP:
    """Mock FastMCP server implementation."""

    def __init__(self, name: str, description: str = "", version: str = "1.0.0"):
        self.name = name
        self.description = description
        self.version = version
        self.tools: Dict[str, Tool] = {}
        self.running = False

    def register_tool(self, tool: Tool):
        """Register a tool with the MCP server."""
        self.tools[tool.name] = tool
        logger.info(f"🛠️  Registered tool: {tool.name}")

    async def start(self, host: str = "0.0.0.0", port: int = 8080):
        """Start the MCP server."""
        if self.running:
            logger.warning("⚠️  MCP server is already running")
            return

        self.running = True
        logger.info(f"🌐 MCP server '{self.name}' started on {host}:{port}")
        logger.info(f"📋 Description: {self.description}")
        logger.info(f"📦 Version: {self.version}")
        logger.info(f"🛠️  Available tools: {list(self.tools.keys())}")

        # In a real implementation, this would start a web server
        # For mock purposes, we'll just keep running until cancelled
        try:
            while self.running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        except KeyboardInterrupt:
            pass

    async def shutdown(self):
        """Shutdown the MCP server."""
        if not self.running:
            return

        self.running = False
        logger.info("🛑 MCP server shutdown complete")

    def get_tools_info(self) -> Dict[str, Any]:
        """Get information about registered tools."""
        tools_info = {}
        for name, tool in self.tools.items():
            tools_info[name] = {
                "description": tool.description,
                "parameters": tool.parameters,
            }
        return tools_info


def create_mock_mcp_server():
    """Create a mock MCP server for testing."""
    return FastMCP(
        name="Aura-Mock",
        description="Mock Aura Platform MCP Server for testing",
        version="0.1.0",
    )
