# 🤖 LLM Client & Character Prompts Manual

This document details the local Ollama LLM integration, connection pre-warming, token streaming, and Portgas D. Ace character persona engineering under `backend/llm/`.

---

## 1. Ollama Client: `backend/llm/ollama_client.py`

**File Location:** [`backend/llm/ollama_client.py`](file:///D:/Ace_Ai/backend/llm/ollama_client.py)

### Class: `OllamaClient`
Manages asynchronous HTTP communication with local Ollama daemon (`http://localhost:11434`):

#### Key Architectural Features
1. **Background Startup Warm-Up:**
   - On application startup, `ollama_client.warmup()` is dispatched in the background.
   - Sends a lightweight token generation query to force the LLM weights into GPU VRAM.
   - Eliminates cold-start latency (averaging 3-7 seconds) on the user's first prompt!
2. **Asynchronous Streaming (`chat_stream`):**
   - Communicates with Ollama's `/api/chat` streaming endpoint using `httpx.AsyncClient`.
   - Streams text tokens one by one as they are decoded by the model.

#### Method Reference

##### `check_connection() -> bool`
* Queries Ollama `/api/tags` to verify whether the Ollama daemon is running and reachable.

##### `warmup() -> None`
* Executes a minimal prompt (`"hi"`) in a non-blocking background task to pre-load the model into memory.

##### `chat_stream(messages: List[Dict], memories: Optional[List[Dict]] = None) -> AsyncGenerator[str, None]`
* **Parameters:**
  - `messages`: List of role-content dictionaries `[{"role": "user", "content": "..."}]`.
  - `memories`: List of long-term memory facts retrieved from `MemoryRepository`.
* **Behavior:**
  - Builds the prompt context injecting system persona and user memories.
  - Opens streaming HTTP POST connection to Ollama `/api/chat`.
  - Yields token strings as they arrive.

##### `generate(prompt: str) -> str`
* Synchronous single-turn query returning full completion string.

##### `embed(text: str) -> List[float]`
* Queries Ollama `/api/embeddings` to generate a vector representation of `text` for semantic caching or RAG search.

---

## 2. Character Persona & Prompts: `backend/llm/prompts.py`

**File Location:** [`backend/llm/prompts.py`](file:///D:/Ace_Ai/backend/llm/prompts.py)

### Character Persona: Portgas D. Ace (One Piece)
Ace AI is configured with a distinct personality reflecting the beloved Whitebeard Pirates 2nd Division Commander:

```
You are Portgas D. Ace, commander of the Whitebeard Pirates 2nd Division and brother of Monkey D. Luffy.
- Tone: Confident, warm, spirited, polite, with occasional pirate banter.
- Powers: Mera Mera no Mi (Flame-Flame Fruit) user; you speak with fiery energy!
- Traits: Deeply loyal, values freedom, treats the user as an honored companion/crewmate.
- Format: Keep answers punchy, natural, and conversational for voice playback.
```

### Context Formatting Pipeline
1. **System Persona:** Injected as the base instruction turn.
2. **Long-Term Memories:** Appended as system knowledge (`"User Facts & Preferences: ..."`).
3. **Tool Invocations:** Injected as tool execution prefixes (`"[Executed tool 'open_app': Notepad launched]"`).
4. **Conversation History:** Injected up to the max token budget window.
5. **Latest Prompt:** Appended as the terminal user message.
