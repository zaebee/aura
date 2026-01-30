import os
import time

import requests
from dotenv import load_dotenv

from agent_identity import AgentWallet

load_dotenv()

GATEWAY = os.getenv("AURA_GATEWAY_URL", "http://localhost:8000")


class AutonomousBuyer:
    def __init__(self, budget_limit: float):
        self.budget = budget_limit
        self.session_token = None
        self.wallet = AgentWallet()  # Generate wallet on initialization
        print(f"🔑 Agent initialized with DID: {self.wallet.did}")

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
        print(f"\n🔍 STEP 1: Searching for '{query}'...")

        payload = {"query": query, "limit": 1}
        headers = self._get_security_headers("POST", "/v1/search", payload)

        resp = requests.post(
            f"{GATEWAY}/search", json=payload, headers=headers, timeout=30
        )
        results = resp.json().get("results", [])

        if not results:
            print("   ❌ No results found.")
            return None

        best_match = results[0]
        print(f"   🎯 Found target: {best_match['name']}")
        print(f"      Base Price: ${best_match['price']}")
        print(f"      Relevance: {best_match['score']:.2f}")
        return best_match

    def negotiate_loop(self, item):
        print(f"\n💬 STEP 2: Starting Negotiation for {item['name']}...")

        # Стратегия: Начинаем с 20% скидки от бюджета (жадничаем)
        current_bid = min(item["price"], self.budget) * 0.8

        # Защита от бесконечного цикла
        max_rounds = 5

        for round_num in range(1, max_rounds + 1):
            print(f"   🔄 Round {round_num}: Bidding ${current_bid:.2f}...")

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
                f"{GATEWAY}/negotiate", json=payload, headers=headers, timeout=30
            )
            data = resp.json()
            status = data.get("status")

            # Анализ ответа сервера
            if status == "accepted":
                final_price = data["data"]["final_price"]
                print(f"\n🎉 SUCCESS! Deal closed at ${final_price}")
                print(f"   Reservation Code: {data['data']['reservation_code']}")
                return True

            elif status == "countered":
                server_offer = data["data"]["proposed_price"]
                server_msg = data["data"]["message"]
                print(f"   ⚠️ Server Countered: ${server_offer} ('{server_msg}')")

                # Принимаем решение (Reasoning)
                if server_offer <= self.budget:
                    print(
                        "   🤔 Counter-offer is within budget. Accepting their price next round."
                    )
                    current_bid = server_offer
                else:
                    # Пытаемся встретиться посередине
                    new_bid = (current_bid + server_offer) / 2
                    if new_bid > self.budget:
                        print(
                            f"   ❌ Too expensive. My budget is ${self.budget}. Walking away."
                        )
                        return False
                    print(f"   🤔 Analyzing... Let's try ${new_bid:.2f}")
                    current_bid = new_bid

            elif status == "ui_required":
                print("\n👮 UI INTERVENTION REQUIRED")
                print("   The amount is too high for autonomous decision.")
                print(f"   Render Template: {data['action_required']['template']}")
                return True  # Считаем успехом, так как передали человеку

            elif status == "rejected":
                print("   ⛔ Offer Rejected without counter-offer.")
                return False

            time.sleep(1)  # Имитация "раздумий"

        print("   ⌛ Negotiation timed out.")
        return False

    def run(self, user_intent: str):
        target = self.search(user_intent)
        if target:
            # Проверка, стоит ли вообще начинать
            if target["price"] > self.budget * 1.5:
                print("   💸 Item is way too expensive for my budget. Skipping.")
                return

            self.negotiate_loop(target)


if __name__ == "__main__":
    # Сценарий 1: Успешный торг (Бюджет позволяет)
    print("=== SCENARIO A: Backpacker looking for a deal ===")
    bot = AutonomousBuyer(budget_limit=60.0)
    bot.run("Cheap hostel in Bali for digital nomad")

    print("\n" + "=" * 50 + "\n")

    # Сценарий 2: Провал (Бюджет слишком мал)
    print("=== SCENARIO B: Dreamer with no money ===")
    broke_bot = AutonomousBuyer(budget_limit=200.0)
    broke_bot.run("Luxury hotel in Dubai")  # Стоит 1000, бюджет 200
