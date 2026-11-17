import sys
import asyncio
import logging
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR.parent))

from voice_assistant.config import settings
from voice_assistant.core.assistant import VoiceAssistantOrchestrator
from voice_assistant.llm.ollama import OllamaLLM
from voice_assistant.rag.vector_store import QdrantVectorStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("assistant.main")

async def perform_startup_checks() -> dict:
    """Perform startup system health checks on Microphone, Ollama, Qdrant, STT, and TTS."""
    results = {
        "microphone": False,
        "ollama": False,
        "qdrant": False,
        "stt": False,
        "tts": False
    }

    try:
        import sounddevice as sd
        devices = sd.query_devices()
        results["microphone"] = len(devices) > 0
    except Exception:
        results["microphone"] = False

    ollama = OllamaLLM()
    results["ollama"] = await ollama.check_health()

    try:
        qs = QdrantVectorStore()
        results["qdrant"] = qs.client is not None
    except Exception as e:
        logger.warning(f"Qdrant startup check warning: {e}")
        results["qdrant"] = False

    try:
        from voice_assistant.stt.whisper import FasterWhisperSTT
        stt = FasterWhisperSTT()
        results["stt"] = stt.model is not None
    except Exception:
        results["stt"] = False

    try:
        from voice_assistant.tts.local_tts import LocalTTSProvider
        tts = LocalTTSProvider()
        results["tts"] = True
    except Exception:
        results["tts"] = False

    return results

def print_startup_banner(checks: dict):
    print("\n" + "=" * 50)
    print("      LOCAL AI VOICE ASSISTANT      ")
    print("=" * 50)
    print(f"LLM:          {settings.OLLAMA_MODEL}")
    print(f"STT:          Faster-Whisper ({settings.WHISPER_MODEL})")
    print(f"Embedding:    {settings.OLLAMA_EMBED_MODEL}")
    print(f"Vector DB:    Qdrant ({settings.QDRANT_COLLECTION})")
    print("-" * 50)
    print(f"Microphone:   {'OK' if checks['microphone'] else 'FAILED (Check audio input)'}")
    print(f"Ollama:       {'OK' if checks['ollama'] else 'FAILED (Check Ollama server)'}")
    print(f"Qdrant:       {'OK' if checks['qdrant'] else 'FAILED'}")
    print(f"STT:          {'OK' if checks['stt'] else 'FAILED'}")
    print(f"TTS:          {'OK' if checks['tts'] else 'FAILED'}")
    print("-" * 50)
    print("Press F8 to activate / start listening.")
    print("Press ESC to interrupt TTS / cancel current response.")
    print("Press F9 to mute/unmute microphone.")
    print("Press CTRL+C to exit.")
    print("Status: LISTENING (Continuous Silero VAD Active)\n")

async def main():
    checks = await perform_startup_checks()
    print_startup_banner(checks)

    assistant = VoiceAssistantOrchestrator()
    try:
        await assistant.start()
    except KeyboardInterrupt:
        print("\nShutdown requested by user. Good bye!")

if __name__ == "__main__":
    asyncio.run(main())
