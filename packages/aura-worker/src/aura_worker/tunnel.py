import asyncio
import hashlib
import os
import secrets
import signal
import subprocess  # nosec B404
from pathlib import Path

import requests
import toml


class Umbilical:
    """Manages the secure STCP tunnel connection to the Hive Hub using frpc."""

    FRPC_VERSION = "0.61.0"
    FRPC_SHA256 = "720a9fe2a3299346572544909a78c023344c88bde13c55b921e298e8c5ded21f"

    def __init__(
        self,
        hive_host: str,
        frp_token: str,
        punk_key: str,
        frp_port: int = 7000,
        worker_id: str | None = None,
    ):
        self.hive_host = hive_host
        self.frp_port = frp_port
        self.frp_token = frp_token
        self.punk_key = punk_key
        self.worker_id = worker_id or secrets.token_hex(4)
        self.proxy_name = f"ollama-worker-{self.worker_id}"

        self.work_dir = Path.home() / ".aura" / "worker"
        self.bin_dir = self.work_dir / "bin"
        self.frpc_path = self.bin_dir / "frpc"
        self.config_path = self.work_dir / "frpc.toml"

        self.process: asyncio.subprocess.Process | None = None

    def ensure_frpc(self):
        if self.frpc_path.exists():
            return

        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.bin_dir.mkdir(parents=True, exist_ok=True)

        frp_file = f"frp_{self.FRPC_VERSION}_linux_amd64.tar.gz"
        frp_url = f"https://github.com/fatedier/frp/releases/download/v{self.FRPC_VERSION}/{frp_file}"

        print(f"Downloading frpc v{self.FRPC_VERSION}...")
        response = requests.get(frp_url, stream=True, timeout=30)  # nosec B113
        response.raise_for_status()

        tar_path = self.bin_dir / frp_file
        sha256 = hashlib.sha256()

        with open(tar_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                sha256.update(chunk)

        if sha256.hexdigest() != self.FRPC_SHA256:
            tar_path.unlink()
            raise RuntimeError(
                f"Checksum verification failed for frpc! Expected {self.FRPC_SHA256}, got {sha256.hexdigest()}"
            )

        print("Checksum verified. Extracting...")
        subprocess.run(
            ["tar", "-xzf", str(tar_path), "-C", str(self.bin_dir)],
            check=True,  # nosec B603 B607
        )

        extracted_dir = self.bin_dir / f"frp_{self.FRPC_VERSION}_linux_amd64"
        (extracted_dir / "frpc").rename(self.frpc_path)

        # Cleanup
        tar_path.unlink()
        subprocess.run(["rm", "-rf", str(extracted_dir)], check=True)  # nosec B603 B607
        self.frpc_path.chmod(0o755)
        print(f"frpc installed at {self.frpc_path}")

    def _generate_config(self):
        config_data = {
            "serverAddr": self.hive_host,
            "serverPort": self.frp_port,
            "auth": {"method": "token", "token": self.frp_token},
            "transport": {"tcpMux": True},
            "loginFailExit": False,
            "proxies": [
                {
                    "name": self.proxy_name,
                    "type": "stcp",
                    "secretKey": self.punk_key,
                    "localIP": "127.0.0.1",
                    "localPort": 11434,
                }
            ],
            "visitors": [
                {
                    "name": f"nats-visitor-{self.worker_id}",
                    "type": "stcp",
                    "serverName": "hive-nats",
                    "secretKey": self.punk_key,
                    "bindAddr": "127.0.0.1",
                    "bindPort": 4222,
                }
            ],
        }
        with open(self.config_path, "w") as f:
            toml.dump(config_data, f)

    async def cleanup_zombies(self):
        """Kill any process listening on port 7000."""
        try:
            process = await asyncio.create_subprocess_exec(
                "lsof", "-t", "-i:7000",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            pids = stdout.decode().strip().split()
            for pid in pids:
                if pid:
                    try:
                        os.kill(int(pid), signal.SIGTERM)
                    except ProcessLookupError:
                        pass
        except Exception:  # nosec B110
            pass

    async def start(self, log_callback=print):
        await asyncio.to_thread(self.ensure_frpc)
        await asyncio.to_thread(self._generate_config)

        log_callback(f"--- Starting Umbilical (STCP Tunnel: {self.proxy_name}) ---")

        if self.process:
            await self.stop()

        await self.cleanup_zombies()

        self.process = await asyncio.create_subprocess_exec(
            str(self.frpc_path), "-c", str(self.config_path),  # nosec B603
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        asyncio.create_task(self._read_output(log_callback))

    async def _read_output(self, log_callback):
        if not self.process or not self.process.stdout:
            return

        while True:
            line = await self.process.stdout.readline()
            if not line:
                break
            text = line.decode().strip()
            log_callback(text)
            if "login to server success" in text:
                log_callback(f"--- Umbilical Connected to Hive at {self.hive_host} ---")

    async def stop(self):
        if self.process:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5)
            except TimeoutError:
                self.process.kill()
            self.process = None

        if self.config_path.exists():
            try:
                self.config_path.unlink()
            except OSError:
                pass
        return "Tunnel stopped"

    @property
    def is_alive(self) -> bool:
        return self.process is not None and self.process.returncode is None
