# 🌐 REST & WebSocket API Reference Manual

Complete technical specification of all HTTP endpoints and WebSocket channels exposed by the **Ace AI** backend (`http://localhost:8000/api`).

Interactive Swagger documentation is available at:
`http://localhost:8000/docs`

---

## 1. System Health

### `GET /api/health`
Returns system status and Ollama model connection health.

**Sample Request:**
```bash
curl -X GET http://localhost:8000/api/health
```

**Sample Response (200 OK):**
```json
{
  "status": "online",
  "character": "Portgas D. Ace",
  "ollama_connected": true,
  "ollama_model": "mistral"
}
```

---

## 2. Chat & Conversations

### `POST /api/chat`
Execute a single-turn synchronous conversation prompt.

**Request Body (`application/json`):**
```json
{
  "message": "Who is your captain?",
  "session_id": "default",
  "speak": true
}
```

**Sample Response (200 OK):**
```json
{
  "user_message": "Who is your captain?",
  "response": "My captain is the greatest man on the seas — Edward Newgate, Pops Whitebeard!",
  "tool_executed": null,
  "state": "idle",
  "cached": false
}
```

---

### `POST /api/chat/stream`
Server-Sent Events (SSE) token stream with real-time sentence-level TTS.

**Request Body (`application/json`):**
```json
{
  "message": "Explain how Devil Fruits work.",
  "session_id": "default",
  "speak": true
}
```

**Response Format (`text/event-stream`):**
```
data: {"type": "start", "user_message": "Explain how Devil Fruits work."}

data: {"type": "token", "content": "Devil "}

data: {"type": "token", "content": "Fruits "}

...

data: {"type": "done", "response": "Devil Fruits grant incredible powers at the cost of being cursed by the sea!", "state": "idle"}
```

---

### `GET /api/chat/history`
Retrieve chronologically ordered message turns for a session.

**Query Parameters:**
- `session_id` (string, default `"default"`): Session tag.
- `limit` (integer, default `20`, max `100`): Message turn count.

**Sample Response (200 OK):**
```json
{
  "session_id": "default",
  "count": 2,
  "messages": [
    {"role": "user", "content": "Hello Ace!"},
    {"role": "assistant", "content": "Yo! What's up, crewmate?"}
  ]
}
```

---

### `DELETE /api/chat/history`
Clear all stored turns for a specific session.

**Query Parameters:**
- `session_id` (string, default `"default"`).

**Sample Response (200 OK):**
```json
{
  "success": true,
  "session_id": "default",
  "deleted_count": 4
}
```

---

## 3. Long-Term Memories

### `GET /api/memories`
List all active long-term memories, optionally filtered by category.

**Query Parameters:**
- `category` (optional string): e.g. `"user_info"`, `"preferences"`.

**Sample Response (200 OK):**
```json
[
  {
    "id": 1,
    "key": "user_name",
    "value": "Chetanya",
    "category": "user_info",
    "created_at": "2026-09-20T08:00:00Z",
    "updated_at": "2026-09-20T08:00:00Z",
    "is_active": true
  }
]
```

---

### `GET /api/memories/detailed`
List all active memories with ISO audit timestamps.

**Sample Response (200 OK):**
```json
{
  "count": 1,
  "memories": [
    {
      "id": 1,
      "key": "user_name",
      "value": "Chetanya",
      "category": "user_info",
      "created_at": "2026-09-20T08:00:00Z",
      "updated_at": "2026-09-20T08:00:00Z"
    }
  ]
}
```

---

### `POST /api/memories`
Create or update a long-term memory fact.

**Request Body (`application/json`):**
```json
{
  "key": "favorite_food",
  "value": "Roast meat",
  "category": "preferences"
}
```

**Sample Response (201 Created):**
```json
{
  "id": 2,
  "key": "favorite_food",
  "value": "Roast meat",
  "category": "preferences",
  "created_at": "2026-09-20T08:05:00Z",
  "updated_at": "2026-09-20T08:05:00Z",
  "is_active": true
}
```

---

### `DELETE /api/memories/{key}`
Delete a long-term memory by key.

**Sample Response (200 OK):**
```json
{
  "success": true,
  "message": "Memory 'favorite_food' deleted successfully."
}
```

---

## 4. Speech & Voice

### `POST /api/voice/speak`
Synthesize text to speech using Edge-TTS.

**Request Body (`application/json`):**
```json
{
  "text": "Fire Fist!",
  "block": false
}
```

**Sample Response (200 OK):**
```json
{
  "status": "speaking",
  "duration": 1.2
}
```

---

### `POST /api/voice/stop`
Barge-In: immediately interrupt active audio playback and clear queued speech.

**Sample Response (200 OK):**
```json
{
  "status": "interrupted",
  "message": "Speech playback stopped instantly."
}
```

---

### `GET /api/voice/status`
Check if the avatar is currently speaking audio.

**Sample Response (200 OK):**
```json
{
  "is_speaking": false
}
```

---

### `POST /api/voice/listen`
Activate microphone, transcribe spoken words via Whisper, and execute full conversational turn.

**Sample Response (200 OK):**
```json
{
  "transcript": "What time is it?",
  "response": "It's currently 1:40 PM, crewmate!",
  "has_speech": true,
  "tool_executed": "get_current_time()",
  "state": "idle"
}
```

---

## 5. Real-Time WebSocket Channel

### `WebSocket /ws`
Provides two-way state synchronization between the desktop GUI overlay and the backend server.

**Client Connection:**
```javascript
const socket = new WebSocket("ws://localhost:8000/ws");

// Send client state ping
socket.send(JSON.stringify({ event: "state_update", state: "idle" }));

// Receive events
socket.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log("Received server event:", data);
};
```
