# 🏛️ Architecture & System Blueprint

This document details the architectural principles, domain decomposition, design patterns, and request lifecycle of the **Ace_Ai** system.

---

## 1. Domain-Driven Design (DDD) Overview

The backend is structured into clear, decoupled domain packages under `backend/`. Each domain encapsulates its own models, schemas, repositories, services, and HTTP routers:

```mermaid
graph TD
    Client[Desktop App / Web / CLI] -->|HTTP / WebSocket| Routers[Domain Routers]
    Routers --> Services[Domain Services]
    Services --> Repositories[Domain Repositories]
    Repositories --> Database[(PostgreSQL / SQLite)]
    Services --> External[Ollama LLM / Edge-TTS / System OS]
    
    subgraph "Domain Modules"
        C[conversations]
        M[memories]
        V[voice]
        K[cache]
        T[tools]
    end
```

### Domain Module Structure
Each domain module contains:
- **`models.py`**: SQLAlchemy database entities inheriting from `BaseAuditModel` (`id`, `created_at`, `updated_at`, `is_active`).
- **`schemas.py`**: Pydantic models for request validation, response serialization, and DTO contracts.
- **`repository.py`**: Data access layer isolating database queries, transactions, and filters.
- **`service.py`**: Pure business logic orchestrating repositories, LLM streaming, audio synthesis, and tools.
- **`router.py`**: FastAPI endpoints binding HTTP paths to domain service methods.

---

## 2. Core Architectural Patterns

### A. Repository Pattern
Data queries are completely decoupled from business logic and controllers.
- `ConversationRepository` manages message turns and token budgeting.
- `MemoryRepository` manages long-term facts, preferences, and categories.
- `CacheRepository` manages exact and normalized prompt query cache entries.

### B. Service Layer Pattern
Encapsulates application workflow:
- `ChatService` handles multi-tier cache evaluation, intent detection, Ollama streaming, and real-time sentence-level TTS dispatch.
- `MemoryService` coordinates validation and persistence of memory records.
- `TTSEngine` provides non-blocking audio generation with instant barge-in cancellation.

### C. Base Audit Pattern (`BaseAuditModel`)
Every database entity derives from `BaseAuditModel` in [`backend/common/models.py`](file:///D:/Ace_Ai/backend/common/models.py):
```python
class BaseAuditModel(Base):
    __abstract__ = True
    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
```
Guarantees audit traceability across conversation messages, user preferences, and cache records.

### D. Facade Pattern for Backward Compatibility
To guarantee that existing test benches, desktop GUI (`desktop/window.py`), and CLI scripts continue working with zero modification:
- `backend/config.py` re-exports from `backend.core.config`.
- `backend/memory/database.py` re-exports models and engine from `backend.core.database`.
- `backend/memory/conversation.py` re-exports methods delegating to repositories.
- `backend/speech/tts_engine.py` re-exports the singleton from `backend.voice.service`.

---

## 3. End-to-End Chat Turn Lifecycle

When a user submits a prompt via desktop chat drawer, voice mic, or REST API:

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Router as Conversations Router
    participant Service as ChatService
    participant Cache as ResponseCacheService
    participant Tool as AgentRouter
    participant LLM as OllamaClient
    participant Voice as TTSEngine
    participant DB as ConversationRepository

    User->>Router: POST /api/chat (or /api/chat/stream)
    Router->>Service: execute_chat(message, session_id, speak)
    Service->>Cache: check_cache(message)
    alt Cache Hit (Exact / Normalized / Semantic)
        Cache-->>Service: Return cached reply
    else Cache Miss
        Service->>Tool: check_intent(message)
        opt Intent Detected
            Tool->>Tool: execute_safe_tool(tool_name, args)
            Tool-->>Service: Tool result injected as system prompt
        end
        Service->>LLM: chat_stream(messages, memories)
        loop Token Stream & Sentence Chunking
            LLM-->>Service: Stream tokens
            opt Sentence Boundary Found (. ! ? \n)
                Service->>Voice: speak(sentence, block=False)
            end
        end
        Service->>Cache: save_cache_entry(message, full_response)
    end
    Service->>DB: add_message(user & assistant turns)
    Service-->>Router: Final Response & metadata
    Router-->>User: JSON Response / SSE Stream Done
```
