# 🔥 Desktop AI Mate & Voice Assistant (Portgas D. Ace & Modular Characters)

A production-grade, local-first **2D Anime AI Desktop Mate & Voice Assistant** running on your Windows laptop. Powered by **Ollama (`llama3:latest`)**, **FastAPI**, **PyQt5**, **Faster-Whisper STT**, **Edge-TTS / SAPI5**, **Instant Barge-In (Interruption)**, **SQLite Long-Term Memory**, **Agent Task Transparency Panel**, and a **Safe Desktop Tools Permission System**.

---

## 🌟 Key Features

### 1. 2D Transparent Animated Companion Overlay
- **Frameless & Draggable**: Floats seamlessly over desktop, browser, code editors, and full-screen games.
- **Dynamic Character System**: Decoupled character architecture. Easily switch between **Portgas D. Ace**, **Luna AI**, or import custom user character packages with live preview!
- **State Machine**: Visual animations matching AI cognitive states:
  - `IDLE`: Subtle bounce & breathing loop.
  - `LISTENING`: Animated mic listening indicator.
  - `THINKING`: Processing prompt or planning agent tools.
  - `SPEAKING` / `TALKING`: Mouth-moving talking animation synced with speech audio.
  - `HAPPY`, `WORKING`, `CONFUSED`, `ERROR`.
- **Speech Bubble**: Floating translucent speech bubbles appearing above the character.

### 2. Multi-Modal Interaction & Chat Drawer
- **Slide-out Chat Drawer**: Clean translucent chat panel docked next to the character with scrollable conversation history.
- **Quick Action Toolbar**:
  - `🧠 Memory`: Open SQLite Long-Term Memory Manager.
  - `⚡ Tasks`: Open Agent Task Transparency Panel.
  - `🛑 Stop`: Instant Barge-in speech cancellation.
  - `🧹 Clear`: Clear conversation history.
- **Slash Commands**:
  - `/help`: Complete guide of commands and shortcut keys.
  - `/memory`: Inspect and delete long-term user memories.
  - `/tools`: List available desktop tools.
  - `/clear`: Clear active conversation context.
  - `/voice`: Toggle continuous Voice Mode.
  - `/stop`: Stop AI speaking immediately.
  - `/settings`: Open Character Settings and Live Preview.

### 3. Voice Pipeline & Instant Barge-In
- **Continuous Voice Mode & Push-to-Talk**: Built-in Faster-Whisper / SpeechRecognition transcription with ambient noise filtering.
- **Instant Barge-In Interruption**: Press **`ESC`** or click **`Stop`** at any time to instantly cancel speech playback, clear pending audio chunks, and return the character to `IDLE`!

### 4. Agent Architecture & Safe Desktop Tools
The assistant is not just a chatbot—it safely controls your computer via a strict permission layer:
- **`get_time`**: Real-time date and clock.
- **`get_system_info`**: Live CPU, RAM, Disk usage, and Battery percentage.
- **`open_application`**: Chrome, VS Code, Notepad, Calculator, Windows Terminal, Explorer, Task Manager.
- **`open_website` / `search_web`**: Direct web navigation and search queries.
- **`take_screenshot`**: Captures screen to `data/screenshots/` without uploading anything.
- **`read_clipboard` / `write_clipboard`**: Clipboard inspection and copy.
- **`list_files` / `read_file` / `create_file` / `move_file`**: Filesystem operations restricted to safe directories.
- **`search_knowledge_base`**: RAG search across documents in `data/documents/`.
- **Permission Levels**:
  - `SAFE`: Auto-executed.
  - `CONFIRM`: File creations / modifications require approval.
  - `DANGEROUS`: Deletions / raw executions blocked by default.

### 5. Memory System
- **Short-Term Context**: Sliding window of conversation turns stored in SQLite (`data/agent.db`).
- **Long-Term Memory**: Stores user facts, preferences, and projects. Easily inspect, create, or delete memories via the UI (`/memory` or `MemoryViewerDialog`).

### 6. Configurable Personality (`config/personality.json`)
Easily customize your companion's name, personality traits, speech style, verbosity, and humor **without touching any Python code**:
```json
{
  "name": "Portgas D. Ace",
  "personality": "friendly, curious, adventurous, energetic and helpful",
  "verbosity": "medium",
  "humor": true,
  "proactive": false,
  "speech_style": "casual, direct, spirited, friendly"
}
```

---

## ⌨️ Global Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| **`ESC`** | **Barge-In / Stop Speaking Immediately** |
| **`Ctrl + Space`** | **Show / Hide Companion Window** |
| **`Ctrl + Shift + M`** | **Toggle Continuous Voice Mode** |
| **`Ctrl + Shift + A`** | **Toggle Agent Task Activity Panel** |

---

## 🚀 Getting Started

### 1. Prerequisites
- **Python 3.10+** (tested on Python 3.13)
- **Ollama** installed and running:
  ```bash
  ollama run llama3:latest
  ```

### 2. Activate Virtual Environment
```powershell
# Windows PowerShell:
.\.venv\Scripts\activate

# Windows Command Prompt (CMD):
.venv\Scripts\activate.bat
```

### 3. Launch Options

#### Option A: Full Desktop AI Mate (GUI Overlay + Backend)
```bash
python run.py
```
This automatically starts:
1. The **FastAPI Backend Server** on `http://127.0.0.1:8000`
2. The **PyQt5 Transparent Desktop Companion Overlay** (with real-time streaming chat drawer & rich code blocks)

#### Option B: Terminal Interactive Chat CLI (Code-based / Lightweight)
```bash
python chat_cli.py
```
- Real-time token streaming typewriter effect directly to console
- Rich syntax, colors, slash commands (`/help`, `/tools`, `/memory`, `/clear`, `/speak on|off`, `/exit`)
- Works in-process or against the backend without launching the GUI!

---

## 🧪 Running Automated Tests

Run the full test suite with `pytest`:
```bash
python -m pytest tests/
```

Tests include:
- `tests/test_tools.py`: Unit tests for all agent tools and permission validations.
- `tests/test_memory_api.py`: Tests for SQLite conversation history and long-term memory operations.
- `tests/test_api_endpoints.py`: Integration tests for FastAPI REST endpoints (`/api/health`, `/api/chat`, `/api/voice/stop`, `/api/memories`).

---

## 📁 Repository Structure

```
D:/Ace_Ai/
│
├── run.py                     # Master launcher (FastAPI + PyQt5 Overlay)
├── requirements.txt           # Python dependencies
├── .env                       # App settings & SQLite database path
├── .env.example               # Template environment configuration
│
├── config/
│   ├── personality.json       # No-code companion personality configuration
│   ├── active_character.json  # Current active character selection
│   └── desktop_position.json  # Saved window desktop coordinates
│
├── characters/
│   ├── ace/                   # Portgas D. Ace assets & character.json
│   └── luna/                  # Luna AI assets & character.json
│
├── backend/
│   ├── main.py                # FastAPI server initialization
│   ├── config.py              # Settings loader
│   ├── llm/
│   │   ├── ollama_client.py   # Async streaming Ollama client
│   │   └── prompts.py         # System prompt dynamically reading personality.json
│   ├── memory/
│   │   ├── database.py        # SQLite database connection & auto init
│   │   └── conversation.py    # Short-term & long-term memory functions
│   ├── speech/
│   │   ├── stt_engine.py      # Faster-Whisper microphone transcription
│   │   └── tts_engine.py      # Edge-TTS / SAPI5 with instant barge-in stop()
│   ├── agent/
│   │   ├── agent.py           # Natural language & JSON tool router
│   │   ├── tools.py           # System, app, file, clipboard, screenshot tools
│   │   └── permissions.py     # SAFE, CONFIRM, DANGEROUS permission levels
│   └── api/
│       ├── chat.py            # POST /api/chat, memory endpoints
│       ├── voice.py           # POST /api/voice/listen, POST /api/voice/stop
│       └── health.py          # GET /api/health
│
├── desktop/
│   ├── window.py              # Main transparent overlay window & shortcuts
│   ├── character_renderer.py  # 2D frame animation renderer
│   ├── character_manager.py   # Modular character loader & validator
│   ├── character_ui.py        # Selection grid dialog, settings preview & bubble
│   ├── chat_drawer.py         # Slide-out chat drawer & slash commands
│   ├── task_panel.py          # Agent Task Transparency Panel
│   ├── memory_viewer.py       # SQLite Long-Term Memory Manager dialog
│   └── audio_worker.py        # QThread workers connecting to FastAPI
│
├── tests/
│   ├── test_tools.py          # Tool and permission unit tests
│   ├── test_memory_api.py     # Memory system unit tests
│   └── test_api_endpoints.py  # FastAPI endpoint integration tests
│
└── voice_assistant/           # Standalone continuous zero-cloud assistant
    ├── app.py                 # Standalone pipeline launcher
    ├── ingest.py              # Document ingestion for RAG
    └── ...
```
