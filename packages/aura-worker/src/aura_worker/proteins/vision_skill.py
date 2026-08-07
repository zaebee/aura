import base64
import json
import re
from pathlib import Path
from typing import Any

import httpx
import structlog
from pydantic import BaseModel, Field, ValidationError

logger = structlog.get_logger(__name__)


class VehicleSpec(BaseModel):
    """The Vehicle Spec Genotype."""

    make: str = Field(..., description="Vehicle manufacturer")
    model: str = Field(..., description="Vehicle model name")
    year: int = Field(..., description="Manufacturing year")
    color: str = Field(..., description="Primary exterior color")
    estimated_price: float = Field(..., description="Estimated market value in USD")
    confidence_score: float = Field(
        ..., description="Identification confidence (0.0-1.0)"
    )


class VisionSkill:
    """Vision Protein: Identifies vehicles using multimodal Ollama."""

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        model_name: str = "gemma3:latest",
    ):
        self.ollama_url = ollama_url
        self.model_name = model_name

        # Load the phenotype (system prompt)
        phenotype_path = Path(__file__).parent / "vision.md"
        try:
            self.system_prompt = phenotype_path.read_text()
        except FileNotFoundError:
            self.system_prompt = "Identify the vehicle in the image and return JSON."
            logger.warning("vision_phenotype_missing", path=str(phenotype_path))

    async def get_encoded_images(self, image_sources: list[str | bytes]) -> list[str]:
        """Encodes images to base64 strings."""
        encoded = []
        for source in image_sources:
            if isinstance(source, bytes):
                encoded.append(base64.b64encode(source).decode("utf-8"))
            elif isinstance(source, str):
                path = Path(source)
                if path.exists():
                    encoded.append(base64.b64encode(path.read_bytes()).decode("utf-8"))
                else:
                    # Assume it's already base64 or a URL (not handled here for simplicity)
                    encoded.append(source)
        return encoded

    async def generate(
        self, image_sources: list[str | bytes], prompt_override: str | None = None
    ) -> dict[str, Any]:
        """Calls Ollama's /api/generate with vision support."""
        images = await self.get_encoded_images(image_sources)
        prompt = prompt_override or "Identify the vehicle in this image."

        payload = {
            "model": self.model_name,
            "prompt": f"{self.system_prompt}\n\nUser Request: {prompt}",
            "images": images,
            "stream": False,
            "format": "json",
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(
                    f"{self.ollama_url}/api/generate", json=payload
                )
                response.raise_for_status()
                result = response.json()
                raw_output = result.get("response", "{}")
                return await self.membrane_validate(raw_output)
            except Exception as e:
                logger.error("vision_generate_error", error=str(e))
                return {"error": str(e)}

    async def membrane_validate(self, raw_json: str) -> dict[str, Any]:
        """The Membrane: validates and repairs JSON output."""
        try:
            # Clean common LLM artifacts (markdown blocks)
            clean_json = re.sub(r"```json\s*|\s*```", "", raw_json).strip()
            data = json.loads(clean_json)

            # If empty, return as is
            if not data:
                return {}

            # Validate against Genotype
            spec = VehicleSpec.model_validate(data)
            return spec.model_dump()
        except (json.JSONDecodeError, ValidationError) as e:
            logger.warning("misfolded_json_detected", error=str(e), raw=raw_json)
            return await self.attempt_repair(raw_json)

    async def attempt_repair(self, raw_json: str) -> dict[str, Any]:
        """Simple heuristic repair for misfolded JSON."""
        # Check if we can extract something using regex if JSON failed
        try:
            # Try to find anything that looks like a JSON object
            match = re.search(r"\{.*\}", raw_json, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                # Partial validation/fill
                return {
                    "make": data.get("make", "Unknown"),
                    "model": data.get("model", "Unknown"),
                    "year": int(data.get("year", 0)),
                    "color": data.get("color", "Unknown"),
                    "estimated_price": float(data.get("estimated_price", 0.0)),
                    "confidence_score": float(data.get("confidence_score", 0.0)),
                }
        except Exception:  # nosec B110
            pass

        return {"error": "Misfolded output could not be repaired", "raw": raw_json}
