from typing import Any
from aura_core.gen.aura.negotiation.v1 import (
    NegotiateResponse,
    SearchResponse,
    NegotiateRequest,
    SearchRequest,
    AgentIdentity
)

class MCPTranslator:
    """
    Translates between MCP/JSON and internal Aura types.
    """

    @staticmethod
    def to_negotiate_request(item_id: str, bid: float, agent_did: str) -> NegotiateRequest:
        return NegotiateRequest(
            item_id=item_id,
            bid_amount=bid,
            currency_code="USD",
            agent=AgentIdentity(did=agent_did, reputation_score=1.0)
        )

    @staticmethod
    def to_search_request(query: str, limit: int = 3) -> SearchRequest:
        return SearchRequest(query=query, limit=limit)

    @staticmethod
    def from_negotiate_response(response: NegotiateResponse) -> str:
        result_type = response.which_oneof("result")

        if result_type == "accepted":
            reveal_method = response.accepted.which_oneof("reveal_method")
            if reveal_method == "crypto_payment":
                p = response.accepted.crypto_payment
                return f"🎉 SUCCESS! Bid accepted. Please pay {p.amount} {p.currency} to {p.wallet_address}. Deal ID: {p.deal_id}"
            else:
                return f"🎉 SUCCESS! Reservation: {response.accepted.reservation_code}"

        elif result_type == "countered":
            proposed_price = response.countered.proposed_price
            message = response.countered.human_message
            return f"🔄 COUNTER-OFFER: ${proposed_price:.2f}. Message: {message}"

        elif result_type == "ui_required":
            template = response.ui_required.template_id
            return f"🚨 HUMAN INTERVENTION REQUIRED. Template: {template}"

        elif result_type == "rejected":
            return "🚫 REJECTED"

        return f"❓ Unknown negotiation status: {result_type}"

    @staticmethod
    def from_search_response(response: SearchResponse) -> str:
        if not response.results:
            return "No hotels found matching your criteria."

        results = []
        for item in response.results:
            results.append(
                f"{item.name} - ${item.base_price:.2f} "
                f"(Relevance: {item.similarity_score:.2f}) - {item.description_snippet}"
            )
        return "🏨 Search Results:\n" + "\n".join(results)
