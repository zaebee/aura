import os
import shutil
import subprocess  # nosec B404
import threading
import time

import requests
import torch


class AuraNode:
    def __init__(self):
        self.ollama_process: subprocess.Popen | None = None
        self.status = "Idle"
        self.is_running = False
        self.requests_processed = 0
        self.lock = threading.Lock()
        self.gpu_active, self.gpu_info = self._check_gpu()

    def _check_gpu(self) -> tuple[bool, str]:
        """System Check Enzyme: verify if a GPU is active."""
        try:
            if torch.cuda.is_available():
                device_name = torch.cuda.get_device_name(0)
                return True, f"GPU Active: {device_name}"
        except (ImportError, RuntimeError):  # nosec B110
            # Catch specific errors related to torch or CUDA availability
            pass

        # Fallback to nvidia-smi
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],  # nosec B603 B607
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                return True, f"GPU Active: {result.stdout.strip()}"
        except (FileNotFoundError, subprocess.SubprocessError):  # nosec B110
            # nvidia-smi not found or failed to run
            pass

        return False, "⚠️ DEGRADED (CPU MODE)"

    def start_ollama(self, log_callback=print):
        with self.lock:
            if self.ollama_process:
                return

            if shutil.which("ollama") is None:
                raise RuntimeError(
                    "Ollama not found. Please install it first: curl -fsSL https://ollama.com/install.sh | sh"
                )

            log_callback("--- Starting Ollama server ---")
            if not self.gpu_active:
                log_callback(
                    "SCREAM: Running on CPU mode! Performance will be severely limited."
                )

            # Enable debug logging for Ollama to ensure thought capture stability
            env = os.environ.copy()
            env["OLLAMA_DEBUG"] = "1"

            self.ollama_process = subprocess.Popen(
                ["ollama", "serve"],  # nosec B603 B607
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
            )

            threading.Thread(
                target=self._read_output,
                args=(self.ollama_process, log_callback),
                daemon=True,
            ).start()

        # Wait for ollama to be up
        for _ in range(30):
            try:
                requests.get("http://localhost:11434", timeout=5)  # nosec B113
                log_callback("Ollama server is up.")
                return
            except requests.exceptions.RequestException:
                time.sleep(1)

        self.stop_ollama()
        raise RuntimeError("Ollama failed to start within 30 seconds.")

    def pull_model(self, model: str, log_callback=print):
        if not model or model.lstrip().startswith("-"):
            raise ValueError(f"Invalid model name provided: '{model}'")
        log_callback(f"--- Pulling model: {model} ---")
        pull_proc = subprocess.Popen(
            ["ollama", "pull", model],  # nosec B603 B607
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        for line in pull_proc.stdout:
            log_callback(line.strip())
        pull_proc.wait()

        if pull_proc.returncode != 0:
            raise RuntimeError(f"Failed to pull model {model}")

    def _read_output(self, process, log_callback):
        for line in process.stdout:
            log_callback(line.strip())
            # Increment stats on successful inference requests
            with self.lock:
                if "POST /api/generate" in line or "POST /api/chat" in line:
                    self.requests_processed += 1

    def stop_ollama(self):
        with self.lock:
            if self.ollama_process:
                self.ollama_process.terminate()
                try:
                    self.ollama_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.ollama_process.kill()
                self.ollama_process = None
        return "Ollama stopped"

    def get_status(self) -> str:
        with self.lock:
            if not self.gpu_active:
                return "⚠️ DEGRADED (CPU MODE)"
            return self.status
