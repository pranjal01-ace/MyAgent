import re
import time
import asyncio
import logging
import numpy as np
from typing import Optional

from voice_assistant.config import settings
from voice_assistant.core.state import StateMachine, AssistantState
from voice_assistant.core.events import LatencyTracker
from voice_assistant.audio.microphone import ContinuousMicrophone
from voice_assistant.audio.vad import SileroVAD
from voice_assistant.stt.whisper import FasterWhisperSTT
from voice_assistant.rag.retriever import RAGRetriever
from voice_assistant.llm.ollama import OllamaLLM
from voice_assistant.conversation.memory import ConversationMemory
from voice_assistant.tts.local_tts import LocalTTSProvider
from voice_assistant.tools.keyboard import KeyboardControls

from voice_assistant.audio.sound_effects import play_listening_chime, play_processing_chime

logger = logging.getLogger("assistant.core")

class VoiceAssistantOrchestrator:
    """Master orchestrator for local conversational voice assistant pipeline."""

    def __init__(self):
        self.state = StateMachine(on_state_change=self._on_state_change)
        self.telemetry = LatencyTracker()

        # Core Components
        self.mic = ContinuousMicrophone()
        self.vad = SileroVAD()
        self.stt = FasterWhisperSTT()
        self.rag = RAGRetriever()
        self.llm = OllamaLLM()
        self.memory = ConversationMemory()
        self.tts = LocalTTSProvider()

        self.keyboard = KeyboardControls(
            on_activate=self.activate,
            on_interrupt=self.interrupt,
            on_toggle_mute=self.toggle_mute
        )

        self._running = False
        self._llm_cancel_event = asyncio.Event()

    def _on_state_change(self, state: AssistantState):
        if state == AssistantState.THINKING:
            play_processing_chime()

    def activate(self):
        logger.info("Manual activation requested.")
        play_listening_chime()
        if self.state.current in [AssistantState.IDLE, AssistantState.ERROR]:
            self.state.transition_to(AssistantState.LISTENING)

    def interrupt(self):
        logger.info("Manual interruption requested.")
        self._llm_cancel_event.set()
        self.tts.stop_sync()
        self.state.transition_to(AssistantState.INTERRUPTED)

    def toggle_mute(self):
        new_mute = not self.mic.is_muted()
        self.mic.set_muted(new_mute)
        print(f"\n[MICROPHONE MUTE STATUS]: {'MUTED 🔇' if new_mute else 'UNMUTED 🎙️'}\n")

    async def start(self):
        """Start all component streams and asynchronous main pipeline loop."""
        self._running = True
        self.mic.start()
        self.keyboard.start()

        print("\n" + "=" * 50)
        print(" 🔥 LOCAL CONVERSATIONAL VOICE ASSISTANT ONLINE 🔥 ")
        print("=" * 50)
        print(f"LLM:          {settings.OLLAMA_MODEL}")
        print(f"STT:          Faster-Whisper ({settings.WHISPER_MODEL})")
        print(f"Embedding:    {settings.OLLAMA_EMBED_MODEL}")
        print(f"Vector DB:    Qdrant ({settings.QDRANT_COLLECTION})")
        print(f"TTS Voice:    {settings.TTS_VOICE}")
        print("-" * 50)
        print("Press F8 to activate. Press ESC to interrupt. Press F9 to mute.")
        print("Status: LISTENING (Continuous VAD Loop Active)\n")

        self.state.transition_to(AssistantState.LISTENING)

        try:
            await self._pipeline_loop()
        except asyncio.CancelledError:
            logger.info("Pipeline loop cancelled.")
        finally:
            self.mic.stop()

    async def _pipeline_loop(self):
        audio_buffer = []
        silence_start_time = None
        is_speaking_utterance = False
        speech_start_time = 0.0

        loop = asyncio.get_running_loop()

        while self._running:
            # 1. Fetch 32ms audio frame (512 samples) from continuous microphone
            frame = await loop.run_in_executor(None, self.mic.get_frame)
            if frame is None or len(frame) == 0:
                await asyncio.sleep(0.01)
                continue

            # 2. Silero VAD speech detection
            is_speech_frame = self.vad.is_speech(frame)
            current_state = self.state.current

            # BARGE-IN INTERRUPTION MONITORING:
            # If user starts speaking while assistant is THINKING or SPEAKING -> Interrupt immediately!
            if is_speech_frame and (current_state in [AssistantState.SPEAKING, AssistantState.THINKING] or self.tts.is_speaking()):
                logger.info("⚡ BARGE-IN DETECTED! User started speaking while assistant was active.")
                self.interrupt()
                is_speaking_utterance = True
                speech_start_time = time.time()
                audio_buffer = [frame]
                silence_start_time = None
                self.telemetry.start_turn()
                self.telemetry.mark("speech_detected")
                self.state.transition_to(AssistantState.LISTENING)
                continue

            # TURN COLLECTION & END-OF-SPEECH DETECTION
            if is_speech_frame:
                if not is_speaking_utterance:
                    # Speech started
                    is_speaking_utterance = True
                    speech_start_time = time.time()
                    audio_buffer = [frame]
                    silence_start_time = None
                    self.telemetry.start_turn()
                    self.telemetry.mark("speech_detected")
                    play_listening_chime()
                    if current_state == AssistantState.IDLE:
                        self.state.transition_to(AssistantState.LISTENING)
                else:
                    audio_buffer.append(frame)
                    silence_start_time = None
            else:
                # Silence frame
                if is_speaking_utterance:
                    audio_buffer.append(frame)
                    if silence_start_time is None:
                        silence_start_time = time.time()
                    
                    silence_duration = time.time() - silence_start_time
                    total_speech_duration = time.time() - speech_start_time

                    # End of speech condition (silence >= MIN_SILENCE_DURATION or max duration reached)
                    if silence_duration >= settings.MIN_SILENCE_DURATION or total_speech_duration >= settings.MAX_UTTERANCE_DURATION:
                        if total_speech_duration >= settings.MIN_SPEECH_DURATION:
                            self.telemetry.mark("speech_ended")
                            play_processing_chime()
                            
                            # Process utterance
                            utterance_pcm = np.concatenate(audio_buffer, axis=0)
                            
                            # Reset turn state variables
                            audio_buffer = []
                            is_speaking_utterance = False
                            silence_start_time = None
                            
                            # Process voice query asynchronously
                            asyncio.create_task(self._process_utterance(utterance_pcm))
                        else:
                            # Ignored noise burst under min speech duration
                            audio_buffer = []
                            is_speaking_utterance = False
                            silence_start_time = None
                            if self.state.current == AssistantState.LISTENING:
                                self.state.transition_to(AssistantState.IDLE)

            await asyncio.sleep(0.005)

    async def _process_utterance(self, audio_pcm: np.ndarray):
        """Asynchronously process recorded audio utterance through STT -> RAG -> Ollama -> Streaming TTS."""
        try:
            self._llm_cancel_event.clear()

            # 1. Speech-To-Text Transcription
            self.state.transition_to(AssistantState.TRANSCRIBING)
            stt_result = await self.stt.transcribe(audio_pcm)
            self.telemetry.mark("stt_completed")

            user_text = stt_result.get("text", "").strip()
            lang = stt_result.get("language", "en")
            conf = stt_result.get("confidence", 0.9)

            if not user_text:
                logger.info("STT returned empty text or filtered hallucination.")
                self.state.transition_to(AssistantState.LISTENING)
                return

            print(f"\n🎤 User [{lang} | {conf}]: {user_text}")
            self.memory.add_user_message(user_text)

            # 2. RAG Retrieval
            self.state.transition_to(AssistantState.RETRIEVING)
            rag_context, sources = await self.rag.retrieve_context(user_text)
            self.telemetry.mark("rag_completed")

            if sources:
                src_list = ", ".join(list({s.get("filename", "") for s in sources if s.get("filename")}))
                print(f"📚 RAG Context Sources: {src_list}")

            # 3. LLM Token Generation & Streaming TTS
            self.state.transition_to(AssistantState.THINKING)
            
            full_response = ""
            first_token_marked = False

            async def _token_interceptor():
                nonlocal full_response, first_token_marked
                async for token in self.llm.generate_stream(
                    query=user_text,
                    rag_context=rag_context,
                    history=self.memory.get_history()[:-1],
                    cancel_event=self._llm_cancel_event
                ):
                    if self._llm_cancel_event.is_set():
                        break
                    if not first_token_marked:
                        self.telemetry.mark("first_llm_token")
                        first_token_marked = True
                        self.state.transition_to(AssistantState.SPEAKING)

                    full_response += token
                    yield token

            # Feed streamed tokens into stateful context-aware TTS engine
            self.telemetry.mark("first_tts_audio")
            await self.tts.speak_stream(_token_interceptor(), cancel_event=self._llm_cancel_event)

            if self._llm_cancel_event.is_set():
                logger.info("Interrupted during response generation.")
                self.state.transition_to(AssistantState.INTERRUPTED)
            else:
                final_text = full_response.strip()
                if final_text:
                    print(f"🔊 Assistant: {final_text}")
                    self.memory.add_assistant_message(final_text)

                self.telemetry.print_summary()
                self.state.transition_to(AssistantState.LISTENING)

        except Exception as e:
            logger.error(f"Error processing utterance: {e}")
            self.state.transition_to(AssistantState.ERROR)
            await asyncio.sleep(1.0)
            self.state.transition_to(AssistantState.LISTENING)
