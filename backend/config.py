"""Legacy facade re-exporting settings from backend.core.config."""
from backend.core.config import settings, Settings, BASE_DIR

__all__ = ["settings", "Settings", "BASE_DIR"]
