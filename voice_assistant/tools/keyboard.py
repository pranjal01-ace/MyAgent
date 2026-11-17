import logging
from typing import Callable, Optional

logger = logging.getLogger("assistant.keyboard")

class KeyboardControls:
    """Global keyboard hotkey listener (F8=Activate, ESC=Interrupt, F9=Mute/Unmute)."""

    def __init__(
        self,
        on_activate: Optional[Callable[[], None]] = None,
        on_interrupt: Optional[Callable[[], None]] = None,
        on_toggle_mute: Optional[Callable[[], None]] = None
    ):
        self.on_activate = on_activate
        self.on_interrupt = on_interrupt
        self.on_toggle_mute = on_toggle_mute
        self._listener_started = False

    def start(self):
        try:
            import keyboard
            keyboard.add_hotkey("F8", self._handle_f8)
            keyboard.add_hotkey("esc", self._handle_esc)
            keyboard.add_hotkey("F9", self._handle_f9)
            self._listener_started = True
            logger.info("Keyboard controls active (F8=Activate, ESC=Interrupt, F9=Mute/Unmute).")
        except Exception as e:
            logger.warning(f"Keyboard listener initialization warning ({e}); hotkeys disabled.")

    def _handle_f8(self):
        logger.info("Hotkey F8 pressed: Activate Assistant.")
        if self.on_activate:
            self.on_activate()

    def _handle_esc(self):
        logger.info("Hotkey ESC pressed: Interrupt TTS / Cancel Generation.")
        if self.on_interrupt:
            self.on_interrupt()

    def _handle_f9(self):
        logger.info("Hotkey F9 pressed: Toggle Mute.")
        if self.on_toggle_mute:
            self.on_toggle_mute()
