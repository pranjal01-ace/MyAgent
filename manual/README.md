# 🔥 Portgas D. Ace AI Desktop Companion — System Manual

Welcome to the comprehensive technical documentation and system manual for **Ace_Ai** (Portgas D. Ace Desktop AI Companion).

This manual provides an exhaustive breakdown of every module, class, method, function, file path, database entity, and API endpoint in the system.

---

## 📑 Manual Directory & Contents

| Document | Description | Key Modules Covered |
| :--- | :--- | :--- |
| [**01. Architecture Overview**](file:///D:/Ace_Ai/manual/01_ARCHITECTURE.md) | Domain-driven architecture, system layers, design patterns, lifecycle flow | Entire backend, desktop & voice stack |
| [**02. Core & Common**](file:///D:/Ace_Ai/manual/02_CORE_AND_COMMON.md) | Database engine, connection pooling, automated migrations, BaseAuditModel, settings | `backend/core/`, `backend/common/` |
| [**03. Conversations Domain**](file:///D:/Ace_Ai/manual/03_CONVERSATIONS.md) | Chat service, SSE streaming, sentence-level TTS dispatch, conversation repository | `backend/conversations/` |
| [**04. Memories Domain**](file:///D:/Ace_Ai/manual/04_MEMORIES.md) | Long-term memory store, audit tracking, category filtering, repository & service | `backend/memories/` |
| [**05. Voice & Speech**](file:///D:/Ace_Ai/manual/05_VOICE_AND_SPEECH.md) | Edge-TTS with sentence streaming, instant barge-in, STT engine, VAD tuning | `backend/voice/`, `backend/speech/` |
| [**06. Cache & Vector Store**](file:///D:/Ace_Ai/manual/06_CACHE_AND_RAG.md) | Multi-tier prompt cache (exact, normalized, semantic pgvector), RAG retrieval | `backend/cache/`, `backend/memory/` |
| [**07. Desktop Tools & Security**](file:///D:/Ace_Ai/manual/07_TOOLS_AND_SECURITY.md) | Safe OS tools, regex command injection defense, path traversal jail, permissions | `backend/tools/`, `backend/agent/` |
| [**08. LLM Client & Prompts**](file:///D:/Ace_Ai/manual/08_LLM_AND_PROMPTS.md) | Ollama client, pre-warming, token streaming, Ace character persona prompts | `backend/llm/` |
| [**09. Desktop GUI & Living Avatar**](file:///D:/Ace_Ai/manual/09_DESKTOP_UI.md) | Transparent overlay window, 2D/3D sprite & GLTF renderers, animation controllers | `desktop/` |
| [**10. REST & WebSocket API Reference**](file:///D:/Ace_Ai/manual/10_API_REFERENCE.md) | Full endpoint contracts, request/response schemas, SSE event protocol | `backend/api/`, domain routers |

---

## 🚀 Quick Execution Guide

### Starting the Backend Server
```powershell
python -m backend.main
# Runs on http://localhost:8000 (Swagger docs at http://localhost:8000/docs)
```

### Launching the Desktop Companion (GUI)
```powershell
python run.py
# Or directly:
python -m desktop.window
```

### Interactive CLI Chat
```powershell
python chat_cli.py
```

### Running Automated Test Suites
```powershell
python -m pytest tests/ -v
```
