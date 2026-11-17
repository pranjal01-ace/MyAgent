import asyncio
import json
import logging
import httpx
from typing import AsyncGenerator, Dict, Any, List, Optional
from backend.config import settings
from backend.llm.prompts import get_system_prompt

logger = logging.getLogger("ace.ollama")

class OllamaClient:
    def __init__(self, base_url: str = None, model: str = None):
        self.base_url = (base_url or settings.OLLAMA_URL).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL
        self._client: Optional[httpx.AsyncClient] = None
        self._client_loop: Optional[asyncio.AbstractEventLoop] = None

    def _get_client(self) -> httpx.AsyncClient:
        """Returns a singleton, keep-alive pooled HTTP client bound to the current event loop."""
        try:
            curr_loop = asyncio.get_running_loop()
        except RuntimeError:
            curr_loop = None

        if (
            self._client is None
            or self._client.is_closed
            or self._client_loop is None
            or self._client_loop.is_closed()
            or (curr_loop is not None and self._client_loop != curr_loop)
        ):
            limits = httpx.Limits(max_keepalive_connections=10, max_connections=20, keepalive_expiry=60.0)
            timeout = httpx.Timeout(connect=30.0, read=300.0, write=30.0, pool=30.0)
            self._client = httpx.AsyncClient(limits=limits, timeout=timeout)
            self._client_loop = curr_loop
        return self._client

    async def close(self):
        """Cleanly close persistent HTTP connection pool on shutdown."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def check_connection(self) -> bool:
        """Verify that Ollama server is running and accessible."""
        try:
            client = self._get_client()
            res = await client.get(f"{self.base_url}/api/tags", timeout=5.0)
            return res.status_code == 200
        except Exception as e:
            logger.warning(f"Ollama connection check failed: {e}")
            return False

    async def warmup(self) -> bool:
        """Preload the model into GPU/VRAM to eliminate first-token cold-start latency."""
        try:
            client = self._get_client()
            payload = {
                "model": self.model,
                "keep_alive": "30m"
            }
            res = await client.post(f"{self.base_url}/api/generate", json=payload, timeout=60.0)
            if res.status_code == 200:
                logger.info(f"Ollama model '{self.model}' warmed up and preloaded into memory.")
                return True
        except Exception as e:
            logger.warning(f"Ollama warmup failed (will load on first user turn): {e}")
        return False

    async def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        memories: Optional[List[str]] = None,
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Send a chat request to Ollama with ultra-fast multithreaded generation options."""
        full_system = system_prompt or get_system_prompt(memories)
        
        formatted_messages = [{"role": "system", "content": full_system}]
        formatted_messages.extend(messages)

        payload = {
            "model": self.model,
            "messages": formatted_messages,
            "stream": False,
            "keep_alive": "30m",
            "options": {
                "num_predict": 512,
                "num_ctx": 2048,
                "num_thread": 8,
                "temperature": 0.6
            }
        }

        try:
            client = self._get_client()
            response = await client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            content = data.get("message", {}).get("content", "")
            return {"content": content, "raw": data}
        except Exception as e:
            logger.error(f"Error calling Ollama API: {e}")
            return {
                "content": f"Hey! I had trouble reaching Ollama: {e}",
                "error": str(e)
            }

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        memories: Optional[List[str]] = None
    ) -> AsyncGenerator[str, None]:
        """Stream chat tokens from Ollama chunk by chunk."""
        full_system = system_prompt or get_system_prompt(memories)
        
        formatted_messages = [{"role": "system", "content": full_system}]
        formatted_messages.extend(messages)

        payload = {
            "model": self.model,
            "messages": formatted_messages,
            "stream": True,
            "keep_alive": "30m",
            "options": {
                "num_predict": 512,
                "num_ctx": 2048,
                "num_thread": 8,
                "temperature": 0.6
            }
        }

        try:
            client = self._get_client()
            async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                if response.status_code != 200:
                    err_body = await response.aread()
                    err_str = err_body.decode("utf-8", errors="ignore")
                    logger.error(f"Ollama stream HTTP {response.status_code}: {err_str}")
                    yield f"\n[Ollama error {response.status_code}: {err_str}]"
                    return

                async for line in response.aiter_lines():
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
            self._client = None
            err_name = type(e).__name__
            err_detail = str(e)
            logger.error(f"Error in Ollama stream ({err_name}): {err_detail}", exc_info=True)
            yield f"\n[Error communicating with Ollama: {err_name} - {err_detail}]"

ollama_client = OllamaClient()

