
from aiogram.types import Message
from aura_core.gen.aura.negotiation.v1 import (
    AgentIdentity,
    NegotiateRequest,
    NegotiateResponse,
    SearchRequest,
    SearchResponse,
)


class TelegramTranslator:
    """
    Translates between Telegram-specific objects and internal Aura types.
    """

    @staticmethod
    def to_negotiate_request(message: Message, item_id: str, bid_amount: float) -> NegotiateRequest:
        return NegotiateRequest(
            item_id=item_id,
            bid_amount=bid_amount,
            currency_code="USD",
            agent=AgentIdentity(
                did=f"telegram:{message.from_user.id}" if message.from_user else "unknown",
                reputation_score=1.0
            )
        )

    @staticmethod
    def to_search_request(query: str, limit: int = 5) -> SearchRequest:
        return SearchRequest(
            query=query,
            limit=limit
        )

    @staticmethod
    def from_negotiate_response(response: NegotiateResponse) -> str:
        result_type = response.which_oneof("result")

        if result_type == "accepted":
            reveal_method = response.accepted.which_oneof("reveal_method")
            if reveal_method == "crypto_payment":
                p = response.accepted.crypto_payment
                return (
                    f"✅ *Bid Accepted!*\n\n"
                    f"To finalize the deal, please pay *{p.amount} {p.currency}* to:\n"
                    f"`{p.wallet_address}`\n\n"
                    f"Memo: `{p.memo}`\n"
                    f"Network: `{p.network}`"
                )
            else:
                return (
                    f"✅ *Bid Accepted!*\n\n"
                    f"Your reservation code is: `{response.accepted.reservation_code}`"
                )

        elif result_type == "countered":
            return (
                f"🔄 *Counter-offer Received*\n\n"
                f"The agent proposed: *${response.countered.proposed_price:.2f}*\n"
                f"Message: _{response.countered.human_message}_"
            )

        elif result_type == "rejected":
            return "❌ *Bid Rejected*"

        elif result_type == "ui_required":
            return "🚨 *Human Intervention Required*\nAn agent will review your request."

        return "❓ Unknown negotiation status."

    @staticmethod
    def from_search_response(response: SearchResponse) -> str:
        if not response.results:
            return "No results found."

        lines = ["🏨 *Search Results:*"]
        for r in response.results:
            lines.append(
                f"• *{r.name}* - ${r.base_price:.2f}\n"
                f"  ID: `{r.item_id}`\n"
                f"  _{r.description_snippet}_"
            )
        return "\n\n".join(lines)
