"""Tests for the aura-worker VisionSkill — the ATCG "Membrane" that validates
and repairs the LLM's vehicle-identification JSON. Pure logic + a mocked Ollama
HTTP call; no torch/gradio needed.
"""

import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aura_worker.proteins.vision_skill import VehicleSpec, VisionSkill
from pydantic import ValidationError

VALID_SPEC = {
    "make": "Toyota",
    "model": "Camry",
    "year": 2020,
    "color": "red",
    "estimated_price": 25000.0,
    "confidence_score": 0.9,
}


# --- VehicleSpec (the genotype) --------------------------------------------


def test_vehicle_spec_accepts_valid_payload():
    spec = VehicleSpec.model_validate(VALID_SPEC)
    assert spec.make == "Toyota"
    assert spec.year == 2020
    assert spec.confidence_score == 0.9


def test_vehicle_spec_rejects_missing_field():
    payload = {k: v for k, v in VALID_SPEC.items() if k != "year"}
    with pytest.raises(ValidationError):
        VehicleSpec.model_validate(payload)


# --- membrane_validate ------------------------------------------------------


@pytest.mark.asyncio
async def test_membrane_validate_plain_json():
    result = await VisionSkill().membrane_validate(json.dumps(VALID_SPEC))
    assert result == VALID_SPEC


@pytest.mark.asyncio
async def test_membrane_validate_strips_markdown_fences():
    fenced = f"```json\n{json.dumps(VALID_SPEC)}\n```"
    result = await VisionSkill().membrane_validate(fenced)
    assert result["make"] == "Toyota"
    assert result["estimated_price"] == 25000.0


@pytest.mark.asyncio
async def test_membrane_validate_empty_object_returns_empty():
    assert await VisionSkill().membrane_validate("{}") == {}


@pytest.mark.asyncio
async def test_membrane_validate_bad_schema_falls_back_to_repair():
    # Valid JSON but missing required fields -> ValidationError -> repair fills defaults.
    result = await VisionSkill().membrane_validate('{"make": "Honda"}')
    assert result["make"] == "Honda"
    assert result["model"] == "Unknown"
    assert result["year"] == 0


@pytest.mark.asyncio
async def test_membrane_validate_malformed_json_falls_back_to_repair():
    result = await VisionSkill().membrane_validate("not json at all")
    assert result["error"] == "Misfolded output could not be repaired"
    assert result["raw"] == "not json at all"


# --- attempt_repair ---------------------------------------------------------


@pytest.mark.asyncio
async def test_attempt_repair_extracts_embedded_json_and_fills_defaults():
    raw = 'Here is the answer: {"make": "Ford", "year": "2019"} thanks!'
    result = await VisionSkill().attempt_repair(raw)
    assert result["make"] == "Ford"
    assert result["year"] == 2019  # coerced from string
    assert result["model"] == "Unknown"
    assert result["estimated_price"] == 0.0


@pytest.mark.asyncio
async def test_attempt_repair_unrepairable_returns_error():
    result = await VisionSkill().attempt_repair("totally unstructured text")
    assert result["error"] == "Misfolded output could not be repaired"
    assert result["raw"] == "totally unstructured text"


# --- get_encoded_images -----------------------------------------------------


@pytest.mark.asyncio
async def test_get_encoded_images_encodes_bytes():
    result = await VisionSkill().get_encoded_images([b"raw-image-bytes"])
    assert result == [base64.b64encode(b"raw-image-bytes").decode("utf-8")]


@pytest.mark.asyncio
async def test_get_encoded_images_reads_existing_file(tmp_path):
    img = tmp_path / "car.jpg"
    img.write_bytes(b"file-image-bytes")
    result = await VisionSkill().get_encoded_images([str(img)])
    assert result == [base64.b64encode(b"file-image-bytes").decode("utf-8")]


@pytest.mark.asyncio
async def test_get_encoded_images_passes_through_nonexistent_string():
    # A non-file string (URL / already-base64) is passed through unchanged.
    result = await VisionSkill().get_encoded_images(["already-base64-or-url"])
    assert result == ["already-base64-or-url"]


# --- generate (Ollama call mocked) -----------------------------------------


def _mock_httpx_client(post_return=None, post_side_effect=None):
    """Build a patch target for httpx.AsyncClient used as an async context manager."""
    client = AsyncMock()
    client.post = AsyncMock(return_value=post_return, side_effect=post_side_effect)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


@pytest.mark.asyncio
async def test_generate_success_validates_ollama_response():
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value={"response": json.dumps(VALID_SPEC)})
    cm = _mock_httpx_client(post_return=response)

    with patch("aura_worker.proteins.vision_skill.httpx.AsyncClient", return_value=cm):
        result = await VisionSkill().generate(
            [b"image-bytes"], prompt_override="find car"
        )

    assert result == VALID_SPEC


@pytest.mark.asyncio
async def test_generate_returns_error_dict_on_http_failure():
    cm = _mock_httpx_client(post_side_effect=RuntimeError("connection refused"))

    with patch("aura_worker.proteins.vision_skill.httpx.AsyncClient", return_value=cm):
        result = await VisionSkill().generate([b"image-bytes"])

    assert result["error"] == "connection refused"
