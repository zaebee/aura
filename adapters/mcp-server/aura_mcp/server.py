"""
MCP Server for Aura Platform

This server acts as a proxy between AI models (via MCP) and the Aura Gateway,
providing search and negotiation capabilities to LLMs like Claude 3.5 Sonnet.
"""

import logging
import os

import httpx
from dotenv import load_dotenv

# Import AgentWallet from parent directory
from aura_mcp.wallet import AgentWallet

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("aura-mcp-server")

# Load environment variables
load_dotenv()

GATEWAY_URL = os.getenv("AURA_GATEWAY_URL", "http://localhost:8000")


class AuraMCPServer:
    """
    MCP Server that exposes Aura Platform capabilities to AI models.

    This server acts as a proxy client that:
    1. Generates a temporary Ed25519 wallet on startup
    2. Signs all requests to the Aura Gateway
    3. Exposes search and negotiation tools via MCP
    4. Handles errors gracefully for LLM consumption
    """

    def __init__(self):
        """Initialize the MCP server and HTTP client."""
        self.wallet = AgentWallet()  # Generate temporary wallet
        self.client = httpx.AsyncClient(timeout=30.0)

        logger.info("🔑 Generated temporary agent wallet")
        logger.info(f"DID: {self.wallet.did}")

    async def search_hotels(self, query: str, limit: int = 3) -> str:
        """
        Search hotels via Aura Gateway.

        Args:
            query: Search query string
            limit: Maximum number of results (default: 3)

        Returns:
            Formatted string with search results for LLM consumption
        """
        logger.info(f"🔍 Searching hotels: '{query}' (limit: {limit})")
        body = {"query": query, "limit": limit}

        try:
            # Sign the request
            agent_id, timestamp, signature = self.wallet.sign_request(
                "POST", "/v1/search", body
            )

            # Make request to Aura Gateway
            response = await self.client.post(
                f"{GATEWAY_URL}/v1/search",
                json=body,
                headers={
                    "X-Agent-ID": agent_id,
                    "X-Timestamp": timestamp,
                    "X-Signature": signature,
                    "Content-Type": "application/json",
                },
            )

            response.raise_for_status()
            data = response.json()

            # Format results for LLM
            results = []
            for item in data.get("results", []):
                results.append(
                    f"{item['name']} - ${item['price']:.2f} "
                    f"(Relevance: {item['score']:.2f}) - {item.get('details', 'No details')}"
                )

            if results:
                return "🏨 Search Results:\n" + "\n".join(results)
            else:
                return "No hotels found matching your criteria."

        except httpx.HTTPStatusError as e:
            logger.error(f"🔴 Gateway error: {e}")
            return f"❌ Search failed: Gateway returned error {e.response.status_code}"
        except httpx.RequestError as e:
            logger.error(f"🔴 Network error: {e}")
            return "❌ Search failed: Could not connect to Aura Gateway"
        except Exception as e:
            logger.error(f"🔴 Unexpected error in search_hotels: {e}", exc_info=True)
            return "❌ Search failed due to an unexpected internal error."

    async def negotiate_price(self, item_id: str, bid: float) -> str:
        """
        Negotiate price for an item via Aura Gateway.

        Args:
            item_id: ID of the item to negotiate
            bid: Bid amount in USD

        Returns:
            Formatted string with negotiation result for LLM consumption
        """
        logger.info(f"💰 Negotiating {item_id}: ${bid:.2f}")

        body = {
            "item_id": item_id,
            "bid_amount": bid,
            "currency": "USD",
            "agent_did": self.wallet.did,
        }

        try:
            # Sign the request
            agent_id, timestamp, signature = self.wallet.sign_request(
                "POST", "/v1/negotiate", body
            )

            # Make request to Aura Gateway
            response = await self.client.post(
                f"{GATEWAY_URL}/v1/negotiate",
                json=body,
                headers={
                    "X-Agent-ID": agent_id,
                    "X-Timestamp": timestamp,
                    "X-Signature": signature,
                    "Content-Type": "application/json",
                },
            )

            response.raise_for_status()
            data = response.json()

            # Handle polymorphic responses
            status = data.get("status")

            if status == "accepted":
                reservation_code = data.get("data", {}).get(
                    "reservation_code", "unknown"
                )
                return f"🎉 SUCCESS! Reservation: {reservation_code}"

            elif status == "countered":
                proposed_price = data.get("data", {}).get("proposed_price", bid)
                message = data.get("data", {}).get("message", "No reason provided")
                return f"🔄 COUNTER-OFFER: ${proposed_price:.2f}. Message: {message}"

            elif status == "ui_required":
                template = data.get("action_required", {}).get("template", "unknown")
                return f"🚨 HUMAN INTERVENTION REQUIRED. Template: {template}"

            elif status == "rejected":
                return "🚫 REJECTED"

            else:
                return f"❓ Unknown negotiation status: {status}"

        except httpx.HTTPStatusError as e:
            logger.error(f"🔴 Gateway error: {e}")
            return f"❌ Negotiation failed: Gateway returned error {e.response.status_code}"
        except httpx.RequestError as e:
            logger.error(f"🔴 Network error: {e}")
            return "❌ Negotiation failed: Could not connect to Aura Gateway"
        except Exception as e:
            logger.error(f"🔴 Unexpected error in negotiate_price: {e}", exc_info=True)
            return "❌ Negotiation failed due to an unexpected internal error."

    async def shutdown(self):
        """Close the underlying HTTP client."""
        await self.client.aclose()
        logger.info("🔌 Closed HTTP client.")
