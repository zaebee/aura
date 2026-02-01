import time

import requests
import structlog
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

from tools.simulators.agent_identity import AgentWallet

load_dotenv()


class BuyerSettings(BaseSettings):
    gateway_url: str = "http://localhost:8000"


settings = BuyerSettings(_env_prefix="AURA_")

# Configure logging
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
)
logger = structlog.get_logger(__name__)

GATEWAY = settings.gateway_url


class AutonomousBuyer:
    def __init__(self, budget_limit: float):
        self.budget = budget_limit
        self.session_token = None
        self.wallet = AgentWallet()  # Generate wallet on initialization
        logger.info("agent_initialized", did=self.wallet.did)

    def _get_security_headers(self, method: str, path: str, body: dict) -> dict:
        """Generate security headers for a request."""
        x_agent_id, x_timestamp, x_signature = self.wallet.sign_request(
            method, path, body
        )
        return {
            "X-Agent-ID": x_agent_id,
            "X-Timestamp": x_timestamp,
            "X-Signature": x_signature,
            "Content-Type": "application/json",
        }

    def search(self, query: str):
        logger.info("searching", query=query)

        payload = {"query": query, "limit": 1}
        headers = self._get_security_headers("POST", "/v1/search", payload)

        resp = requests.post(
            f"{GATEWAY}/v1/search", json=payload, headers=headers, timeout=30
        )
        results = resp.json().get("results", [])

        if not results:
            logger.warning("search_no_results")
            return None

        best_match = results[0]
        logger.info(
            "target_found",
            name=best_match["name"],
            price=best_match["price"],
            relevance=f"{best_match['score']:.2f}",
        )
        return best_match

    def negotiate_loop(self, item):
        logger.info("starting_negotiation", item=item["name"])

        # Стратегия: Начинаем с 20% скидки от бюджета (жадничаем)
        current_bid = min(item["price"], self.budget) * 0.8

        # Защита от бесконечного цикла
        max_rounds = 5

        for round_num in range(1, max_rounds + 1):
            logger.info("bid_round", round=round_num, amount=f"{current_bid:.2f}")

            payload = {
                "item_id": item["id"],
                "bid_amount": round(current_bid, 2),
                "agent_did": self.wallet.did,
                "currency": "USD",
            }

            # Generate security headers
            headers = self._get_security_headers("POST", "/v1/negotiate", payload)

            # Если есть сессия, могли бы передавать, но у нас stateless пока
            resp = requests.post(
                f"{GATEWAY}/v1/negotiate", json=payload, headers=headers, timeout=30
            )
            data = resp.json()
            status = data.get("status")

            # Анализ ответа сервера
            if status == "accepted":
                final_price = data["data"]["final_price"]
                logger.info(
                    "negotiation_success",
                    final_price=final_price,
                    reservation=data["data"]["reservation_code"],
                )
                return True

            elif status == "countered":
                server_offer = data["data"]["proposed_price"]
                server_msg = data["data"]["message"]
                logger.info(
                    "server_counter_offer", amount=server_offer, message=server_msg
                )

                # Принимаем решение (Reasoning)
                if server_offer <= self.budget:
                    logger.info(
                        "decision_accept_counter",
                        reasoning="Counter-offer is within budget.",
                    )
                    current_bid = server_offer
                else:
                    # Пытаемся встретиться посередине
                    new_bid = (current_bid + server_offer) / 2
                    if new_bid > self.budget:
                        logger.warning(
                            "decision_walk_away",
                            reasoning=f"Too expensive. Budget is ${self.budget}.",
                        )
                        return False
                    logger.info(
                        "decision_new_counter",
                        amount=f"{new_bid:.2f}",
                        reasoning="Splitting the difference.",
                    )
                    current_bid = new_bid

            elif status == "ui_required":
                logger.info(
                    "ui_intervention_required",
                    template=data["action_required"]["template"],
                )
                return True  # Считаем успехом, так как передали человеку

            elif status == "rejected":
                logger.warning("negotiation_rejected")
                return False

            time.sleep(1)  # Имитация "раздумий"

        logger.warning("negotiation_timeout")
        return False

    def run(self, user_intent: str):
        target = self.search(user_intent)
        if target:
            # Проверка, стоит ли вообще начинать
            if target["price"] > self.budget * 1.5:
                logger.info("skipping_item", reasoning="Way too expensive for budget.")
                return

            self.negotiate_loop(target)


if __name__ == "__main__":
    # Сценарий 1: Успешный торг (Бюджет позволяет)
    logger.info("scenario_start", name="Backpacker looking for a deal")
    bot = AutonomousBuyer(budget_limit=60.0)
    bot.run("Cheap hostel in Bali for digital nomad")

    # Сценарий 2: Провал (Бюджет слишком мал)
    logger.info("scenario_start", name="Dreamer with no money")
    broke_bot = AutonomousBuyer(budget_limit=200.0)
    broke_bot.run("Luxury hotel in Dubai")  # Стоит 1000, бюджет 200
