# 💬 Conversations Domain Manual

This document details the chat service, streaming token pipeline, sentence-level TTS dispatch, conversation models, repositories, and HTTP endpoints under `backend/conversations/`.

---

## 1. Conversation Model: `backend/conversations/models.py`

**File Location:** [`backend/conversations/models.py`](file:///D:/Ace_Ai/backend/conversations/models.py)

### Class: `ConversationModel(BaseAuditModel)`
Represents an individual chat turn persisted in the database table `conversations`:

```python
class ConversationModel(BaseAuditModel):
    __tablename__ = "conversations"

    session_id = Column(String(64), default="default", index=True, nullable=False)
    role = Column(String(20), nullable=False)      # 'user', 'assistant', 'system'
    content = Column(Text, nullable=False)
    metadata_json = Column(Text, default="{}", nullable=False)
```

| Field Name | Type | Purpose |
| :--- | :--- | :--- |
| `id` | `Integer` | Unique primary key (inherited from `BaseAuditModel`) |
| `session_id` | `String(64)` | Indexed session identifier enabling multi-session chat histories |
| `role` | `String(20)` | Speaker role: `"user"`, `"assistant"`, or `"system"` |
| `content` | `Text` | Full textual message or prompt turn |
| `metadata_json` | `Text` | JSON-encoded turn metadata (e.g. latency, tool logs, cache status) |
| `created_at` | `DateTime` | UTC timestamp of message creation |
| `updated_at` | `DateTime` | UTC timestamp of message update |
| `is_active` | `Boolean` | Flag supporting soft deletion |

---

## 2. Conversation Repository: `backend/conversations/repository.py`

**File Location:** [`backend/conversations/repository.py`](file:///D:/Ace_Ai/backend/conversations/repository.py)

### Class: `ConversationRepository`
Encapsulates all database interactions for chat turns:

#### Method Reference

1. **`add_message(role: str, content: str, session_id: str = "default", metadata: Optional[Dict] = None) -> ConversationModel`**
   - **Parameters:**
     - `role`: Message sender role (`"user"`, `"assistant"`, `"system"`).
     - `content`: Message text.
     - `session_id`: Session tag (defaults to `"default"`).
     - `metadata`: Optional dictionary serialized to `metadata_json`.
   - **Returns:** Created `ConversationModel` record.

2. **`get_recent_messages(session_id: str = "default", limit: int = 10) -> List[Dict[str, str]]`**
   - **Parameters:**
     - `session_id`: Session identifier.
     - `limit`: Maximum turns to return (default 10).
   - **Returns:** List of message dictionaries `[{"role": "user", "content": "..."}]` ordered chronologically (oldest to newest).

3. **`get_budgeted_messages(session_id: str = "default", max_tokens: int = 2000, avg_chars_per_token: int = 4) -> List[Dict[str, str]]`**
   - **Parameters:**
     - `session_id`: Target session.
     - `max_tokens`: Context token limit budget.
     - `avg_chars_per_token`: Approximation factor (default 4 chars/token).
   - **Returns:** Oldest-first list of messages fitting strictly within the context token budget.

4. **`clear_conversation(session_id: str = "default") -> int`**
   - **Parameters:** `session_id`.
   - **Returns:** Number of deleted message rows.

5. **`soft_delete_conversation(session_id: str = "default") -> int`**
   - **Parameters:** `session_id`.
   - **Behavior:** Sets `is_active = False` for all rows in the session, maintaining audit logs while hiding them from active context.

---

## 3. Chat Service: `backend/conversations/service.py`

**File Location:** [`backend/conversations/service.py`](file:///D:/Ace_Ai/backend/conversations/service.py)

### Class: `ChatService`
Orchestrates prompt cache validation, safe desktop tools, LLM inference, and sentence-streaming speech output:

#### Key Methods

1. **`execute_chat(message: str, session_id: str = "default", speak: bool = True) -> Dict[str, Any]`**
   - **Workflow:**
     1. Evaluates constant math expressions (e.g. `2+2`) instantly without LLM latency.
     2. Checks multi-tier cache (Exact match, Normalized prompt, Semantic embedding).
     3. Checks intent for safe desktop tools (e.g. `open_app`, `system_info`).
     4. Loads budgeted conversation context and long-term memories.
     5. Queries Ollama LLM for streaming completion.
     6. Persists query to cache and turns to `ConversationRepository`.
     7. Speaks reply asynchronously if `speak=True`.
   - **Returns:** `{ "user_message", "response", "tool_executed", "state", "cached" }`.

2. **`stream_chat(message: str, session_id: str = "default", speak: bool = True) -> AsyncGenerator[Dict[str, Any], None]`**
   - **Purpose:** Server-Sent Events (SSE) generator yielding incremental tokens as they stream from Ollama.
   - **Real-Time Sentence-Level TTS Streaming:**
     - Tracks incoming token stream using `_find_sentence_boundary(buffer)`.
     - When punctuation (`.`, `!`, `?`, `\n`) is detected and buffer exceeds 20 characters, dispatches sentence to `TTSEngine.speak(sentence, block=False)` immediately.
     - User hears speech start playing while Ollama is still generating subsequent sentences!

3. **`_find_sentence_boundary(text: str) -> Optional[int]`**
   - Scans string for natural linguistic pauses while ignoring numeric decimals (e.g. `3.14`) and honorific abbreviations (e.g. `Dr.`, `Mr.`).

4. **`_evaluate_constant_math(prompt: str) -> Optional[str]`**
   - Uses Python AST to safely compute basic math expressions without executing arbitrary code, returning an instant Ace-flavored persona answer.

---

## 4. Endpoints Reference: `backend/conversations/router.py`

**File Location:** [`backend/conversations/router.py`](file:///D:/Ace_Ai/backend/conversations/router.py)

| Method | Endpoint | Request Body | Response | Description |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/chat` | `ChatRequest` | `ChatResponse` | Single-turn synchronous chat execution |
| `POST` | `/api/chat/stream` | `ChatRequest` | SSE Stream | Real-time token streaming with sentence-level TTS |
| `GET` | `/api/chat/history` | Query params | `{"session_id", "messages", "count"}` | Retrieve recent messages for session |
| `DELETE` | `/api/chat/history` | Query params | `{"success", "deleted_count"}` | Clear session chat turns |
| `GET` | `/api/conversations` | Query params | `{"messages": [...]}` | Legacy endpoint for history |
| `POST` | `/api/conversations/clear` | Query params | `{"status", "message"}` | Legacy endpoint to clear history |
