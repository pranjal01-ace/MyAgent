import threading
import logging
from enum import Enum
from typing import Callable, List

logger = logging.getLogger("assistant.state")

class AssistantState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    RETRIEVING = "retrieving"
    THINKING = "thinking"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    ERROR = "error"

class StateMachine:
    """Thread-safe assistant state manager with listener callbacks."""

    def __init__(self, initial_state: AssistantState = AssistantState.IDLE):
        self._state = initial_state
        self._lock = threading.Lock()
        self._listeners: List[Callable[[AssistantState, AssistantState], None]] = []

    @property
    def current(self) -> AssistantState:
        with self._lock:
            return self._state

    def transition_to(self, new_state: AssistantState):
        with self._lock:
            old_state = self._state
            if old_state == new_state:
                return
            self._state = new_state

        logger.info(f"State transition: [{old_state.value.upper()}] ──► [{new_state.value.upper()}]")
        for listener in self._listeners:
            try:
                listener(old_state, new_state)
            except Exception as e:
                logger.error(f"Error in state listener callback: {e}")

    def add_listener(self, callback: Callable[[AssistantState, AssistantState], None]):
        with self._lock:
            self._listeners.append(callback)
