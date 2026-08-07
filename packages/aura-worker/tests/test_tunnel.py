"""Tests for the aura-worker Umbilical — the frpc STCP tunnel manager.
Subprocess, HTTP and the real filesystem are avoided via tmp paths + mocks.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import toml
from aura_worker.tunnel import Umbilical


def _umbilical(tmp_path, **kwargs):
    """An Umbilical with all filesystem paths redirected under tmp_path."""
    defaults = {
        "hive_host": "hive.example",
        "frp_token": "tok",
        "punk_key": "secret-key",
    }
    u = Umbilical(**{**defaults, **kwargs})
    u.work_dir = tmp_path
    u.bin_dir = tmp_path / "bin"
    u.frpc_path = u.bin_dir / "frpc"
    u.config_path = tmp_path / "frpc.toml"
    return u


# --- __init__ ---------------------------------------------------------------


def test_init_generates_worker_id_and_proxy_name(tmp_path):
    u = _umbilical(tmp_path)
    assert len(u.worker_id) == 8  # secrets.token_hex(4)
    assert u.proxy_name == f"ollama-worker-{u.worker_id}"


def test_init_honours_explicit_worker_id(tmp_path):
    u = _umbilical(tmp_path, worker_id="node-42")
    assert u.worker_id == "node-42"
    assert u.proxy_name == "ollama-worker-node-42"


# --- _generate_config -------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_config_writes_expected_proxy(tmp_path):
    u = _umbilical(tmp_path, worker_id="w1")
    await u._generate_config()

    cfg = toml.load(u.config_path)
    assert cfg["serverAddr"] == "hive.example"
    assert cfg["serverPort"] == 7000
    assert cfg["auth"] == {"method": "token", "token": "tok"}
    (proxy,) = cfg["proxies"]
    assert proxy["name"] == "ollama-worker-w1"
    assert proxy["type"] == "stcp"
    assert proxy["secretKey"] == "secret-key"
    assert proxy["localPort"] == 11434


@pytest.mark.asyncio
async def test_generate_config_adds_nats_visitor_when_active(tmp_path):
    u = _umbilical(tmp_path, worker_id="w1", nats_active=True)
    await u._generate_config()

    cfg = toml.load(u.config_path)
    (visitor,) = cfg["visitors"]
    assert visitor["name"] == "nats-visitor-w1"
    assert visitor["bindPort"] == 4222
    assert visitor["secretKey"] == "secret-key"


@pytest.mark.asyncio
async def test_generate_config_omits_nats_visitor_when_inactive(tmp_path):
    u = _umbilical(tmp_path, nats_active=False)
    await u._generate_config()

    cfg = toml.load(u.config_path)
    assert cfg["visitors"] == []


# --- ensure_frpc ------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_frpc_skips_download_when_binary_present(tmp_path):
    u = _umbilical(tmp_path)
    u.bin_dir.mkdir(parents=True, exist_ok=True)
    u.frpc_path.write_text("binary")

    with patch("aura_worker.tunnel.httpx.AsyncClient") as client:
        await u.ensure_frpc()

    client.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_frpc_rejects_bad_checksum(tmp_path):
    u = _umbilical(tmp_path)

    # Mock httpx streaming so the "download" writes known bytes whose sha256
    # won't match FRPC_SHA256 -> RuntimeError, and the partial tarball is removed.
    response = MagicMock()
    response.raise_for_status = MagicMock()

    async def _aiter_bytes(chunk_size=8192):
        yield b"corrupted-frpc-archive"

    response.aiter_bytes = _aiter_bytes
    stream_cm = MagicMock()
    stream_cm.__aenter__ = AsyncMock(return_value=response)
    stream_cm.__aexit__ = AsyncMock(return_value=False)
    client = MagicMock()
    client.stream = MagicMock(return_value=stream_cm)
    client_cm = MagicMock()
    client_cm.__aenter__ = AsyncMock(return_value=client)
    client_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("aura_worker.tunnel.httpx.AsyncClient", return_value=client_cm):
        with pytest.raises(RuntimeError, match="Checksum verification failed"):
            await u.ensure_frpc()

    tar_path = u.bin_dir / f"frp_{u.FRPC_VERSION}_linux_amd64.tar.gz"
    assert not tar_path.exists()  # partial download cleaned up


# --- stop -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_terminates_process_and_removes_config(tmp_path):
    u = _umbilical(tmp_path)
    u.config_path.write_text("dummy")
    proc = MagicMock()
    proc.terminate = MagicMock()
    proc.wait = AsyncMock()
    u.process = proc

    result = await u.stop()

    assert result == "Tunnel stopped"
    proc.terminate.assert_called_once()
    assert u.process is None
    assert not u.config_path.exists()


@pytest.mark.asyncio
async def test_stop_without_process_still_returns_message(tmp_path):
    u = _umbilical(tmp_path)
    assert await u.stop() == "Tunnel stopped"


# --- is_alive ---------------------------------------------------------------


def test_is_alive_false_without_process(tmp_path):
    assert _umbilical(tmp_path).is_alive is False


def test_is_alive_true_while_running(tmp_path):
    u = _umbilical(tmp_path)
    proc = MagicMock()
    proc.returncode = None
    u.process = proc
    assert u.is_alive is True


def test_is_alive_false_after_exit(tmp_path):
    u = _umbilical(tmp_path)
    proc = MagicMock()
    proc.returncode = 0
    u.process = proc
    assert u.is_alive is False


# --- _read_output -----------------------------------------------------------


@pytest.mark.asyncio
async def test_read_output_announces_connection(tmp_path):
    u = _umbilical(tmp_path)
    proc = MagicMock()
    proc.stdout = MagicMock()
    proc.stdout.readline = AsyncMock(
        side_effect=[b"[I] starting\n", b"[I] login to server success\n", b""]
    )
    u.process = proc
    logs: list[str] = []

    await u._read_output(logs.append)

    assert any("Umbilical Connected to Hive at hive.example" in line for line in logs)
