from typing import Any
from aura_core import HiveContext, NegotiationOffer
from aura_core.gen.aura.dna.v1 import Event as ProtoEvent

class MCPTranslator:
    @staticmethod
    def to_negotiation_signal(item_id: str, bid: float, agent_did: str) -> dict:
        return {
            "item_id": item_id,
            "bid_amount": bid,
            "currency": "USD",
            "agent_did": agent_did,
        }

    @staticmethod
    def from_proto_event(payload: bytes) -> ProtoEvent:
        return ProtoEvent().parse(payload)

    @staticmethod
    def format_search_results(results: list) -> str:
        if not results:
            return "No hotels found matching your criteria."

        formatted = ["🏨 Search Results:"]
        for item in results:
            formatted.append(
                f"{item['name']} - ${item['price']:.2f} "
                f"(Relevance: {item['score']:.2f}) - {item.get('details', 'No details')}"
            )
        return "\n".join(formatted)

    @staticmethod
    def format_negotiation_response(status: str, data: dict) -> str:
        if status == "accepted":
            reservation_code = data.get("reservation_code", "unknown")
            return f"🎉 SUCCESS! Reservation: {reservation_code}"
        elif status == "countered":
            proposed_price = data.get("proposed_price")
            message = data.get("message", "No reason provided")
            return f"🔄 COUNTER-OFFER: ${proposed_price:.2f}. Message: {message}"
        elif status == "ui_required":
            template = data.get("template", "unknown")
            return f"🚨 HUMAN INTERVENTION REQUIRED. Template: {template}"
        elif status == "rejected":
            return "🚫 REJECTED"
        else:
            return f"❓ Unknown negotiation status: {status}"
