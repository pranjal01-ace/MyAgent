"""
Gesture Registry for Phase 3 Vision Subsystem.

Stores definitions and action mappings for all recognized gestures.
Maintains metadata including enabled status, confidence threshold, cooldown, and bound action.
"""

import logging
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from backend.vision.models import GestureType
from backend.vision.config import get_vision_config

logger = logging.getLogger("ace.vision.registry")


class GestureDefinition(BaseModel):
    """Metadata and action configuration for a registered gesture."""
    name: str = Field(..., description="Unique gesture identifier matching GestureType")
    description: str = Field(..., description="Human-readable description of gesture meaning")
    enabled: bool = Field(default=True, description="Whether gesture execution is actively enabled")
    confidence_threshold: float = Field(default=0.65, description="Minimum confidence required to trigger action")
    cooldown_ms: int = Field(default=1000, description="Minimum milliseconds required between repeat triggers")
    action: str = Field(..., description="Target action identifier dispatched upon recognition")


class GestureRegistry:
    """Central registry of recognizable gestures and their safe system action bindings."""

    def __init__(self):
        self._gestures: Dict[str, GestureDefinition] = {}
        self._initialize_default_gestures()

    def _initialize_default_gestures(self) -> None:
        """Populates the registry with standard Phase 3 safe gestures and actions."""
        cfg = get_vision_config()
        default_conf = cfg.confidence_threshold
        default_cool = cfg.cooldown_ms

        defaults = [
            GestureDefinition(
                name=GestureType.WAVE.value,
                description="Friendly hand wave greeting",
                enabled=True,
                confidence_threshold=default_conf,
                cooldown_ms=default_cool,
                action="ace_greeting"
            ),
            GestureDefinition(
                name=GestureType.THUMBS_UP.value,
                description="Approval or agreement gesture",
                enabled=True,
                confidence_threshold=default_conf,
                cooldown_ms=default_cool,
                action="ace_positive_reaction"
            ),
            GestureDefinition(
                name=GestureType.OPEN_PALM.value,
                description="Halt / stop current Ace speaking or active background action",
                enabled=True,
                confidence_threshold=default_conf,
                cooldown_ms=default_cool,
                action="stop_current_action"
            ),
            GestureDefinition(
                name=GestureType.PEACE.value,
                description="Peace / victory sign for character interaction",
                enabled=True,
                confidence_threshold=default_conf,
                cooldown_ms=default_cool,
                action="ace_peace_reaction"
            ),
            GestureDefinition(
                name=GestureType.PINCH.value,
                description="Index & thumb pinch for action confirmation or selection",
                enabled=True,
                confidence_threshold=default_conf,
                cooldown_ms=default_cool,
                action="ace_confirmation_reaction"
            ),
            GestureDefinition(
                name=GestureType.FIST.value,
                description="Closed fist - no destructive action, acknowledged safely",
                enabled=True,
                confidence_threshold=default_conf,
                cooldown_ms=default_cool,
                action="safe_reaction"
            ),
            GestureDefinition(
                name=GestureType.POINT.value,
                description="Pointing index finger - acknowledged safely",
                enabled=True,
                confidence_threshold=default_conf,
                cooldown_ms=default_cool,
                action="safe_reaction"
            ),
        ]

        for defn in defaults:
            self.register(defn)

    def register(self, definition: GestureDefinition) -> None:
        """Registers or updates a gesture definition."""
        key = definition.name.upper()
        self._gestures[key] = definition
        logger.debug(f"Registered gesture: '{key}' -> action '{definition.action}'")

    def get(self, name: str) -> Optional[GestureDefinition]:
        """Retrieves a gesture definition by name."""
        return self._gestures.get(name.upper())

    def is_enabled(self, name: str) -> bool:
        """Checks if a gesture is registered and enabled."""
        defn = self.get(name)
        return defn is not None and defn.enabled

    def list_all(self) -> List[GestureDefinition]:
        """Returns all registered gesture definitions."""
        return list(self._gestures.values())

    def update(self, name: str, **kwargs) -> Optional[GestureDefinition]:
        """Updates configuration properties of an existing registered gesture."""
        defn = self.get(name)
        if not defn:
            return None

        current = defn.model_dump()
        for k, v in kwargs.items():
            if v is not None and k in current:
                current[k] = v

        updated = GestureDefinition(**current)
        self._gestures[name.upper()] = updated
        return updated


# Global singleton gesture registry
gesture_registry = GestureRegistry()
