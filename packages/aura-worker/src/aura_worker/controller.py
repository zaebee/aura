import asyncio
import logging
import secrets

import gradio as gr

from .metabolism import HiveLogHandler, MetabolicLoop
from .node import AuraNode
from .tunnel import Umbilical


class WorkerController:
    """
    Worker Metabolism Controller: Orchestrates the start/stop and state management.
    Separates the visual Phenotype (UI) from the internal Metabolism.
    """

    def __init__(self):
        self.node = AuraNode()
        self.log_handler: HiveLogHandler | None = None
        self.metabolism: MetabolicLoop | None = None
        self.umbilical: Umbilical | None = None
        self.worker_id = secrets.token_hex(4)
        self.original_log_level: int | None = None
        self.ui_log_queue = asyncio.Queue(maxsize=5000)
        self.full_logs = []

    def log(self, message):
        """Internal log callback that secretes logs into the UI queue."""
        clean_msg = str(message).strip()
        if not clean_msg:
            return

        # Add to the UI queue for gr.Timer to consume
        try:
            self.ui_log_queue.put_nowait(clean_msg + "\n")
        except (asyncio.QueueFull, RuntimeError):
            pass

        # Also push to HiveLogHandler if active for NATS streaming
        if self.log_handler:
            self.log_handler.write(clean_msg)
        else:
            # Fallback to console during bootstrap
            print(f"[Worker] {clean_msg}")

    async def start(
        self, model, hive_host, nats_url, frp_token, punk_key, frp_port, progress=None
    ):
        if progress is None:
            progress = gr.Progress()

        async with self.node.lock:
            if self.node.is_running:
                return "Node is already running."

        try:
            progress(0, desc="Starting Ollama...")
            await self.node.start_ollama(log_callback=self.log)

            progress(0.3, desc=f"Pulling model {model}...")
            await self.node.pull_model(model, log_callback=self.log)

            progress(0.7, desc="Establishing Umbilical...")
            self.umbilical = Umbilical(
                hive_host=hive_host,
                frp_token=frp_token,
                punk_key=punk_key,
                frp_port=int(frp_port),
                worker_id=self.worker_id,
            )
            await self.umbilical.start(log_callback=self.log)

            # Initialize Log Protein and Metabolic Loop
            progress(0.8, desc="Synchronizing with Hive Bloodstream...")
            self.log_handler = HiveLogHandler(
                worker_name=self.worker_id, nats_url=nats_url, ui_queue=self.ui_log_queue
            )
            self.metabolism = MetabolicLoop(
                worker_name=self.worker_id, nats_url=nats_url
            )

            # Setup standard logging
            root_logger = logging.getLogger()
            self.original_log_level = root_logger.level
            root_logger.addHandler(self.log_handler)
            root_logger.setLevel(logging.INFO)

            await self.log_handler.start()
            await self.metabolism.start(kill_callback=self.stop)

            async with self.node.lock:
                self.node.is_running = True
                self.node.status = "Connected"

            return "Node Started Successfully!"
        except Exception as e:
            self.log(f"Error starting node: {e}")
            await self.stop()
            return f"Error: {e}"

    async def stop(self):
        self.log("--- Stopping Aura Node ---")

        if self.metabolism:
            await self.metabolism.stop()
            self.metabolism = None

        if self.log_handler:
            root_logger = logging.getLogger()
            root_logger.removeHandler(self.log_handler)
            if self.original_log_level is not None:
                root_logger.setLevel(self.original_log_level)
            await self.log_handler.stop()
            self.log_handler = None

        if self.umbilical:
            await self.umbilical.stop()
            self.umbilical = None

        await self.node.stop_ollama()

        async with self.node.lock:
            self.node.is_running = False
            self.node.status = "Idle"

        return "Node Stopped"

    async def test_pulse(self):
        if not self.log_handler or not self.log_handler.is_connected:
            return "❌ NATS not connected. Start the node first."

        success = await self.log_handler.send_test_event()
        if success:
            return "✅ Pulse Sent! Check NATS bloodstream."
        else:
            return "❌ Failed to send pulse (check tunnel)."

    async def get_ui_logs(self):
        """Drains the UI log queue and returns the concatenated string."""
        while not self.ui_log_queue.empty():
            try:
                msg = self.ui_log_queue.get_nowait()
                self.full_logs.append(msg)
            except (asyncio.QueueEmpty, RuntimeError):
                break

        # Keep only last 1000 lines to avoid memory bloat
        if len(self.full_logs) > 1000:
            self.full_logs = self.full_logs[-1000:]

        return "".join(self.full_logs)

    async def get_status(self):
        node_status = await self.node.get_status()
        nats_status = "🔴 Offline"

        if self.metabolism and self.metabolism.is_connected:
            nats_status = "🟢 Connected (Pulse Active)"
        elif self.node.is_running:
            nats_status = "🟠 Pending (Connecting...)"

        async with self.node.lock:
            if self.node.is_running:
                # Check if processes are still alive
                if (
                    self.node.ollama_process
                    and self.node.ollama_process.returncode is not None
                ):
                    self.node.status = "Error: Ollama process stopped"
                    self.node.is_running = False
                elif self.umbilical and not self.umbilical.is_alive:
                    self.node.status = "Error: Umbilical process stopped"
                    self.node.is_running = False

            requests_processed = self.node.requests_processed

        return node_status, nats_status, requests_processed
