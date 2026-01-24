import time

import requests

GATEWAY_URL = "http://localhost:8000/v1/negotiate"


def run_agent_scenario(scenario_name, item_id, bid, did="did:agent:007"):
    print(f"\n--- 🤖 SCENARIO: {scenario_name} ---")
    print(f"Target: {item_id} | Bid: ${bid}")

    payload = {
        "item_id": item_id,
        "bid_amount": bid,
        "currency": "USD",
        "agent_did": did,
    }

    try:
        start_ts = time.time()
        response = requests.post(GATEWAY_URL, json=payload)
        latency = (time.time() - start_ts) * 1000

        print(f"⏱️  Latency: {latency:.2f}ms")

        if response.status_code != 200:
            print(f"❌ Error {response.status_code}: {response.text}")
            return

        data = response.json()
        status = data.get("status")

        if status == "accepted":
            print("✅ OFFER ACCEPTED!")
            print(f"   Final Price: ${data['data']['final_price']}")
            print(f"   Reservation: {data['data']['reservation_code']}")

        elif status == "countered":
            print("⚠️  OFFER COUNTERED")
            print(f"   Server proposed: ${data['data']['proposed_price']}")
            print(f"   Message: '{data['data']['message']}'")

        elif status == "ui_required":
            print("👮 UI REQUIRED (Human Loop)")
            print(f"   Template: {data['action_required']['template']}")
            print(f"   Context: {data['action_required']['context']}")

        elif status == "rejected":
            print("⛔ REJECTED", data)
            # Добавляем вывод причины, если она есть
            if "data" in data and "message" in data["data"]:
                print(f"   Reason: {data['data']['message']}")
            elif "data" in data and "reason_code" in data["data"]:
                print(f"   Code: {data['data']['reason_code']}")

    except Exception as e:
        print(f"🔥 System Error: {e}")


if __name__ == "__main__":
    # 1. Жадный агент (слишком дешево)
    # floor_price у hotel_alpha = 800
    run_agent_scenario("Greedy Agent", "hotel_alpha", 1.0)

    # 2. Умный агент (в рамках допустимого)
    run_agent_scenario("Smart Agent", "hotel_alpha", 850.0)

    # 3. Богатый агент (Триггер UI подтверждения > 1000)
    run_agent_scenario("High-Roller Agent", "hotel_alpha", 1200.0)

    # 4. Ошибка (товар не существует)
    run_agent_scenario("Lost Agent", "hotel_omega_999", 100.0)
