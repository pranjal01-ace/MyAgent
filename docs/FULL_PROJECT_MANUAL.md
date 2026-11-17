# 🔥 Portgas D. Ace AI Desktop Companion — Full Project Manual

> **All-in-One Comprehensive Technical Reference**  
> Covers every file, module, class, function, parameter, and API endpoint across the entire `Ace_Ai` repository.

---

## 📑 Master Table of Contents
1. [Architecture & Topology](#1-architecture--topology)
2. [Root Scripts & Entrypoints](#2-root-scripts--entrypoints)
3. [Backend Core & Common (`backend/core/`, `backend/common/`)](#3-backend-core--common)
4. [Conversations Domain (`backend/conversations/`)](#4-conversations-domain)
5. [Memories Domain (`backend/memories/`)](#5-memories-domain)
6. [Voice & Speech Subsystem (`backend/voice/`, `backend/speech/`)](#6-voice--speech-subsystem)
7. [Multi-Tier Cache & Vector RAG (`backend/cache/`, `backend/memory/`)](#7-multi-tier-cache--vector-rag)
8. [Desktop Tools & Security Guardrails (`backend/tools/`, `backend/agent/`)](#8-desktop-tools--security-guardrails)
9. [LLM Client & Ace Persona (`backend/llm/`)](#9-llm-client--ace-persona)
10. [Master Application & APIs (`backend/main.py`, `backend/api/`)](#10-master-application--apis)
11. [Desktop GUI & Living Avatar (`desktop/`)](#11-desktop-gui--living-avatar)
12. [Voice Assistant Subsystem (`voice_assistant/`)](#12-voice-assistant-subsystem)

---

## 1. Architecture & Topology

The project is structured as a **Domain-Driven Architecture (DDD)** with layered separation:
- **Presentation Layer**: Transparent PyQt5 desktop GUI overlay (`desktop/`), CLI (`chat_cli.py`), and REST/WebSocket API (`backend/api/`, domain routers).
- **Service Layer**: Business workflows, sentence-level streaming TTS, intent detection, and cache resolution (`service.py`).
- **Repository Layer**: Isolated database queries, transactions, and token budgeting (`repository.py`).
- **Persistence Layer**: PostgreSQL with `pgvector` HNSW indexing (fallback to SQLite at `data/agent.db`).
- **External Interfaces**: Local Ollama LLM (`mistral`), Microsoft Edge-TTS neural voices, Windows SAPI5, and OS desktop automation.

```
D:\Ace_Ai\
├── backend/            # Clean DDD backend API, services, repositories, models
├── desktop/            # Transparent always-on-top PyQt5 avatar GUI & 2D/3D renderers
├── voice_assistant/    # Standalone voice agent & RAG document ingestion pipeline
├── test_bench/         # Diagnostic test suites (Tests 1-184)
├── tests/              # 43 automated regression pytest cases
└── docs/               # System documentation & manuals
```

---

## 2. Root Scripts & Entrypoints

### [`run.py`](file:///D:/Ace_Ai/run.py)
- **Role**: Primary launcher for the desktop application.
- **Workflow**: Launches the FastAPI server in a background thread/process if not already running, verifies Ollama availability, and initializes the PyQt5 `MainWindow`.

### [`chat_cli.py`](file:///D:/Ace_Ai/chat_cli.py)
- **Role**: Terminal-based interactive conversation client.
- **Features**: ANSI color-coded Ace persona replies, dynamic token budgeting, session management, and instant command-line query execution against `ChatService`.

### [`conftest.py`](file:///D:/Ace_Ai/conftest.py)
- **Role**: Global test configuration for pytest.
- **Fixtures**: Configures mock test database engines, test client sessions, and isolates unit test data from production databases.

---

## 3. Backend Core & Common

### [`backend/core/config.py`](file:///D:/Ace_Ai/backend/core/config.py)
- **Class `Settings(BaseSettings)`**: Centralized configuration management parsed from `.env` via Pydantic.
  - `API_HOST: str = "0.0.0.0"`: API server binding interface.
  - `API_PORT: int = 8000`: API port.
  - `DATABASE_URL: str`: PostgreSQL connection string (fallback: SQLite `sqlite:///data/agent.db`).
  - `OLLAMA_URL: str = "http://localhost:11434"`: Ollama daemon address.
  - `OLLAMA_MODEL: str = "mistral"`: Default LLM model name.
  - `TTS_ENGINE: str = "edge"`: Speech backend (`"edge"` or `"sapi5"`).
  - `TTS_VOICE: str = "en-US-ChristopherNeural"`: Edge-TTS natural voice voice tag.
  - `VAD_MIN_SILENCE_DURATION: float = 0.4`: Voice Activity Detection pause threshold.
  - `WORKSPACE_ROOT: Path`: Confined workspace directory path for safe file tools.
- **Exports**: `settings = Settings()`, `BASE_DIR = Path(...)`.

### [`backend/core/database.py`](file:///D:/Ace_Ai/backend/core/database.py)
- **Functions**:
  - `create_db_engine() -> Engine`: Instantiates SQLAlchemy engine with connection pooling (`pool_size=15`, `max_overflow=25`, `pool_timeout=15`, `pool_recycle=1800`, `pool_pre_ping=True`). Auto-creates PostgreSQL database catalog if missing; falls back to SQLite if PostgreSQL is unavailable.
  - `get_db() -> Generator[Session, None, None]`: FastAPI dependency yielding thread-local `SessionLocal` with deterministic cleanup.
  - `init_db() -> None`: Creates missing tables on `Base.metadata`. Executes non-destructive schema migrations (`ALTER TABLE ... ADD COLUMN IF NOT EXISTS updated_at, is_active`) and registers PL/pgSQL vector functions (`cosine_similarity`, `vector_dot_product`).

### [`backend/common/models.py`](file:///D:/Ace_Ai/backend/common/models.py)
- **Class `BaseAuditModel(Base)`**: Abstract base model inherited by all database models.
  - `id: int`: Primary key with B-tree index.
  - `created_at: datetime`: UTC creation timestamp (`default=utcnow`).
  - `updated_at: datetime`: UTC last modified timestamp (`onupdate=utcnow`).
  - `is_active: bool`: Soft-deletion state flag (`default=True`).

### [`backend/common/schemas.py`](file:///D:/Ace_Ai/backend/common/schemas.py)
- **Class `BaseAuditSchema(BaseModel)`**: Pydantic V2 base schema with `model_config = ConfigDict(from_attributes=True)` exposing `id`, `created_at`, `updated_at`, and `is_active`.
- **Class `GenericResponse(BaseModel)`**: Standard JSON envelope `{ success: bool, message: str, data: Optional[Dict] }`.

### [`backend/common/exceptions.py`](file:///D:/Ace_Ai/backend/common/exceptions.py) & [`exception_handlers.py`](file:///D:/Ace_Ai/backend/common/exception_handlers.py)
- **Classes**:
  - `AppException(message, status_code=400, details=None)`: Base domain exception.
  - `EntityNotFoundError(entity_name, entity_id)`: Maps to HTTP 404.
  - `SecurityValidationError(message)`: Maps to HTTP 403 (security violations).
  - `ToolExecutionError(tool_name, error_msg)`: Maps to HTTP 500.
- **Handlers**: `app_exception_handler` formats clean JSON; `generic_exception_handler` masks unexpected internal stack traces.

---

## 4. Conversations Domain

### [`backend/conversations/models.py`](file:///D:/Ace_Ai/backend/conversations/models.py)
- **Class `ConversationModel(BaseAuditModel)`**: Table `conversations`.
  - `session_id: str`: 64-character indexed session identifier.
  - `role: str`: Sender role (`"user"`, `"assistant"`, `"system"`).
  - `content: str`: Turn message body.
  - `metadata_json: str`: Serialized turn diagnostics (latency, tool executions, cache hit info).

### [`backend/conversations/schemas.py`](file:///D:/Ace_Ai/backend/conversations/schemas.py)
- `ChatRequest(message: str, speak: bool = True, session_id: str = "default")`.
- `ChatResponse(user_message: str, response: str, tool_executed: Optional[str], state: str, cached: bool)`.
- `StreamEventSchema`: Defines Server-Sent Events fields (`type`, `content`, `done`, etc.).

### [`backend/conversations/repository.py`](file:///D:/Ace_Ai/backend/conversations/repository.py)
- **Class `ConversationRepository`**:
  - `add_message(role, content, session_id="default", metadata=None) -> ConversationModel`: Appends a chat turn.
  - `get_recent_messages(session_id="default", limit=10) -> List[Dict]`: Chronologically ordered turns.
  - `get_budgeted_messages(session_id="default", max_tokens=2000, avg_chars_per_token=4) -> List[Dict]`: Prunes oldest turns to fit within context token window.
  - `clear_conversation(session_id="default") -> int`: Deletes session history rows.
  - `soft_delete_conversation(session_id="default") -> int`: Sets `is_active=False` for audit retention.

### [`backend/conversations/service.py`](file:///D:/Ace_Ai/backend/conversations/service.py)
- **Class `ChatService`**:
  - `execute_chat(message, session_id, speak) -> Dict`: Full turn orchestrator: AST instant math calculation -> Multi-tier cache lookup -> Safe tool intent check -> Budgeted context assembly -> Ollama generation -> Cache persistence -> Asynchronous TTS playback.
  - `stream_chat(message, session_id, speak) -> AsyncGenerator[Dict, None]`: Real-time SSE token stream. Uses `_find_sentence_boundary()` to detect complete linguistic sentences (`.`, `!`, `?`, `\n`) and dispatches audio to `TTSEngine.speak(block=False)` while the LLM is still generating!
  - `_evaluate_constant_math(prompt: str) -> Optional[str]`: Evaluates basic arithmetic via Python AST instantly without LLM latency.

### [`backend/conversations/router.py`](file:///D:/Ace_Ai/backend/conversations/router.py)
- `POST /api/chat`: Single-turn synchronous chat endpoint.
- `POST /api/chat/stream`: Server-Sent Events (SSE) token stream with sentence-streaming audio.
- `GET /api/chat/history`: Retrieves recent messages for a session.
- `DELETE /api/chat/history`: Purges message history for a session.
- `GET /api/conversations`: Backward-compatibility endpoint.
- `POST /api/conversations/clear`: Backward-compatibility endpoint.

---

## 5. Memories Domain

### [`backend/memories/models.py`](file:///D:/Ace_Ai/backend/memories/models.py)
- **Class `MemoryModel(BaseAuditModel)`**: Table `memories`.
  - `key: str`: Unique indexed title/slug (e.g. `"user_name"`, `"birthday"`).
  - `value: str`: Memory fact text.
  - `category: str`: Tag (e.g. `"user_info"`, `"preferences"`).

### [`backend/memories/schemas.py`](file:///D:/Ace_Ai/backend/memories/schemas.py)
- `MemoryCreateSchema(key: str, value: str, category: Optional[str] = "general")`.
- `MemoryUpdateSchema(value: Optional[str], category: Optional[str])`.
- `MemoryResponseSchema(BaseAuditSchema)`: Serializes memory with audit timestamps.

### [`backend/memories/repository.py`](file:///D:/Ace_Ai/backend/memories/repository.py)
- **Class `MemoryRepository`**:
  - `upsert_memory(key, value, category="general") -> MemoryModel`: Updates existing memory and triggers `updated_at`, or inserts new record.
  - `get_by_key(key) -> Optional[MemoryModel]`: Fetches single active memory.
  - `get_all(category=None) -> List[MemoryModel]`: Retrieves all active memories.
  - `get_detailed() -> List[Dict]`: Retrieves memories formatted with ISO timestamps.
  - `delete_by_key(key) -> bool`: Soft or hard deletes memory by key.
  - `count(category=None) -> int`: Returns active count.

### [`backend/memories/service.py`](file:///D:/Ace_Ai/backend/memories/service.py)
- **Class `MemoryService`**: Business validation layer; raises `EntityNotFoundError` on missing memory keys.

### [`backend/memories/router.py`](file:///D:/Ace_Ai/backend/memories/router.py)
- `GET /api/memories`: Lists all active memories.
- `GET /api/memories/detailed`: Lists memories with ISO timestamps.
- `POST /api/memories`: Creates or updates a memory.
- `GET /api/memories/{key}`: Retrieves memory by key.
- `DELETE /api/memories/{key}`: Deletes memory by key.
- `POST /api/memory`: Legacy singular endpoint route.
- `DELETE /api/memory/{key}`: Legacy singular endpoint route.

---

## 6. Voice & Speech Subsystem

### [`backend/voice/service.py`](file:///D:/Ace_Ai/backend/voice/service.py) & [`backend/speech/tts_engine.py`](file:///D:/Ace_Ai/backend/speech/tts_engine.py)
- **Class `TTSEngine`**:
  - **Edge-TTS Backend**: Synthesizes high-definition neural speech (`en-US-ChristopherNeural`).
  - **SAPI5 Fallback**: Offline Windows TTS engine (`pyttsx3`) used automatically if network drops.
  - **Audio Playback**: Uses `pygame.mixer` with dedicated background playback worker.
  - **Sentence Streaming**: Dispatches sentences sequentially to eliminate voice wait latency.
  - `speak(text: str, block: bool = False) -> float`: Plays audio asynchronously. Returns duration.
  - `stop() -> None`: Instant Barge-In cancellation. Sets `_interrupted = True`, halts `pygame.mixer`, and clears temporary audio cache.
  - `is_speaking() -> bool`: Returns active playback state.

### [`backend/speech/stt_engine.py`](file:///D:/Ace_Ai/backend/speech/stt_engine.py)
- **Class `STTEngine`**:
  - Micro-speech capture via `speech_recognition` with energy threshold auto-calibration.
  - `listen_and_transcribe(timeout=5, phrase_time_limit=12) -> str`: Captures voice, transcribes to text via Whisper / Google Speech API, returns transcript string.

### [`backend/voice/router.py`](file:///D:/Ace_Ai/backend/voice/router.py)
- `POST /api/voice/speak`: Synthesizes and speaks text payload.
- `POST /api/voice/stop`: Barge-In interrupt endpoint.
- `GET /api/voice/status`: Returns `{ "is_speaking": bool }`.
- `POST /api/voice/listen`: Captures audio turn, transcribes, queries LLM, and speaks.

---

## 7. Multi-Tier Cache & Vector RAG

### [`backend/cache/models.py`](file:///D:/Ace_Ai/backend/cache/models.py)
- **Class `QueryCacheModel(BaseAuditModel)`**: Table `query_cache`.
  - `prompt_normalized: str`: Unique indexed normalized prompt.
  - `response: str`: Cached answer text.
  - `tool_executed: Optional[str]`: Tool run metadata if applicable.
  - `embedding: Optional[List[float]]`: Vector embedding for semantic similarity searches.
  - `hit_count: int`: Counter tracking hit frequency.

### [`backend/cache/repository.py`](file:///D:/Ace_Ai/backend/cache/repository.py)
- **Class `CacheRepository`**:
  - `get_by_normalized_prompt(prompt_norm) -> Optional[QueryCacheModel]`: Fast normalized lookup.
  - `save_cache_entry(prompt_norm, response, tool_executed, embedding) -> QueryCacheModel`: Upserts cache entry.
  - `increment_hit_count(entry_id) -> None`: Atomically increments hit counter.
  - `clear() -> None`: Empties cache table.

### [`backend/cache/service.py`](file:///D:/Ace_Ai/backend/cache/service.py) & [`backend/agent/cache.py`](file:///D:/Ace_Ai/backend/agent/cache.py)
- **Class `ResponseCacheService`**:
  - **Tier 1 (Exact)**: Matches identical raw prompt string (`<1ms`).
  - **Tier 2 (Normalized)**: Lowercases, strips punctuation, normalizes whitespace (`<3ms`).
  - **Tier 3 (Semantic)**: Computes embedding vector via Ollama and calculates cosine similarity across stored query embeddings. Matches if cosine similarity $\ge 0.90$.

### [`backend/memory/vector_store.py`](file:///D:/Ace_Ai/backend/memory/vector_store.py)
- **Class `PostgresVectorStore`**:
  - PostgreSQL `pgvector` nearest-neighbor search with HNSW indexing for RAG documents.
  - `add_documents(texts, metadatas) -> List[str]`: Batch ingestion.
  - `similarity_search(query, k=4) -> List[Dict]`: Top-$k$ context chunk retrieval.
  - **Failover**: Gracefully switches to Qdrant or in-memory vector indexing if PostgreSQL extension is absent.

---

## 8. Desktop Tools & Security Guardrails

### [`backend/agent/tools.py`](file:///D:/Ace_Ai/backend/agent/tools.py) & [`backend/tools/helpers.py`](file:///D:/Ace_Ai/backend/tools/helpers.py)
- **Safe Desktop OS Tools**:
  - `open_application(app_name: str) -> str`: Launches approved desktop apps (`notepad`, `calc`, `chrome`, etc.).
  - `create_file(path: str, content: str) -> str`: Confined workspace file creation.
  - `read_file(path: str) -> str`: Confined workspace file reading (max 50KB).
  - `list_files(directory: str) -> str`: Directory listing within workspace.
  - `get_system_info() -> str`: OS, architecture, hostname details.
  - `get_current_time() -> str`: Local formatted date and time.
- **Security Defenses**:
  - `resolve_workspace_path(path) -> Path`: Traversal jail rejecting `../`, absolute drives, or symlinks.
  - **Command Injection Guard**: Regex blocking metacharacters (`&`, `|`, `;`, `` ` ``, `$()`, `>`, `<`).
  - Vetted binary launching via `subprocess.Popen([binary_path])` without shell expansion (`shell=False`).

### [`backend/agent/agent.py`](file:///D:/Ace_Ai/backend/agent/agent.py) & [`permissions.py`](file:///D:/Ace_Ai/backend/agent/permissions.py)
- **Class `AgentRouter`**: `check_intent(prompt)` classifies intent and maps to safe tools.
- **Class `PermissionManager`**: Evaluates permissions (`PermissionLevel.AUTO`, `ASK`, `DENY`).

---

## 9. LLM Client & Ace Persona

### [`backend/llm/ollama_client.py`](file:///D:/Ace_Ai/backend/llm/ollama_client.py)
- **Class `OllamaClient`**:
  - `check_connection() -> bool`: Verifies Ollama availability.
  - `warmup() -> None`: Background startup task sending a dummy token prompt to load LLM weights into GPU memory, eliminating cold-start delay.
  - `chat_stream(messages, memories) -> AsyncGenerator[str, None]`: Streams tokens asynchronously from Ollama `/api/chat`.
  - `generate(prompt) -> str`: Synchronous text generation.
  - `embed(text) -> List[float]`: Generates embedding vectors via Ollama.

### [`backend/llm/prompts.py`](file:///D:/Ace_Ai/backend/llm/prompts.py)
- Injects One Piece character persona:
  - **Character**: Portgas D. Ace, Commander of the Whitebeard Pirates 2nd Division, Mera Mera no Mi user.
  - **Style**: Confident, spirited, polite, warm, protective older brother of Luffy.
  - **Context**: Injects long-term user facts, tool results, and history window into the system prompt.

---

## 10. Master Application & APIs

### [`backend/main.py`](file:///D:/Ace_Ai/backend/main.py)
- Instantiates FastAPI `app`, CORS middleware, exception handlers, and mounts:
  - `health.router` on `/api`
  - `conversations_router` on `/api`
  - `memories_router` and `memory_alias_router` on `/api`
  - `voice_router` on `/api`
  - `websocket.router` on `/`
- Startup event runs `init_db()` and triggers background `ollama_client.warmup()`.

### [`backend/api/health.py`](file:///D:/Ace_Ai/backend/api/health.py)
- `GET /api/health`: Returns system status and Ollama connection state.

### [`backend/api/websocket.py`](file:///D:/Ace_Ai/backend/api/websocket.py)
- `WebSocket /ws`: Real-time bidirectional state synchronization between GUI and backend.

---

## 11. Desktop GUI & Living Avatar

### [`desktop/window.py`](file:///D:/Ace_Ai/desktop/window.py)
- **Class `MainWindow(QMainWindow)`**:
  - Frameless (`FramelessWindowHint`), always-on-top (`WindowStaysOnTopHint`), transparent background (`WA_TranslucentBackground`).
  - Mouse dragging system, tray icon integration, and right-click context menu.

### [`desktop/living_character.py`](file:///D:/Ace_Ai/desktop/living_character.py)
- **Class `LivingCharacterWidget(QWidget)`**:
  - Physics-driven idle breathing and floating.
  - Gaze tracking: eyes follow screen mouse cursor within clamped bounding limits.
  - Dynamic blinking timer (3-6s intervals) and mouth lip-sync during audio playback.

### [`desktop/chat_drawer.py`](file:///D:/Ace_Ai/desktop/chat_drawer.py)
- **Class `ChatDrawerWidget(QFrame)`**:
  - Slide-out glassmorphism chat panel.
  - Markdown syntax highlighting for code blocks.
  - Audio recording toggle and instant barge-in interrupt button.

### [`desktop/character_manager.py`](file:///D:/Ace_Ai/desktop/character_manager.py)
- **Class `CharacterManager`**: Reads character manifest configs (`character.json`) to switch between avatars (Ace, Luffy, etc.).

### [`desktop/character_renderer.py`](file:///D:/Ace_Ai/desktop/character_renderer.py) & [`renderer_3d.py`](file:///D:/Ace_Ai/desktop/renderer_3d.py)
- Dual 2D Sprite (QPainter) and 3D GLTF (OpenGL / QtQuick3D) rendering engines.

### [`desktop/audio_worker.py`](file:///D:/Ace_Ai/desktop/audio_worker.py)
- **Class `AudioWorker(QThread)`**: Decouples voice playback and mic capture from the GUI event loop to ensure 60 FPS animation smoothness.

### [`desktop/avatar.py`](file:///D:/Ace_Ai/desktop/avatar.py)
- **Class `AvatarWidget(QWidget)`**: 2D sprite state renderer with status pill badge (`IDLE`, `LISTENING`, `THINKING`, `SPEAKING`).

### [`desktop/memory_viewer.py`](file:///D:/Ace_Ai/desktop/memory_viewer.py)
- **Class `MemoryViewerDialog(QDialog)`**: Dark-themed GUI table enabling users to inspect, add, or delete long-term companion memories.

### [`desktop/task_panel.py`](file:///D:/Ace_Ai/desktop/task_panel.py)
- **Class `AgentTaskPanel(QFrame)`**: Floating transparency panel displaying step-by-step tool execution progress and emergency task abort.

---

## 12. Voice Assistant Subsystem

### [`voice_assistant/app.py`](file:///D:/Ace_Ai/voice_assistant/app.py)
- Standalone CLI voice agent with automated hardware startup diagnostics (`perform_startup_checks`) checking Microphone, Ollama, Qdrant, STT, and TTS.

### [`voice_assistant/config.py`](file:///D:/Ace_Ai/voice_assistant/config.py)
- Independent environment configuration for the standalone voice assistant subsystem.

### [`voice_assistant/ingest.py`](file:///D:/Ace_Ai/voice_assistant/ingest.py)
- Multi-format RAG document ingestion pipeline:
  - Supports `.txt`, `.md`, `.pdf`, `.docx`.
  - Uses `RecursiveTextChunker` (500-char chunks, 50-char overlap).
  - Generates embeddings via `OllamaEmbeddingGenerator` (`nomic-embed-text`).
  - Ingests into `UnifiedVectorStore` (PostgreSQL / Qdrant).
