import asyncio
import os
import shutil
import signal
from collections.abc import Callable
from typing import Any

import httpx
import structlog
import torch

logger = structlog.get_logger(__name__)


class AuraNode:
    def __init__(self) -> None:
        self.ollama_process: asyncio.subprocess.Process | None = None
        self.status: str = "Idle"
        self.is_running: bool = False
        self.requests_processed: int = 0
        self.lock: asyncio.Lock = asyncio.Lock()
        self.gpu_active: bool = False
        self.gpu_info: str = "Checking GPU..."

    async def _check_gpu(self) -> tuple[bool, str]:
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
            proc = await asyncio.create_subprocess_exec(
                "nvidia-smi",
                "--query-gpu=name",
                "--format=csv,noheader",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                return True, f"GPU Active: {stdout.decode().strip()}"
        except (FileNotFoundError, Exception):  # nosec B110
            # nvidia-smi not found or failed to run
            pass

        return False, "⚠️ DEGRADED (CPU MODE)"

    async def cleanup_zombies(self) -> None:
        """Kill any process listening on port 11434."""
        try:
            process = await asyncio.create_subprocess_exec(
                "lsof",
                "-t",
                "-i:11434",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            pids: list[str] = stdout.decode().strip().split()
            for pid in pids:
                if pid:
                    try:
                        os.kill(int(pid), signal.SIGTERM)
                    except ProcessLookupError:
                        pass
        except Exception:
            logger.warning(
                "Failed to clean up zombie processes on port 11434", exc_info=True
            )

    async def start_ollama(self, log_callback: Callable[[Any], None] = print) -> None:
        async with self.lock:
            if self.ollama_process:
                return

            # Verify GPU before starting
            self.gpu_active, self.gpu_info = await self._check_gpu()

            await self.cleanup_zombies()

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
            env: dict[str, str] = os.environ.copy()
            env["OLLAMA_DEBUG"] = "1"
            env["OLLAMA_MAX_LOADED_MODELS"] = "1"
            env["OLLAMA_NUM_PARALLEL"] = "1"
            env["OLLAMA_FLASH_ATTENTION"] = "0"

            self.ollama_process = await asyncio.create_subprocess_exec(
                "ollama",
                "serve",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
            )

            asyncio.create_task(self._read_output(self.ollama_process, log_callback))

        # Wait for ollama to be up
        async with httpx.AsyncClient() as client:
            for _ in range(30):
                try:
                    await client.get("http://localhost:11434", timeout=5)
                    log_callback("Ollama server is up.")
                    return
                except Exception:  # nosec B110
                    await asyncio.sleep(1)

        await self.stop_ollama()
        raise RuntimeError("Ollama failed to start within 30 seconds.")

    async def pull_model(
        self, model: str, log_callback: Callable[[Any], None] = print
    ) -> None:
        if not model or model.lstrip().startswith("-"):
            raise ValueError(f"Invalid model name provided: '{model}'")
        log_callback(f"--- Pulling model: {model} ---")

        pull_proc: asyncio.subprocess.Process = await asyncio.create_subprocess_exec(
            "ollama",
            "pull",
            model,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        if pull_proc.stdout:
            while True:
                line: bytes = await pull_proc.stdout.readline()
                if not line:
                    break
                log_callback(line.decode().strip())

        await pull_proc.wait()

        if pull_proc.returncode != 0:
            raise RuntimeError(f"Failed to pull model {model}")

    async def _read_output(
        self, process: asyncio.subprocess.Process, log_callback: Callable[[Any], None]
    ) -> None:
        if process.stdout is None:
            return
        while True:
            line: bytes = await process.stdout.readline()
            if not line:
                break
            text: str = line.decode().strip()
            log_callback(text)
            # Increment stats on successful inference requests
            async with self.lock:
                if "POST /api/generate" in text or "POST /api/chat" in text:
                    self.requests_processed += 1

    async def stop_ollama(self) -> str:
        async with self.lock:
            if self.ollama_process:
                self.ollama_process.terminate()
                try:
                    await asyncio.wait_for(self.ollama_process.wait(), timeout=5)
                except TimeoutError:
                    self.ollama_process.kill()
                self.ollama_process = None
        return "Ollama stopped"

    async def get_status(self) -> str:
        async with self.lock:
            base_status = self.status
            if not self.gpu_active:
                if self.is_running:
                    return f"{base_status} (⚠️ CPU MODE)"
                return "⚠️ DEGRADED (CPU MODE)"
            return base_status
