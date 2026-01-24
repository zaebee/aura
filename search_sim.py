import requests

URL = "http://localhost:8000/v1/search"


def test_query(query):
    print(f"\n🧠 Query: '{query}'")
    try:
        resp = requests.post(URL, json={"query": query, "limit": 2})
        data = resp.json()

        for item in data.get("results", []):
            print(f"   🔹 [{item['score']:.2f}] {item['name']} (${item['price']})")

    except Exception as e:
        print(e)


if __name__ == "__main__":
    # Тест 1: Ищем лакшери (Должен быть Hotel Alpha)
    test_query("Luxury stay with spa and ocean view")

    # Тест 2: Ищем дешевку (Должен быть Hostel Beta)
    test_query("Cheap place for backpackers, low budget")

    # Тест 3: Нечеткий запрос (Контекст)
    test_query("Place for digital nomad to work and surf")
