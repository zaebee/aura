import time

import requests
import structlog
from agent_identity import AgentWallet
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()


class SimSettings(BaseSettings):
    gateway_url: str = "http://localhost:8000"


settings = SimSettings(_env_prefix="AURA_")

# Configure logging
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
)
logger = structlog.get_logger(__name__)

GATEWAY_URL = settings.gateway_url


def run_agent_scenario(scenario_name, item_id, bid, wallet=None):
    """
    Run a negotiation scenario with cryptographic signing.

    Args:
        scenario_name: Name of the scenario
        item_id: ID of the item to negotiate
        bid: Bid amount
        wallet: AgentWallet instance (optional)
    """
    # If no wallet provided, create a new one
    if wallet is None:
        wallet = AgentWallet()
        logger.info("generated_new_agent_wallet", did=wallet.did)

    logger.info("running_scenario", scenario=scenario_name)
    logger.info("scenario_details", target=item_id, bid=bid, agent=wallet.did)

    payload = {
        "item_id": item_id,
        "bid_amount": bid,
        "currency": "USD",
        "agent_did": wallet.did,  # Use the wallet's DID
    }

    try:
        start_ts = time.time()
        method = "/v1/negotiate"

        # Sign the request
        x_agent_id, x_timestamp, x_signature = wallet.sign_request(
            "POST", method, payload
        )

        # Add headers to the request
        headers = {
            "X-Agent-ID": x_agent_id,
            "X-Timestamp": x_timestamp,
            "X-Signature": x_signature,
            "Content-Type": "application/json",
        }

        response = requests.post(
            f"{GATEWAY_URL}{method}", json=payload, headers=headers, timeout=30
        )
        latency = (time.time() - start_ts) * 1000

        logger.info(
            "request_completed", gateway=GATEWAY_URL, latency_ms=f"{latency:.2f}"
        )

        if response.status_code != 200:
            logger.error(
                "api_error", status_code=response.status_code, text=response.text
            )
            return

        data = response.json()
        status = data.get("status")

        if status == "accepted":
            logger.info(
                "offer_accepted",
                final_price=data["data"]["final_price"],
                reservation=data["data"]["reservation_code"],
            )

        elif status == "countered":
            logger.info(
                "offer_countered",
                proposed_price=data["data"]["proposed_price"],
                message=data["data"]["message"],
            )

        elif status == "ui_required":
            logger.info(
                "ui_required",
                template=data["action_required"]["template"],
                context=data["action_required"]["context"],
            )

        elif status == "rejected":
            reason = data.get("data", {}).get("message", "No reason provided")
            code = data.get("data", {}).get("reason_code", "N/A")
            logger.warning("offer_rejected", reason=reason, code=code)

    except Exception as e:
        logger.error("system_error", error=str(e))


if __name__ == "__main__":
    # Create a wallet for all scenarios
    wallet = AgentWallet()
    logger.info("agent_initialized", did=wallet.did, public_key=wallet.public_key_hex)

    # 1. Жадный агент (слишком дешево)
    # floor_price у hotel_alpha = 800
    run_agent_scenario("Greedy Agent", "hotel_alpha", 1.0, wallet)

    # 2. Умный агент (в рамках допустимого)
    run_agent_scenario("Smart Agent", "hotel_alpha", 850.0, wallet)

    # 3. Богатый агент (Триггер UI подтверждения > 1000)
    run_agent_scenario("High-Roller Agent", "hotel_alpha", 1200.0, wallet)

    # 4. Ошибка (товар не существует)
    run_agent_scenario("Lost Agent", "hotel_omega_999", 100.0, wallet)
