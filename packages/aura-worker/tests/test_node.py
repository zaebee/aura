"""Tests for the aura-worker AuraNode — Ollama lifecycle + vision inference.
Subprocess and HTTP are mocked; no real Ollama/torch needed.
"""

import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aura_worker.node import VISION_MODEL, VISION_OLLAMA_URL, AuraNode


def _mock_httpx_client(post_return=None, post_side_effect=None):
    client = AsyncMock()
    client.post = AsyncMock(return_value=post_return, side_effect=post_side_effect)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm, client


def _ollama_response(response_text: str):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value={"response": response_text})
    return resp


# --- __init__ ---------------------------------------------------------------


def test_init_defaults():
    node = AuraNode()
    assert node.status == "Idle"
    assert node.is_running is False
    assert node.requests_processed == 0
    assert node.gpu_active is False
    assert node.ollama_process is None


# --- analyze_vision ---------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_vision_parses_ollama_json():
    cm, client = _mock_httpx_client(
        _ollama_response(json.dumps({"make": "Toyota", "model": "Camry"}))
    )
    with patch("aura_worker.node.httpx.AsyncClient", return_value=cm):
        result = await AuraNode().analyze_vision([b"image-bytes"], "identify")

    assert result == {"make": "Toyota", "model": "Camry"}


@pytest.mark.asyncio
async def test_analyze_vision_builds_expected_payload():
    cm, client = _mock_httpx_client(_ollama_response("{}"))
    with patch("aura_worker.node.httpx.AsyncClient", return_value=cm):
        await AuraNode().analyze_vision([b"img-a", b"img-b"], "find car")

    url, kwargs = client.post.await_args.args[0], client.post.await_args.kwargs
    assert url == VISION_OLLAMA_URL
    payload = kwargs["json"]
    assert payload["model"] == VISION_MODEL
    assert payload["prompt"] == "find car"
    assert payload["images"] == [
        base64.b64encode(b"img-a").decode("utf-8"),
        base64.b64encode(b"img-b").decode("utf-8"),
    ]


@pytest.mark.asyncio
async def test_analyze_vision_invalid_json_returns_error():
    cm, _ = _mock_httpx_client(_ollama_response("this is not json"))
    with patch("aura_worker.node.httpx.AsyncClient", return_value=cm):
        result = await AuraNode().analyze_vision([b"img"], "p")

    assert result["error"] == "Invalid JSON from Ollama"
    assert result["raw"] == "this is not json"


@pytest.mark.asyncio
async def test_analyze_vision_http_failure_returns_error():
    cm, _ = _mock_httpx_client(post_side_effect=RuntimeError("connection refused"))
    with patch("aura_worker.node.httpx.AsyncClient", return_value=cm):
        result = await AuraNode().analyze_vision([b"img"], "p")

    assert result == {"error": "connection refused"}


# --- get_status -------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_status_gpu_active_returns_base_status():
    node = AuraNode()
    node.gpu_active = True
    node.status = "Processing"
    assert await node.get_status() == "Processing"


@pytest.mark.asyncio
async def test_get_status_cpu_mode_while_running():
    node = AuraNode()
    node.gpu_active = False
    node.is_running = True
    node.status = "Processing"
    assert await node.get_status() == "Processing (⚠️ CPU MODE)"


@pytest.mark.asyncio
async def test_get_status_cpu_mode_idle_is_degraded():
    node = AuraNode()
    node.gpu_active = False
    node.is_running = False
    assert await node.get_status() == "⚠️ DEGRADED (CPU MODE)"


# --- pull_model (input validation) -----------------------------------------


@pytest.mark.asyncio
async def test_pull_model_rejects_empty_name():
    with pytest.raises(ValueError):
        await AuraNode().pull_model("")


@pytest.mark.asyncio
async def test_pull_model_rejects_flag_like_name():
    with pytest.raises(ValueError):
        await AuraNode().pull_model("  --rm")


# --- stop_ollama ------------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_ollama_terminates_running_process():
    node = AuraNode()
    proc = MagicMock()
    proc.terminate = MagicMock()
    proc.wait = AsyncMock()
    node.ollama_process = proc

    result = await node.stop_ollama()

    assert result == "Ollama stopped"
    proc.terminate.assert_called_once()
    assert node.ollama_process is None


@pytest.mark.asyncio
async def test_stop_ollama_without_process_is_noop():
    node = AuraNode()
    assert await node.stop_ollama() == "Ollama stopped"


# --- _read_output -----------------------------------------------------------


@pytest.mark.asyncio
async def test_read_output_counts_inference_requests():
    node = AuraNode()
    proc = MagicMock()
    proc.stdout = MagicMock()
    proc.stdout.readline = AsyncMock(
        side_effect=[
            b"GET / 200\n",
            b"POST /api/generate 200\n",
            b"POST /api/chat 200\n",
            b"",  # EOF
        ]
    )
    logs: list[str] = []

    await node._read_output(proc, logs.append)

    assert node.requests_processed == 2
    assert "POST /api/generate 200" in logs


@pytest.mark.asyncio
async def test_read_output_no_stdout_returns_quietly():
    node = AuraNode()
    proc = MagicMock()
    proc.stdout = None
    await node._read_output(proc, print)  # should not raise
    assert node.requests_processed == 0
