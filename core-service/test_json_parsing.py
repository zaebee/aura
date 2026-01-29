#!/usr/bin/env python3
"""
Test the robust JSON parsing function in DSPy strategy.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent / "src"))

from llm.prepare.clean import clean_and_parse_json


def test_json_parsing():
    """Test various JSON response formats."""
    print("🧪 Testing robust JSON parsing...")

    # Test cases: (input, expected_output)
    test_cases = [
        # 1. Clean JSON
        (
            '{"action": "accept", "price": 100, "message": "OK"}',
            {"action": "accept", "price": 100, "message": "OK"},
        ),
        # 2. Markdown-wrapped JSON
        (
            '```json\n{"action": "counter", "price": 150, "message": "Counter"}\n```',
            {"action": "counter", "price": 150, "message": "Counter"},
        ),
        # 3. Code block without json specifier
        (
            '```\n{"action": "reject", "price": 0, "message": "No"}\n```',
            {"action": "reject", "price": 0, "message": "No"},
        ),
        # 4. JSON with extra text
        (
            'Here is the response: {"action": "accept", "price": 200, "message": "Yes"}',
            {"action": "accept", "price": 200, "message": "Yes"},
        ),
        # 5. JSON embedded in response field
        (
            '{"response": {"action": "counter", "price": 175, "message": "Maybe"}}',
            {"response": {"action": "counter", "price": 175, "message": "Maybe"}},
        ),
        # 6. Whitespace and newlines
        (
            '  \n  ```json  \n  {"action": "accept", "price": 120, "message": "Sure"}  \n  ```  \n  ',
            {"action": "accept", "price": 120, "message": "Sure"},
        ),
        # 7. Code block with json specifier
        (
            '```json\n{"action": "reject", "price": 0, "message": "No"}\n```',
            {"action": "reject", "price": 0, "message": "No"},
        ),
        # 8. Code block with json specifier
        (
            '```json\n{\n    "action": "counter",\n    "price": 950,\n    "message": "Thank you for your offer. Given current high demand, we cannot accommodate $600, but I can offer you a rate of $950 with a complimentary room upgrade included. This reflects excellent value for our premium accommodations."\n}\n```',
            {
                "action": "counter",
                "price": 950,
                "message": "Thank you for your offer. Given current high demand, we cannot accommodate $600, but I can offer you a rate of $950 with a complimentary room upgrade included. This reflects excellent value for our premium accommodations.",
            },
        ),
    ]

    passed = 0
    failed = 0

    for i, (input_text, expected) in enumerate(test_cases, 1):
        try:
            result = clean_and_parse_json(input_text)
            if result == expected:
                print(f"✅ Test {i}: PASSED")
                passed += 1
            else:
                print(f"❌ Test {i}: FAILED - Expected {expected}, got {result}")
                failed += 1
        except Exception as e:
            print(f"❌ Test {i}: FAILED with exception: {e}")
            failed += 1

    # Test error cases
    print("\n🧪 Testing error cases...")

    error_cases = [
        None,
        "",
        "not a json",
        "{",  # Incomplete JSON
        "no braces at all",
    ]

    for i, bad_input in enumerate(error_cases, 1):
        try:
            clean_and_parse_json(bad_input)
            print(f"❌ Error test {i}: Should have failed but didn't")
            failed += 1
        except ValueError:
            print(f"✅ Error test {i}: Correctly raised ValueError")
            passed += 1
        except Exception as e:
            print(f"❌ Error test {i}: Wrong exception type: {e}")
            failed += 1

    print(f"\n📊 Results: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    success = test_json_parsing()
    sys.exit(0 if success else 1)
