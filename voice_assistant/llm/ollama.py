import json
import logging
import httpx
from typing import AsyncGenerator, List, Dict, Any, Optional
from voice_assistant.config import settings
from voice_assistant.llm.prompts import build_system_prompt

logger = logging.getLogger("assistant.llm.ollama")

class OllamaLLM:
    """Async streaming Ollama LLM provider."""

    def __init__(self, base_url: str = None, model: str = None):
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL

    async def check_health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{self.base_url}/api/tags")
                return res.status_code == 200
        except Exception as e:
            logger.warning(f"Ollama health check failed: {e}")
            return False

    async def generate_stream(
        self,
        query: str,
        rag_context: str = "",
        history: List[Dict[str, str]] = None,
        cancel_event: Optional[Any] = None
    ) -> AsyncGenerator[str, None]:
        """Stream response tokens token-by-token with cancellation support."""
        system_prompt = build_system_prompt(rag_context)
        
        messages = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": query})

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "keep_alive": "30m",
            "options": {
                "num_predict": 45,   # Fast 1-2 sentence spoken response
                "num_ctx": 512,      # Small context window for fast prompt evaluation
                "num_thread": 8,     # Multi-core CPU threading
                "temperature": 0.5
            }
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                    async for line in response.aiter_lines():
                        if cancel_event and cancel_event.is_set():
                            logger.info("Ollama LLM generation stream cancelled via event.")
                            break
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                            delta = chunk.get("message", {}).get("content", "")
                            if delta:
                                yield delta
                        except json.JSONDecodeError:
                            pass
        except Exception as e:
            logger.error(f"Error during Ollama LLM stream: {e}")
            yield f"\n[LLM error: {e}]"
