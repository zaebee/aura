import base64
import json
import re
from typing import Any

import httpx
import structlog
from pydantic import ValidationError

logger = structlog.get_logger(__name__)

# The Auto-Savant Phenotype: High-precision vehicle identification
_PERCEPTION_PROMPT = """# 👁️ Aura Vision: Vehicle Identification Phenotype

You are a specialized vision-enabled AI in the Aura Hive. Your primary objective is the high-precision identification and specification of vehicles from visual sensory input.

## 🧬 Instructions

1.  **Analyze** the provided image carefully to identify the make, model, and year of the vehicle.
2.  **Extract** visual attributes such as color and body style.
3.  **Estimate** a fair market price based on the vehicle's apparent condition and market trends (use USD).
4.  **Assign** a confidence score (0.0 to 1.0) to your identification.
5.  **Output** ONLY a valid JSON object following the strict Genotype schema.

## 🧬 Genotype Schema (Strict JSON)

```json
{
  "make": "string",
  "model": "string",
  "year": 2024,
  "color": "string",
  "estimated_price": 50000.0,
  "confidence_score": 0.95
}
```

## 🛡️ Membrane Rules

- Do NOT include any conversational text or markdown blocks (other than the JSON itself).
- If multiple vehicles are present, identify the most prominent one.
- If no vehicle is found, return an empty object `{}`.
"""


class PerceptionEngine:
    def __init__(self, ollama_url: str, model: str):
        self.ollama_url = ollama_url
        self.model = model

    async def perceive_image(self, image_bytes: bytes) -> dict[str, Any]:
        """Calls Ollama's /api/generate with multimodal support."""
        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        payload = {
            "model": self.model,
            "prompt": _PERCEPTION_PROMPT,
            "stream": False,
            "images": [base64_image],
            "format": "json",
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(
                    f"{self.ollama_url}/api/generate", json=payload
                )
                response.raise_for_status()
                result = response.json()
                response_text = result.get("response", "")
                return self._parse_and_validate(response_text)
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                logger.error("perception_engine_error", error=str(e))
                return self._get_fallback_item(str(e))

    def _parse_and_validate(self, raw_json: str) -> dict[str, Any]:
        """Validates and repairs JSON output."""
        try:
            # Clean common LLM artifacts
            clean_json = re.sub(r"```json\s*|\s*```", "", raw_json).strip()
            data = json.loads(clean_json)

            if not data:
                return {}

            # Minimal check for required fields for internal dict
            # In a more strict setup, we'd use a Pydantic model here too.
            return {
                "make": data.get("make", "Unknown"),
                "model": data.get("model", "Unknown"),
                "year": int(data.get("year", 0)),
                "color": data.get("color", "Unknown"),
                "estimated_price": float(data.get("estimated_price", 0.0)),
                "confidence_score": float(data.get("confidence_score", 0.0)),
                # Map to ItemData-like fields for the Aggregator
                "id": f"perceived-{data.get('make', 'unknown')}-{data.get('model', 'unknown')}",
                "name": f"{data.get('year', '')} {data.get('make', '')} {data.get('model', '')}".strip(),
                "base_price": float(data.get("estimated_price", 0.0)),
                "floor_price": float(data.get("estimated_price", 0.0)) * 0.9,
                "meta": {
                    "color": data.get("color", "Unknown"),
                    "confidence": str(data.get("confidence_score", 0.0))
                }
            }
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            logger.error("perception_mapping_error", error=str(e), text=raw_json)
            return self._get_fallback_item(f"Parse error: {e}")

    def _get_fallback_item(self, error: str) -> dict[str, Any]:
        return {
            "id": "unknown",
            "name": "Unknown Item",
            "base_price": 0.0,
            "floor_price": 0.0,
            "meta": {"error": error},
            "error": error
        }
