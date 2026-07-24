"""Tests for the aura-worker MetabolicLoop — NATS command + Vision-RPC handling.
NATS and the worker node are mocked; the Vision RPC uses a real Signal proto.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from aura_core_gen.aura.core.v1 import Observation, PerceptionSignal, Signal
from aura_worker.metabolism import MetabolicLoop
from aura_worker.metabolism.main import VISION_ANALYZE_SUBJECT


def _msg(data: bytes, subject: str = "aura.worker.w.commands"):
    m = MagicMock()
    m.data = data
    m.subject = subject
    m.respond = AsyncMock()
    return m


def _signal_bytes(images: list[bytes], prompt: str) -> bytes:
    return bytes(Signal(perception=PerceptionSignal(image_data=images, prompt=prompt)))


# --- _handle_message (control signals) -------------------------------------


@pytest.mark.asyncio
async def test_kill_signal_invokes_sync_callback():
    fired = []
    loop = MetabolicLoop("w")
    loop._kill_callback = lambda: fired.append(True)
    await loop._handle_message(_msg(b"KILL"))  # case-insensitive
    assert fired == [True]


@pytest.mark.asyncio
async def test_kill_signal_awaits_async_callback():
    fired = []

    async def cb():
        fired.append(True)

    loop = MetabolicLoop("w")
    loop._kill_callback = cb
    await loop._handle_message(_msg(b"kill"))
    assert fired == [True]


@pytest.mark.asyncio
async def test_non_kill_message_is_ignored():
    fired = []
    loop = MetabolicLoop("w")
    loop._kill_callback = lambda: fired.append(True)
    await loop._handle_message(_msg(b"status"))
    assert fired == []


# --- _handle_vision_request (proto path) -----------------------------------


@pytest.mark.asyncio
async def test_vision_request_delegates_to_node_and_responds_observation():
    node = AsyncMock()
    node.analyze_vision = AsyncMock(return_value={"make": "Toyota", "model": "Camry"})
    loop = MetabolicLoop("w", node=node)
    msg = _msg(_signal_bytes([b"image-bytes"], "find the car"))

    await loop._handle_vision_request(msg)

    node.analyze_vision.assert_awaited_once()
    images, prompt = node.analyze_vision.await_args.args
    assert list(images) == [b"image-bytes"]
    assert prompt == "find the car"

    msg.respond.assert_awaited_once()
    obs = Observation().parse(msg.respond.await_args.args[0])
    assert obs.success is True


@pytest.mark.asyncio
async def test_vision_request_without_images_responds_error():
    node = AsyncMock()
    loop = MetabolicLoop("w", node=node)
    msg = _msg(_signal_bytes([], "prompt"))

    await loop._handle_vision_request(msg)

    node.analyze_vision.assert_not_awaited()
    obs = Observation().parse(msg.respond.await_args.args[0])
    assert obs.success is False
    assert "No images" in obs.error


@pytest.mark.asyncio
async def test_vision_request_without_node_responds_error():
    loop = MetabolicLoop("w", node=None)
    msg = _msg(_signal_bytes([b"img"], "prompt"))

    await loop._handle_vision_request(msg)

    obs = Observation().parse(msg.respond.await_args.args[0])
    assert obs.success is False
    assert "Node not initialized" in obs.error


@pytest.mark.asyncio
async def test_vision_request_propagates_node_error_into_observation():
    node = AsyncMock()
    node.analyze_vision = AsyncMock(return_value={"error": "ollama down"})
    loop = MetabolicLoop("w", node=node)
    msg = _msg(_signal_bytes([b"img"], "p"))

    await loop._handle_vision_request(msg)

    obs = Observation().parse(msg.respond.await_args.args[0])
    assert obs.success is False
    assert obs.error == "ollama down"


# --- start / stop / is_connected -------------------------------------------


@pytest.mark.asyncio
async def test_start_connects_and_subscribes_to_both_subjects():
    loop = MetabolicLoop("worker-1")
    loop.nc = AsyncMock()

    ok = await loop.start()

    assert ok is True
    loop.nc.connect.assert_awaited_once()
    subjects = [call.args[0] for call in loop.nc.subscribe.await_args_list]
    assert "aura.worker.worker-1.commands" in subjects
    assert VISION_ANALYZE_SUBJECT in subjects


@pytest.mark.asyncio
async def test_start_returns_false_when_connect_fails():
    loop = MetabolicLoop("w")
    loop.nc = AsyncMock()
    loop.nc.connect = AsyncMock(side_effect=RuntimeError("no server"))

    assert await loop.start() is False


@pytest.mark.asyncio
async def test_stop_drains_and_closes_when_connected():
    loop = MetabolicLoop("w")
    loop.nc = MagicMock()
    loop.nc.is_connected = True
    loop.nc.drain = AsyncMock()
    loop.nc.close = AsyncMock()

    await loop.stop()

    loop.nc.drain.assert_awaited_once()
    loop.nc.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_is_noop_when_disconnected():
    loop = MetabolicLoop("w")
    loop.nc = MagicMock()
    loop.nc.is_connected = False
    loop.nc.drain = AsyncMock()

    await loop.stop()

    loop.nc.drain.assert_not_awaited()


def test_is_connected_reflects_client_state():
    loop = MetabolicLoop("w")
    loop.nc = MagicMock()
    loop.nc.is_connected = True
    assert loop.is_connected is True
