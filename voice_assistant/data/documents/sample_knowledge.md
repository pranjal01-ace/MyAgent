# Local Voice Assistant Knowledge Base

## Overview
This local AI Voice Assistant is built with an ultra-low latency architecture.
It runs completely locally without requiring external cloud APIs or uploading private data to third-party servers.

## Core Features
1. **Audio Streaming**: Uses continuous `sounddevice` ring-buffer PCM audio input at 16kHz sample rate.
2. **Silero VAD**: Real-time ONNX Voice Activity Detection for instant turn detection and speech start/end classification.
3. **Faster-Whisper STT**: Low-latency quantized local speech-to-text supporting English, Hindi, and Hinglish.
4. **Qdrant Vector RAG**: High-performance local vector similarity search retrieving private knowledge base context.
5. **Ollama LLM Streaming**: Real-time token-by-token generation with sliding-window conversation memory.
6. **Barge-In Interruption**: Instantly stops TTS speech output when the user starts speaking or presses the ESC hotkey.

## Deployment Guidelines
- Step 1: Clone the repository and initialize python virtual environment.
- Step 2: Ingest knowledge documents using `python ingest.py --path data/documents`.
- Step 3: Run the local voice assistant using `python app.py`.
