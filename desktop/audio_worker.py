import json
import logging
import requests
from PyQt5.QtCore import QThread, pyqtSignal as Signal

logger = logging.getLogger("ace.audio_worker")
API_BASE_URL = "http://127.0.0.1:8000/api"


class ChatWorker(QThread):
    """Worker thread for sending chat text messages to backend API with real-time token streaming and cancellation."""
    token_received = Signal(str)            # Emitted for each streaming token
    tool_started = Signal(str)              # Emitted when desktop tool begins executing
    response_received = Signal(str, str, str) # user_text, ai_response, tool_executed
    error_occurred = Signal(str)

    def __init__(self, message: str, speak: bool = True):
        super().__init__()
        self.message = message
        self.speak = speak
        self._is_stopped = False

    def stop(self):
        """Cancel the streaming request immediately."""
        self._is_stopped = True

    def run(self):
        full_response = ""
        tool_executed = ""
        stream_succeeded = False

        # Attempt 1: Real-time SSE streaming endpoint
        try:
            with requests.post(
                f"{API_BASE_URL}/chat/stream",
                json={"message": self.message, "speak": self.speak},
                stream=True,
                timeout=(20, 300)
            ) as res:
                if res.status_code == 200:
                    stream_succeeded = True
                    for raw_line in res.iter_lines(decode_unicode=True):
                        if self._is_stopped:
                            logger.info("ChatWorker stream stopped by user.")
                            break
                        if not raw_line:
                            continue
                        line = raw_line.strip()
                        if not line.startswith("data: "):
                            continue

                        data_str = line[6:]
                        try:
                            event = json.loads(data_str)
                        except Exception:
                            continue

                        event_type = event.get("type")
                        if event_type == "token":
                            token = event.get("content", "")
                            full_response += token
                            self.token_received.emit(token)
                        elif event_type == "tool_start":
                            t_name = event.get("tool", "")
                            self.tool_started.emit(t_name)
                        elif event_type == "tool_result":
                            tool_executed = event.get("tool", "") or tool_executed
                        elif event_type == "done":
                            full_response = event.get("response", full_response)
                            tool_executed = event.get("tool_executed", tool_executed)
                        elif event_type == "error":
                            self.error_occurred.emit(event.get("error", "Unknown stream error"))
                            return

                    self.response_received.emit(self.message, full_response, tool_executed or "")
                    return
        except Exception as e:
            logger.warning(f"SSE stream failed, attempting standard chat endpoint fallback: {e}")

        # Attempt 2: Standard non-streaming fallback
        if not stream_succeeded and not self._is_stopped:
            try:
                res = requests.post(
                    f"{API_BASE_URL}/chat",
                    json={"message": self.message, "speak": self.speak},
                    timeout=120
                )
                if res.status_code == 200:
                    data = res.json()
                    ai_resp = data.get("response", "")
                    tool_exec = data.get("tool_executed", "")
                    self.response_received.emit(self.message, ai_resp, tool_exec or "")
                else:
                    self.error_occurred.emit(f"Server error: {res.status_code}")
            except Exception as e:
                self.error_occurred.emit(str(e))


class VoiceWorker(QThread):
    """Worker thread for continuous voice conversation loop."""
    response_received = Signal(str, str, str, bool) # transcript, ai_response, tool_executed, has_speech
    error_occurred = Signal(str)

    def run(self):
        try:
            res = requests.post(f"{API_BASE_URL}/voice/listen", timeout=300)
            if res.status_code == 200:
                data = res.json()
                transcript = data.get("transcript", "")
                ai_resp = data.get("response", "")
                tool_exec = data.get("tool_executed", "")
                has_speech = data.get("has_speech", False)
                self.response_received.emit(transcript, ai_resp, tool_exec or "", has_speech)
            else:
                self.error_occurred.emit(f"Server error: {res.status_code}")
        except Exception as e:
            self.error_occurred.emit(str(e))
