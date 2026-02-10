import base64
import hashlib
import json
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)


class PerceptionEngine:
    def __init__(self, ollama_url: str, model: str):
        self.ollama_url = ollama_url
        self.model = model

    async def perceive_image(self, image_bytes: bytes) -> dict[str, Any]:
        """Calls Ollama's /api/generate with multimodal support."""
        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        prompt = """
        Analyze this image. If it is a car, describe it and provide estimated prices in JSON format.
        JSON format:
        {
            "name": "Car Make and Model",
            "base_price": 50000.0,
            "floor_price": 45000.0,
            "meta": {
                "color": "Color",
                "condition": "Condition",
                "type": "car"
            }
        }
        If it is not a car, still try to describe it in this format but set type to its category.
        Only return the JSON.
        """

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "images": [base64_image],
            "format": "json",
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.ollama_url}/api/generate", json=payload
                )
                response.raise_for_status()
                result = response.json()
                response_text = result.get("response", "")
                return self.map_text_to_item(response_text)
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            logger.error("perception_engine_error", error=str(e))
            return self._get_fallback_item(str(e))

    def map_text_to_item(self, text: str) -> dict[str, Any]:
        """The Mapping Enzyme: maps text response into Item-like dict."""
        try:
            data = json.loads(text)
            # Use a stable hash for asset ID
            item_hash = hashlib.sha256(text.encode()).hexdigest()[:12]

            # Ensure meta values are strings for Protobuf compatibility
            raw_meta = data.get("meta", {})
            meta = {str(k): str(v) for k, v in raw_meta.items()}

            return {
                "id": f"perceived-{item_hash}",
                "name": data.get("name", "Unknown Item"),
                "base_price": float(data.get("base_price", 0.0)),
                "floor_price": float(data.get("floor_price", 0.0)),
                "meta": meta,
            }
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            logger.error("mapping_error", error=str(e), text=text)
            return self._get_fallback_item(f"Parse error: {e}")

    def _get_fallback_item(self, error: str) -> dict[str, Any]:
        return {
            "id": "unknown",
            "name": "Unknown Item",
            "base_price": 0.0,
            "floor_price": 0.0,
            "meta": {"error": error},
        }
