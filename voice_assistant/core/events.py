import time
import logging
from typing import Dict, Optional

logger = logging.getLogger("assistant.telemetry")

class LatencyTracker:
    """Tracks latency metrics across pipeline stages for performance optimization."""

    def __init__(self):
        self.t_start: Optional[float] = None
        self.timestamps: Dict[str, float] = {}

    def start_turn(self):
        self.t_start = time.time()
        self.timestamps = {"speech_detected": 0.0}

    def mark(self, stage_name: str):
        if self.t_start is None:
            self.t_start = time.time()
        
        elapsed = time.time() - self.t_start
        self.timestamps[stage_name] = elapsed
        logger.info(f"Telemetry [{stage_name}]: {elapsed:.2f}s")

    def print_summary(self):
        if not self.timestamps:
            return

        print("\n" + "=" * 40)
        print("        LATENCY TELEMETRY METRICS        ")
        print("=" * 40)
        for stage, duration in self.timestamps.items():
            formatted_stage = stage.replace("_", " ").title()
            print(f"{formatted_stage:<22}: {duration:.2f}s")
        print("=" * 40 + "\n")
