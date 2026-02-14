import asyncio
import logging
import re
import threading
import uuid
from collections import deque
from datetime import UTC, datetime

from aura_core_gen.aura.core.v1 import Event, LogEvent
from nats.aio.client import Client as NATS


class HiveLogHandler(logging.Handler):
    """
    Log Protein: Streams worker logs into the NATS bloodstream.
    Uses an internal asyncio.Queue to ensure logging never blocks LLM inference.
    Aligned with Chromosomal DNA v0.3.0.
    """

    def __init__(
        self,
        worker_name: str,
        nats_url: str = "nats://localhost:4222",
        max_logs: int = 1000,
        ui_queue: asyncio.Queue[str] | None = None,
    ) -> None:
        super().__init__()
        self.worker_name: str = worker_name
        self.nats_url: str = nats_url
        self.queue: asyncio.Queue[Event | None] = asyncio.Queue(maxsize=10000)
        self.ui_queue: asyncio.Queue[str] | None = ui_queue
        self.loop: asyncio.AbstractEventLoop | None = None
        self._processing_task: asyncio.Task[None] | None = None
        self._nats_client: NATS = NATS()

        # Keep internal deque for local Gradio UI compatibility (Legacy/Fallback)
        self.local_logs: deque[str] = deque(maxlen=max_logs)
        self.lock: threading.Lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        log_entry: str = self.format(record)

        # Add to local deque for UI
        with self.lock:
            self.local_logs.append(log_entry + "\n")

        # Put in UI queue if present
        if self.ui_queue and self.loop and self.loop.is_running():
            try:
                self.loop.call_soon_threadsafe(
                    self.ui_queue.put_nowait, log_entry + "\n"
                )
            except (asyncio.QueueFull, RuntimeError):
                pass

        # Extract thought metadata if present (Gemma 3 Thought Capture)
        metadata: dict[str, str] = {}
        if "<think>" in log_entry:
            match = re.search(r"<think>(.*?)</think>", log_entry, re.DOTALL)
            if match:
                metadata["thought"] = match.group(1).strip()
            elif "<think>" in log_entry and "</think>" not in log_entry:
                # Handle partial/streamed thoughts if they appear line-by-line
                metadata["thought_state"] = "started"

        # Create binary Event
        # Aligned: event_id -> identifier
        event: Event = Event(
            identifier=str(uuid.uuid4()),
            topic=f"aura.worker.{self.worker_name}.logs",
            timestamp=datetime.fromtimestamp(record.created, tz=UTC),
            log=LogEvent(
                level=record.levelname,
                message=log_entry,
                logger_name=record.name,
                worker_name=self.worker_name,
            ),
            metadata=metadata,
        )

        # Put in queue for NATS background task
        if self.loop and self.loop.is_running():
            try:
                self.loop.call_soon_threadsafe(self.queue.put_nowait, event)
            except (asyncio.QueueFull, RuntimeError):
                pass  # Drop logs if queue is full or loop closing to avoid blocking

    def write(self, data: str) -> None:
        """Captures redirected stdout (e.g. from Ollama) and logs it as INFO."""
        if not data:
            return

        clean_data: str = data.strip()
        if not clean_data:
            return

        # Create a dummy record for stdout
        record: logging.LogRecord = logging.LogRecord(
            name="ollama",
            level=logging.INFO,
            pathname="node.py",
            lineno=0,
            msg=clean_data,
            args=(),
            exc_info=None,
        )
        self.emit(record)

    def get_logs(self) -> str:
        with self.lock:
            return "".join(self.local_logs)

    def clear(self) -> None:
        with self.lock:
            self.local_logs.clear()

    async def send_test_event(self) -> bool:
        """Manually send a test event to NATS to verify the umbilical pulse."""
        if not self.is_connected:
            return False

        event: Event = Event(
            identifier=str(uuid.uuid4()),
            topic=f"aura.worker.{self.worker_name}.test",
            timestamp=datetime.now(tz=UTC),
            log=LogEvent(
                level="INFO",
                message="PULSE CHECK: NATS Telepathic Logger is active.",
                logger_name="test_pulse",
                worker_name=self.worker_name,
            ),
        )
        try:
            await self._nats_client.publish(event.topic, bytes(event))
            return True
        except Exception as e:
            logging.warning("Failed to send test pulse: %s", e)
            return False

    async def start(self) -> bool:
        """Initialize NATS connection and start background processing task."""
        self.loop = asyncio.get_running_loop()
        try:
            await self._nats_client.connect(
                self.nats_url,
                connect_timeout=2,
                reconnect_time_wait=1,
                max_reconnect_attempts=60,
            )
            self._processing_task = asyncio.create_task(self._process_queue())
            return True
        except Exception:
            # Fallback print if NATS is not available yet. Avoid logging the exception to prevent credential leaks.
            print("HiveLogHandler NATS connection pending.")
            return False

    async def stop(self) -> None:
        """Gracefully stop the log handler, ensuring the queue is flushed."""
        if self.queue:
            await self.queue.put(None)

        if self._processing_task:
            try:
                await self._processing_task
            except Exception:  # nosec B110
                pass
            self._processing_task = None

        if self._nats_client.is_connected:
            await self._nats_client.drain()
            await self._nats_client.close()

    async def _process_queue(self) -> None:
        while True:
            try:
                event: Event | None = await self.queue.get()
                if event is None:
                    self.queue.task_done()
                    break

                if self._nats_client.is_connected:
                    await self._nats_client.publish(event.topic, bytes(event))
            except Exception as e:
                # Don't use logging here to avoid infinite recursion if it fails
                print(f"Error streaming log to NATS: {e}")
            finally:
                self.queue.task_done()

    @property
    def is_connected(self) -> bool:
        return bool(self._nats_client.is_connected)
