from typing import Any

import structlog

from translator import MCPTranslator

logger = structlog.get_logger(__name__)

class MCPReceptor:
    def __init__(self, metabolism: Any, wallet: Any):
        self.metabolism = metabolism
        self.wallet = wallet

    async def search_hotels(self, query: str, limit: int = 3) -> str:
        logger.info(f"🔍 Searching hotels: '{query}' (limit: {limit})")

        # In the new pattern, we should convert to a Signal
        # but since we are using a gRPC client that expects specific methods,
        # we'll use the client's search method.

        try:
            observation = await self.metabolism.execute_search(query, limit)
            if not observation.success:
                return f"❌ Search failed: {observation.error}"

            return MCPTranslator.format_search_results(observation.data)

        except Exception as e:
            logger.error("Search failed", error=e, exc_info=True)
            return f"❌ Search failed: {str(e)}"

    async def negotiate_price(self, item_id: str, bid: float) -> str:
        logger.info(f"💰 Negotiating {item_id}: ${bid:.2f}")

        try:
            # Call metabolism
            observation = await self.metabolism.execute_negotiate(item_id, bid, self.wallet.did)

            if not observation.success:
                return f"❌ Negotiation failed: {observation.error}"

            # Observation.data should contain the negotiation result (dict)
            res = observation.data

            # Determine status
            status = "unknown"
            if "accepted" in res and res["accepted"]:
                status = "accepted"
            elif "countered" in res and res["countered"]:
                status = "countered"
            elif "ui_required" in res and res["ui_required"]:
                status = "ui_required"
            elif "rejected" in res and res["rejected"]:
                status = "rejected"

            # Use translator to format for LLM
            return MCPTranslator.format_negotiation_response(status, res.get(status, {}) if status != "unknown" else {})

        except Exception as e:
            logger.error("Negotiation failed", error=e, exc_info=True)
            return f"❌ Negotiation failed: {str(e)}"
