"""
Gesture Events and Action Resolver for Phase 3 Vision Subsystem.

Translates normalized GestureEvent objects into safe Ace companion reactions,
TTS speech control, WebSocket UI notifications, and tool interactions.
"""

import asyncio
import logging
from typing import Dict, Any, Optional

from backend.vision.models import GestureEvent, GestureType
from backend.vision.gesture_registry import gesture_registry
from backend.api.websocket import ws_manager
from backend.voice.service import tts_engine

logger = logging.getLogger("ace.vision.events")


class GestureActionResolver:
    """
    Resolves recognized gesture events into concrete, safe system and character actions.
    Ensures safe execution without invoking unconfirmed dangerous commands.
    """

    def __init__(self):
        self.registry = gesture_registry

    async def dispatch_event(self, event: GestureEvent) -> Dict[str, Any]:
        """
        Dispatches a validated GestureEvent to the appropriate Ace subsystem.
        """
        gesture_name = event.gesture.value if isinstance(event.gesture, GestureType) else str(event.gesture)
        defn = self.registry.get(gesture_name)

        if not defn:
            logger.warning(f"No definition found for gesture '{gesture_name}'. Ignoring.")
            return {"status": "ignored", "reason": "unknown_gesture"}

        if not defn.enabled:
            logger.info(f"Gesture '{gesture_name}' is disabled in registry. Ignoring.")
            return {"status": "ignored", "reason": "gesture_disabled"}

        action = defn.action
        logger.info(
            f"Gesture detected: {gesture_name} confidence={event.confidence:.2f} "
            f"(hand: {event.hand.value}) -> Action: {action}"
        )

        # 1. Broadcast gesture event over WebSocket to connected frontend / companion clients
        try:
            await ws_manager.broadcast_event(
                "gesture_detected",
                {
                    "id": event.id,
                    "gesture": gesture_name,
                    "confidence": event.confidence,
                    "hand": event.hand.value,
                    "state": event.state.value,
                    "action": action,
                    "duration_ms": event.duration_ms,
                    "timestamp": event.timestamp.isoformat()
                }
            )
        except Exception as e:
            logger.warning(f"Failed to broadcast gesture via WebSocket: {e}")

        # 2. Execute target action safely
        result = await self._execute_action(action, event)
        return result

    async def _execute_action(self, action: str, event: GestureEvent) -> Dict[str, Any]:
        """Maps registered action strings to specific safe Ace behaviors."""

        if action == "stop_current_action":
            # OPEN_PALM: Instant barge-in stop
            logger.info("Executing 'stop_current_action': halting active Ace speech and pending actions.")
            try:
                tts_engine.stop()
                await ws_manager.broadcast_event(
                    "character_reaction",
                    {"action": "stop", "reaction": "interrupted", "gesture": event.gesture.value}
                )
                return {"status": "success", "action": action, "detail": "Active speech and tasks stopped."}
            except Exception as e:
                logger.error(f"Error executing stop_current_action: {e}")
                return {"status": "error", "error": str(e)}

        elif action == "ace_greeting":
            # WAVE: Friendly greeting
            logger.info("Executing 'ace_greeting': Ace responds to user wave.")
            try:
                await ws_manager.broadcast_event(
                    "character_reaction",
                    {"action": "wave", "animation": "greeting", "reaction": "friendly_wave"}
                )
                # Play short Ace greeting if not already speaking
                if not tts_engine.is_speaking():
                    tts_engine.speak_stream_chunk("Hey there! Good to see you! What's on your mind?")
                return {"status": "success", "action": action, "detail": "Ace responded with greeting."}
            except Exception as e:
                logger.error(f"Error executing ace_greeting: {e}")
                return {"status": "error", "error": str(e)}

        elif action == "ace_positive_reaction":
            # THUMBS_UP: Positive encouragement
            logger.info("Executing 'ace_positive_reaction': Ace gives positive response.")
            try:
                await ws_manager.broadcast_event(
                    "character_reaction",
                    {"action": "thumbs_up", "animation": "nod", "reaction": "positive"}
                )
                if not tts_engine.is_speaking():
                    tts_engine.speak_stream_chunk("Alright! Love the energy, let's keep that fire going!")
                return {"status": "success", "action": action, "detail": "Ace responded positively."}
            except Exception as e:
                logger.error(f"Error executing ace_positive_reaction: {e}")
                return {"status": "error", "error": str(e)}

        elif action == "ace_peace_reaction":
            # PEACE: Peace gesture response
            logger.info("Executing 'ace_peace_reaction': Ace reacts to peace sign.")
            try:
                await ws_manager.broadcast_event(
                    "character_reaction",
                    {"action": "peace", "animation": "smile", "reaction": "peace"}
                )
                if not tts_engine.is_speaking():
                    tts_engine.speak_stream_chunk("Peace! Ace is right here with you.")
                return {"status": "success", "action": action, "detail": "Ace responded with peace reaction."}
            except Exception as e:
                logger.error(f"Error executing ace_peace_reaction: {e}")
                return {"status": "error", "error": str(e)}

        elif action == "ace_confirmation_reaction":
            # PINCH: Acknowledge selection / confirmation
            logger.info("Executing 'ace_confirmation_reaction': Acknowledging pinch gesture.")
            try:
                await ws_manager.broadcast_event(
                    "character_reaction",
                    {"action": "confirm", "animation": "nod", "reaction": "confirmed"}
                )
                return {"status": "success", "action": action, "detail": "Pinch confirmation acknowledged."}
            except Exception as e:
                logger.error(f"Error executing ace_confirmation_reaction: {e}")
                return {"status": "error", "error": str(e)}

        elif action == "safe_reaction":
            # FIST / POINT: Passive recognition without destructive action
            logger.info(f"Executing 'safe_reaction' for gesture '{event.gesture.value}'. No destructive action.")
            await ws_manager.broadcast_event(
                "character_reaction",
                {"action": "acknowledged", "gesture": event.gesture.value}
            )
            return {"status": "success", "action": action, "detail": "Safe passive acknowledgement."}

        else:
            logger.warning(f"Unmapped action '{action}'. Ignoring safely.")
            return {"status": "unhandled", "action": action}


# Global singleton action resolver
gesture_action_resolver = GestureActionResolver()
