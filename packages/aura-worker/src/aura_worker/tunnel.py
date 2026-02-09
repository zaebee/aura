import hashlib
import secrets
import subprocess  # nosec B404
import threading
from pathlib import Path

import requests
import toml


class Umbilical:
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

        self.process: subprocess.Popen | None = None

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
            ["tar", "-xzf", str(tar_path), "-C", str(self.bin_dir)], check=True  # nosec B603 B607
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
            "proxies": [
                {
                    "name": self.proxy_name,
                    "type": "stcp",
                    "secretKey": self.punk_key,
                    "localIP": "127.0.0.1",
                    "localPort": 11434,
                }
            ],
        }
        with open(self.config_path, "w") as f:
            toml.dump(config_data, f)

    def start(self, log_callback=print):
        self.ensure_frpc()
        self._generate_config()

        log_callback(f"--- Starting Umbilical (STCP Tunnel: {self.proxy_name}) ---")

        if self.process:
            self.stop()

        self.process = subprocess.Popen(
            [str(self.frpc_path), "-c", str(self.config_path)],  # nosec B603
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        threading.Thread(
            target=self._read_output, args=(log_callback,), daemon=True
        ).start()

    def _read_output(self, log_callback):
        if not self.process or not self.process.stdout:
            return

        for line in self.process.stdout:
            log_callback(line.strip())
            if "login to server success" in line:
                log_callback(f"--- Umbilical Connected to Hive at {self.hive_host} ---")

    def stop(self):
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
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
        return self.process is not None and self.process.poll() is None
