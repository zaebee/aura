import json
import re
from typing import Any


def clean_and_parse_json(text: str) -> dict[str, Any]:
    """Clean response from Markdown and attempt to extract JSON.

    Handles various LLM response formats including:
    - Markdown-wrapped JSON: ```json\n{...}\n```
    - Raw JSON strings
    - JSON embedded in text
    - Code block wrapped JSON: ```\n{...}\n```
    """
    if not text or not isinstance(text, str):
        raise ValueError(f"Invalid input: expected string, got {type(text)}")

    # 1. Remove Markdown code block markers
    text = re.sub(r"^```json\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    # 2. Try direct JSON parsing
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 3. Look for JSON object in text (fallback)
    # Pattern: find content between first { and last }
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # 4. Try to extract JSON from common LLM patterns
    # Pattern: "response": {...} or "action": {...}
    json_match = re.search(
        r'"(response|action|result)"\s*:\s*(\{.*\})', text, re.DOTALL
    )
    if json_match:
        try:
            return json.loads(json_match.group(2))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Failed to parse valid JSON from LLM response: {text[:100]}...")
