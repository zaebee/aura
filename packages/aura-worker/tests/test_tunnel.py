"""Tests for the aura-worker Umbilical — the frpc STCP tunnel manager.
Subprocess, HTTP and the real filesystem are avoided via tmp paths + mocks.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
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


def _scripted_client(*outcomes):
    """An httpx.AsyncClient stand-in playing one outcome per stream() call.

    An outcome is either an exception — raised on entering the stream, which is
    where both a dropped connection and a raise_for_status land as far as the
    caller is concerned — or the bytes the response body should yield.

    Returns the client context manager and the list that records each attempt.
    """
    attempts: list[str] = []

    def _stream(method, url, **kwargs):
        attempts.append(url)
        outcome = outcomes[len(attempts) - 1]
        cm = MagicMock()
        cm.__aexit__ = AsyncMock(return_value=False)
        if isinstance(outcome, Exception):
            cm.__aenter__ = AsyncMock(side_effect=outcome)
            return cm

        response = MagicMock()
        response.raise_for_status = MagicMock()

        async def _aiter_bytes(chunk_size=8192, _body=outcome):
            yield _body

        response.aiter_bytes = _aiter_bytes
        cm.__aenter__ = AsyncMock(return_value=response)
        return cm

    client = MagicMock()
    client.stream = MagicMock(side_effect=_stream)
    client_cm = MagicMock()
    client_cm.__aenter__ = AsyncMock(return_value=client)
    client_cm.__aexit__ = AsyncMock(return_value=False)
    return client_cm, attempts


def _dropped_connection():
    return httpx.RemoteProtocolError("Server disconnected without sending a response.")


def _missing_release():
    request = httpx.Request("GET", "https://github.com/fatedier/frp")
    return httpx.HTTPStatusError(
        "404", request=request, response=httpx.Response(404, request=request)
    )


@pytest.mark.asyncio
async def test_ensure_frpc_retries_a_dropped_connection(tmp_path):
    """One blip must not end the download — this is what killed a Colab run."""
    u = _umbilical(tmp_path)
    client_cm, attempts = _scripted_client(_dropped_connection(), b"second-attempt")

    with patch("aura_worker.tunnel.httpx.AsyncClient", return_value=client_cm):
        with patch("aura_worker.tunnel.asyncio.sleep", AsyncMock()):
            # The retry succeeds at the network layer; the body is not the real
            # archive, so it stops at the checksum — past the point that failed.
            with pytest.raises(RuntimeError, match="Checksum verification failed"):
                await u.ensure_frpc()

    assert len(attempts) == 2


@pytest.mark.asyncio
async def test_ensure_frpc_reports_the_url_when_every_attempt_drops(tmp_path):
    u = _umbilical(tmp_path)
    client_cm, attempts = _scripted_client(
        _dropped_connection(), _dropped_connection(), _dropped_connection()
    )

    with patch("aura_worker.tunnel.httpx.AsyncClient", return_value=client_cm):
        with patch("aura_worker.tunnel.asyncio.sleep", AsyncMock()):
            with pytest.raises(RuntimeError, match="frp_0.61.0_linux_amd64.tar.gz"):
                await u.ensure_frpc()

    assert len(attempts) == u.FRPC_DOWNLOAD_ATTEMPTS == 3


@pytest.mark.asyncio
async def test_ensure_frpc_does_not_retry_a_missing_release(tmp_path):
    """A 404 will not heal on its own; retrying it only delays the truth."""
    u = _umbilical(tmp_path)
    client_cm, attempts = _scripted_client(_missing_release(), b"never-reached")

    with patch("aura_worker.tunnel.httpx.AsyncClient", return_value=client_cm):
        with patch("aura_worker.tunnel.asyncio.sleep", AsyncMock()):
            with pytest.raises(httpx.HTTPStatusError):
                await u.ensure_frpc()

    assert len(attempts) == 1


@pytest.mark.asyncio
async def test_ensure_frpc_does_not_retry_a_bad_checksum(tmp_path):
    """The integrity check is a verdict, not a transient error."""
    u = _umbilical(tmp_path)
    client_cm, attempts = _scripted_client(b"corrupted", b"corrupted")

    with patch("aura_worker.tunnel.httpx.AsyncClient", return_value=client_cm):
        with patch("aura_worker.tunnel.asyncio.sleep", AsyncMock()):
            with pytest.raises(RuntimeError, match="Checksum verification failed"):
                await u.ensure_frpc()

    assert len(attempts) == 1


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
