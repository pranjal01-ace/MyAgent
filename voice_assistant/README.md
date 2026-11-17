# 🎙️ Production Local AI Voice Assistant (`voice_assistant`)

A production-grade, local-first conversational voice assistant featuring **continuous microphone streaming (`sounddevice`)**, **Silero VAD ONNX turn detection**, **Faster-Whisper STT**, **Qdrant RAG**, **Ollama LLM Token Streaming**, **Streaming Sentence TTS**, **Barge-In Interruption**, and **Latency Telemetry**.

---

## 🌟 Key Features

- **Continuous Listening & Turn Detection**: Real-time 32ms audio frame processing with Silero VAD ONNX. Automatically detects when you start and stop speaking.
- **Barge-In Interruption**: Talk while the assistant is speaking to immediately interrupt TTS and ask a new question. Press `ESC` anytime to cancel speech output.
- **Fast Local STT**: Powered by `faster-whisper` (`tiny.en` / `small` / `medium`) with beam size 1 and Voice Activity Detection (VAD) noise filtering.
- **Local RAG Vector Database**: Powered by **Qdrant** (supports local Qdrant server `http://localhost:6333` or local disk vector storage `./data/qdrant`). Parses `.txt`, `.md`, `.pdf`, `.docx`.
- **Ollama Streaming LLM**: Connects to local Ollama (`qwen3:8b`, `llama3:latest`, etc.) with streaming token delivery and sliding-window conversation memory.
- **Streaming Sentence TTS**: Synthesizes and plays sentence chunks in real time as Ollama generates tokens.
- **Multi-Lingual Support**: Understands and responds in English, Hindi, and Hinglish.

---

## 🚀 Quick Start Guide (Windows)

### 1. Installation
Initialize virtual environment and install requirements:
```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r voice_assistant/requirements.txt
```

### 2. Ollama Setup & Model Pulls
Ensure **Ollama** is running locally (`http://localhost:11434`):
```bash
# Pull LLM model
ollama pull llama3:latest

# Pull Embedding model for RAG
ollama pull nomic-embed-text
```

### 3. Ingest Documents into RAG Vector DB
Ingest knowledge base documents from `voice_assistant/data/documents/`:
```powershell
.\.venv\Scripts\python.exe voice_assistant/ingest.py --path voice_assistant/data/documents
```

### 4. Run the Voice Assistant
```powershell
.\.venv\Scripts\python.exe voice_assistant/app.py
```

---

## ⌨️ Controls & Hotkeys

- **`F8`**: Activate assistant / start listening loop
- **`ESC`**: Interrupt TTS speech / cancel current generation
- **`F9`**: Mute / unmute microphone
- **`CTRL+C`**: Exit application

---

## ⚙️ Environment Configuration (`.env`)

```ini
# Ollama Configuration
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3:latest
OLLAMA_EMBED_MODEL=nomic-embed-text

# Qdrant Vector DB
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=knowledge
QDRANT_STORAGE_PATH=./data/qdrant

# STT (Faster-Whisper)
WHISPER_MODEL=tiny.en
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
STT_LANGUAGE=auto

# Silero VAD Parameters
VAD_THRESHOLD=0.5
MIN_SPEECH_DURATION=0.25
MIN_SILENCE_DURATION=0.6
MAX_UTTERANCE_DURATION=30.0

# RAG & Memory
RAG_TOP_K=5
CHUNK_SIZE=800
CHUNK_OVERLAP=150
MAX_HISTORY_MESSAGES=20

# TTS
TTS_VOICE=en-US-GuyNeural
TTS_SPEED=1.0
```

---

## 📁 Directory Structure

```
voice_assistant/
│
├── app.py                 # Application entry point & health checks
├── ingest.py              # CLI document ingestion tool for Qdrant
├── config.py              # Application settings loader (.env)
├── requirements.txt       # Dependencies
├── .env.example           # Environment template
├── README.md              # Documentation
│
├── audio/
│   ├── microphone.py      # Sounddevice continuous ring-buffer stream
│   ├── vad.py             # Silero VAD ONNX engine
│   └── audio_utils.py     # PCM normalization utilities
│
├── stt/
│   ├── base.py            # Abstract STT provider interface
│   └── whisper.py         # Faster-Whisper local provider
│
├── llm/
│   ├── ollama.py          # Async streaming Ollama LLM provider
│   └── prompts.py         # System prompt framing & RAG incorporation
│
├── rag/
│   ├── document_loader.py # Document parsers (.txt, .md, .pdf, .docx)
│   ├── chunker.py         # Recursive text chunker
│   ├── embeddings.py      # Ollama embedding generator
│   ├── vector_store.py    # Qdrant vector database store
│   └── retriever.py       # Similarity retriever
│
├── tts/
│   ├── base.py            # Abstract TTS provider interface
│   └── local_tts.py       # Streaming local TTS with barge-in cancellation
│
├── conversation/
│   └── memory.py          # Sliding-window memory manager
│
├── core/
│   ├── assistant.py       # Master pipeline orchestrator
│   ├── state.py           # State machine
│   └── events.py          # Latency telemetry tracker
│
├── tools/
│   └── keyboard.py        # Global hotkey listener
│
├── data/
│   ├── documents/         # RAG source documents
│   ├── qdrant/            # Local Qdrant vector storage
│   └── audio/             # Temporary speech audio
│
└── tests/
    ├── test_vad.py        # VAD tests
    ├── test_memory.py     # Conversation memory tests
    └── test_rag.py        # RAG chunker tests
```

---

## 🧪 Running Tests

```powershell
.\.venv\Scripts\pytest.exe voice_assistant/tests/
```
