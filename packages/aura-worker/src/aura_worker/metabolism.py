import collections
import threading


class HiveLogHandler:
    def __init__(self, max_logs: int = 1000):
        self.logs = collections.deque(maxlen=max_logs)
        self.lock = threading.Lock()

    def write(self, data: str):
        with self.lock:
            if data:
                # Strip and add newline if missing for consistent display
                clean_data = data.strip()
                if clean_data:
                    self.logs.append(clean_data + "\n")

    def get_logs(self) -> str:
        with self.lock:
            return "".join(self.logs)

    def clear(self):
        with self.lock:
            self.logs.clear()
