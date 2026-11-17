import re
import json
import asyncio
import logging
from typing import AsyncGenerator, Dict, Any, Optional, Tuple

from backend.agent.agent import agent_router
from backend.agent.cache import response_cache, evaluate_constant_math
from backend.llm.ollama_client import ollama_client
from backend.speech.tts_engine import tts_engine
from backend.conversations.repository import conversation_repository
from backend.memory.conversation import get_long_term_memories
from backend.context.models import ContextType
from backend.context.analyzer import context_analyzer
from backend.context.state_manager import conversation_state_manager
from backend.context.retriever import relevant_context_retriever
from backend.llm.prompts import build_contextual_system_prompt

logger = logging.getLogger("ace.conversations.service")

DYNAMIC_TOOLS = {"get_time", "get_system_info", "take_screenshot", "read_clipboard"}


class ToolExecutionResult(tuple):
    """3-tuple subclass containing (tool_name, tool_executed, tool_result_prefix)
    with direct access to raw tool_result as property/attribute.
    Can also be unpacked as (tool_name, tool_executed, prefix)."""
    tool_name: Optional[str]
    tool_executed: Optional[str]
    prefix: Optional[str]
    tool_result: Optional[str]

    def __new__(cls, tool_name, tool_executed, prefix, tool_result=None):
        return super().__new__(cls, (tool_name, tool_executed, prefix))

    def __init__(self, tool_name, tool_executed, prefix, tool_result=None):
        self.tool_name = tool_name
        self.tool_executed = tool_executed
        self.prefix = prefix
        self.tool_result = tool_result


def _get_tool_speech_summary(tool_name: str, tool_result: str) -> str:
    """Provide a natural, concise spoken companion voice line for desktop tool actions."""
    spoken_map = {
        "get_system_info": "Here are your PC specs and hardware details.",
        "get_resource_usage": "Here is your current resource usage.",
        "get_processes": "Here are the active processes running on your system.",
        "search_processes": "Here are the processes matching your search.",
        "get_process_details": "Here are the details for that process.",
        "get_active_window": "Here is your active window.",
        "get_clipboard": "Here is what is currently in your clipboard.",
        "set_clipboard": "Copied to your clipboard.",
        "clear_clipboard": "Clipboard cleared.",
        "open_application": "I've launched the application for you.",
        "open_folder": "Opened the folder for you.",
        "open_file": "Opened the file for you.",
        "terminate_process": "Terminated the process.",
        "show_notification": "Notification displayed.",
        "take_screenshot": "I've taken the screenshot.",
    }
    if tool_name in spoken_map:
        return spoken_map[tool_name]
    if len(tool_result) <= 120 and "\n" not in tool_result and "|" not in tool_result:
        clean = re.sub(r"[✅❌⚠️📋🖥️📊🔍ℹ️]", "", tool_result).strip()
        return clean or tool_result
    return "Here are the results."


def _chunk_tool_response_tokens(text: str) -> list[str]:
    """Split response into small chunks for responsive SSE streaming."""
    lines = text.splitlines(keepends=True)
    chunks = []
    for line in lines:
        if len(line) <= 40:
            chunks.append(line)
        else:
            for i in range(0, len(line), 30):
                chunks.append(line[i:i + 30])
    return chunks


class ChatService:
    """Orchestrates conversation memory, tool execution, response caching,
    LLM generation, and sentence-streaming text-to-speech.
    """

    def __init__(self):
        self.router = agent_router
        self.llm = ollama_client
        self.tts = tts_engine
        self.cache = response_cache
        self.repo = conversation_repository
        self._single_flight: Dict[str, asyncio.Future] = {}
        self._single_flight_lock = asyncio.Lock()

    def check_and_execute_tool(self, user_text: str) -> ToolExecutionResult:
        """Checks for tool intent and executes it if matched."""
        intent = self.router.check_intent(user_text)
        if not intent:
            return ToolExecutionResult(None, None, None, None)

        tool_name, tool_args = intent
        try:
            exec_res = self.router.execute_tool(tool_name, tool_args)
            if isinstance(exec_res, tuple):
                success, tool_result = exec_res
            else:
                tool_result = str(exec_res)
        except Exception as e:
            logger.error(f"Error executing tool '{tool_name}': {e}")
            tool_result = f"Error: {e}"

        tool_executed = f"{tool_name}({tool_args})"
        tool_result_prefix = f"[Executed desktop tool '{tool_name}': {tool_result}]\n"
        return ToolExecutionResult(tool_name, tool_executed, tool_result_prefix, tool_result)

    @staticmethod
    def _find_sentence_boundary(text: str) -> int:
        """Find the index of the first natural sentence boundary in text for streaming TTS."""
        if not text:
            return -1

        nl_idx = text.find("\n")
        if nl_idx != -1 and len(text[:nl_idx].strip().split()) >= 2:
            return nl_idx + 1

        pattern = re.compile(r"([.!?])(?:\s+|$)")
        for match in pattern.finditer(text):
            end_pos = match.end()
            punct_char = match.group(1)
            char_idx = match.start(1)

            if punct_char == ".":
                if char_idx > 0 and char_idx + 1 < len(text):
                    if text[char_idx - 1].isdigit() and text[char_idx + 1].isdigit():
                        continue
                word_before = text[:char_idx].split()[-1] if text[:char_idx].split() else ""
                clean_word = re.sub(r"[^\w]", "", word_before.lower())
                if clean_word in {"mr", "mrs", "ms", "dr", "prof", "sr", "jr", "vs", "etc", "eg", "ie"}:
                    continue

            return end_pos

        return -1

    async def execute_chat(
        self,
        message: str,
        session_id: str = "default",
        speak: bool = True
    ) -> Dict[str, Any]:
        """Execute a complete single chat turn with contextual reasoning and context-aware cache."""
        user_text = message.strip()
        if not user_text:
            return {
                "user_message": "",
                "response": "",
                "tool_executed": None,
                "state": "idle"
            }

        # Save user message
        self.repo.add_message(role="user", content=user_text, session_id=session_id)

        # 1. Constant math evaluation (instant 0.01ms, non-contextual)
        constant_math = evaluate_constant_math(user_text)
        if constant_math:
            logger.info(f"Resolved constant math instantly: '{user_text}' -> '{constant_math}'")
            self.repo.add_message(role="assistant", content=constant_math, session_id=session_id)
            self.cache.set(user_text, constant_math)
            if speak:
                self.tts.speak(constant_math, block=False)
            return {
                "user_message": user_text,
                "response": constant_math,
                "tool_executed": "constant_math_eval",
                "state": "speaking" if speak else "idle",
                "cached": True
            }

        # 2. Context Analysis & State Tracking
        state = conversation_state_manager.get_state(session_id)
        recent_turns = self.repo.get_recent_messages(session_id=session_id, limit=4)
        analysis = await context_analyzer.analyze(
            user_message=user_text,
            current_topic=state.get("current_topic"),
            current_entity=state.get("current_entity"),
            recent_turns=recent_turns,
            use_llm_if_needed=False
        )

        active_topic = analysis.topic or state.get("current_topic")
        active_entity = analysis.entity or state.get("current_entity")
        active_correction = state.get("active_correction")

        # 3. Handle Corrections & Topic Transitions
        if analysis.context_type == ContextType.CORRECTION:
            old_entity, new_entity = conversation_state_manager.apply_correction(
                session_id=session_id,
                new_entity=analysis.entity or analysis.new_context or "alternative",
                new_topic=analysis.topic,
                entity_type=analysis.entity_type
            )
            # Invalidate incompatible cache entries across all tiers
            self.cache.invalidate_context(
                topic=analysis.topic,
                entity=new_entity,
                conflicting_context=old_entity or analysis.correction_target
            )
            active_entity = new_entity
            active_topic = analysis.topic or active_topic
            active_correction = f"{old_entity} -> {new_entity}"
        elif analysis.context_type == ContextType.TOPIC_SWITCH:
            conversation_state_manager.update_state(
                session_id=session_id,
                topic=analysis.topic,
                entity=analysis.entity,
                entity_type=analysis.entity_type,
                active_correction=None
            )
            active_topic = analysis.topic
            active_entity = analysis.entity
            active_correction = None
        elif analysis.context_type in {ContextType.FOLLOW_UP, ContextType.REFERENCE}:
            if not active_entity and state.get("current_entity"):
                active_entity = state.get("current_entity")

        # 4. Tool execution check (Action intents bypass conversational cache)
        tool_exec_res = self.check_and_execute_tool(user_text)
        tool_name, tool_executed, tool_result_prefix = tool_exec_res
        tool_result = getattr(tool_exec_res, "tool_result", None)

        if tool_name and tool_result is not None:
            final_text = tool_result
            self.repo.add_message(
                role="assistant",
                content=final_text,
                session_id=session_id,
                metadata_json=json.dumps(analysis.to_dict())
            )
            conversation_state_manager.update_state(
                session_id=session_id,
                topic=analysis.topic or state.get("current_topic"),
                entity=analysis.entity or state.get("current_entity"),
                last_user=user_text,
                last_assistant=final_text
            )

            is_cacheable = False
            from backend.tools.registry import tool_registry
            t = tool_registry.get(tool_name)
            if t:
                is_cacheable = t.cacheable
            else:
                is_cacheable = (tool_name not in DYNAMIC_TOOLS)

            if is_cacheable and final_text:
                self.cache.set(
                    prompt=user_text,
                    response=final_text,
                    tool_executed=tool_executed,
                    context_key=active_entity,
                    entity=active_entity,
                    topic=active_topic
                )

            if speak and final_text:
                spoken_summary = _get_tool_speech_summary(tool_name, final_text)
                self.tts.speak(spoken_summary, block=False)

            return {
                "user_message": user_text,
                "response": final_text,
                "tool_executed": tool_executed,
                "state": "speaking" if speak and final_text else "idle",
                "cached": False
            }

        # 5. Context-Aware Cache Lookup (Skipped on corrections or when tool is executed)
        if analysis.context_type != ContextType.CORRECTION and not tool_name:
            cached_entry = self.cache.get(
                prompt=user_text,
                context_key=active_entity,
                entity=active_entity,
                topic=active_topic
            )
            if cached_entry:
                cached_response = cached_entry["response"]
                cached_tool = cached_entry.get("tool_executed")
                self.repo.add_message(
                    role="assistant",
                    content=cached_response,
                    session_id=session_id,
                    metadata_json=json.dumps(analysis.to_dict())
                )
                if speak:
                    self.tts.speak(cached_response, block=False)
                return {
                    "user_message": user_text,
                    "response": cached_response,
                    "tool_executed": cached_tool,
                    "state": "speaking" if speak else "idle",
                    "cached": True,
                    "source": cached_entry.get("source", "cache")
                }

        # 6. Relevant Context Retrieval & Contextual Prompt Builder
        recent_messages = relevant_context_retriever.get_relevant_context_turns(
            session_id=session_id,
            analysis=analysis,
            current_entity=active_entity,
            current_topic=active_topic,
            max_tokens=1000
        )
        memories = get_long_term_memories()

        if tool_result_prefix:
            recent_messages.append({"role": "system", "content": tool_result_prefix})

        contextual_system_prompt = build_contextual_system_prompt(
            user_memories=memories,
            current_topic=active_topic,
            current_entity=active_entity,
            current_entity_type=analysis.entity_type or state.get("current_entity_type"),
            active_correction=active_correction,
            is_ambiguous=analysis.ambiguity_detected,
            ambiguity_candidates=analysis.candidate_entities
        )

        # 7. Ollama LLM generation
        full_response = ""
        async for token in self.llm.chat_stream(
            messages=recent_messages,
            system_prompt=contextual_system_prompt,
            memories=memories
        ):
            full_response += token

        final_text = full_response.strip()
        lowered_final = final_text.lower()
        is_error_resp = "error communicating with ollama" in lowered_final or final_text.startswith("[Error") or final_text.startswith("[Ollama error")

        if not is_error_resp and final_text:
            self.repo.add_message(
                role="assistant",
                content=final_text,
                session_id=session_id,
                metadata_json=json.dumps(analysis.to_dict())
            )
            # Update conversational state with new entity/topic if established
            updated_entity = active_entity or analysis.entity
            updated_topic = active_topic or analysis.topic
            conversation_state_manager.update_state(
                session_id=session_id,
                topic=updated_topic,
                entity=updated_entity,
                last_user=user_text,
                last_assistant=final_text
            )

        is_cacheable = not is_error_resp and not analysis.ambiguity_detected
        if tool_name:
            from backend.tools.registry import tool_registry
            t = tool_registry.get(tool_name)
            if t:
                is_cacheable = is_cacheable and t.cacheable
            else:
                is_cacheable = is_cacheable and (tool_name not in DYNAMIC_TOOLS)

        if is_cacheable and final_text:
            self.cache.set(
                prompt=user_text,
                response=final_text,
                tool_executed=tool_executed,
                context_key=active_entity,
                entity=active_entity,
                topic=active_topic
            )

        if speak and final_text:
            self.tts.speak(final_text, block=False)

        return {
            "user_message": user_text,
            "response": final_text,
            "tool_executed": tool_executed,
            "state": "speaking" if speak and final_text else "idle",
            "cached": False
        }

    async def stream_chat(
        self,
        message: str,
        session_id: str = "default",
        speak: bool = True
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream chat tokens with contextual reasoning & context-aware cache."""
        user_text = message.strip()
        if not user_text:
            yield {"type": "error", "error": "Message cannot be empty."}
            return

        yield {"type": "start", "user_message": user_text}
        self.repo.add_message(role="user", content=user_text, session_id=session_id)

        # 1. Instant Constant Math (non-contextual)
        constant_math = evaluate_constant_math(user_text)
        if constant_math:
            yield {"type": "token", "content": constant_math}
            self.repo.add_message(role="assistant", content=constant_math, session_id=session_id)
            self.cache.set(user_text, constant_math)
            if speak:
                self.tts.speak(constant_math, block=False)
            yield {
                "type": "done",
                "user_message": user_text,
                "response": constant_math,
                "tool_executed": "constant_math_eval",
                "state": "speaking" if speak else "idle",
                "cached": True
            }
            return

        # 2. Context Analysis & State Tracking
        state = conversation_state_manager.get_state(session_id)
        recent_turns = self.repo.get_recent_messages(session_id=session_id, limit=4)
        analysis = await context_analyzer.analyze(
            user_message=user_text,
            current_topic=state.get("current_topic"),
            current_entity=state.get("current_entity"),
            recent_turns=recent_turns,
            use_llm_if_needed=False
        )

        active_topic = analysis.topic or state.get("current_topic")
        active_entity = analysis.entity or state.get("current_entity")
        active_correction = state.get("active_correction")

        # 3. Handle Corrections & Topic Transitions
        if analysis.context_type == ContextType.CORRECTION:
            old_entity, new_entity = conversation_state_manager.apply_correction(
                session_id=session_id,
                new_entity=analysis.entity or analysis.new_context or "alternative",
                new_topic=analysis.topic,
                entity_type=analysis.entity_type
            )
            # Invalidate incompatible cache entries across all tiers
            self.cache.invalidate_context(
                topic=analysis.topic,
                entity=new_entity,
                conflicting_context=old_entity or analysis.correction_target
            )
            active_entity = new_entity
            active_topic = analysis.topic or active_topic
            active_correction = f"{old_entity} -> {new_entity}"
        elif analysis.context_type == ContextType.TOPIC_SWITCH:
            conversation_state_manager.update_state(
                session_id=session_id,
                topic=analysis.topic,
                entity=analysis.entity,
                entity_type=analysis.entity_type,
                active_correction=None
            )
            active_topic = analysis.topic
            active_entity = analysis.entity
            active_correction = None
        elif analysis.context_type in {ContextType.FOLLOW_UP, ContextType.REFERENCE}:
            if not active_entity and state.get("current_entity"):
                active_entity = state.get("current_entity")

        # 4. Desktop Tool Check (Action intents bypass conversational cache)
        tool_name, tool_executed, tool_result_prefix = None, None, None
        intent = self.router.check_intent(user_text)
        if intent:
            t_name, tool_args = intent
            yield {"type": "tool_start", "tool": f"{t_name}({tool_args})"}
            tool_exec_res = self.check_and_execute_tool(user_text)
            tool_name, tool_executed, tool_result_prefix = tool_exec_res
            tool_result = getattr(tool_exec_res, "tool_result", None)
            yield {
                "type": "tool_result",
                "tool": tool_executed,
                "result_prefix": tool_result_prefix
            }

            if tool_name and tool_result is not None:
                final_text = tool_result
                # Stream the markdown output directly to the UI in responsive chunks
                for chunk in _chunk_tool_response_tokens(final_text):
                    yield {"type": "token", "content": chunk}
                    await asyncio.sleep(0.005)

                self.repo.add_message(
                    role="assistant",
                    content=final_text,
                    session_id=session_id,
                    metadata_json=json.dumps(analysis.to_dict())
                )
                conversation_state_manager.update_state(
                    session_id=session_id,
                    topic=analysis.topic or state.get("current_topic"),
                    entity=analysis.entity or state.get("current_entity"),
                    last_user=user_text,
                    last_assistant=final_text
                )

                is_cacheable = False
                from backend.tools.registry import tool_registry
                t = tool_registry.get(tool_name)
                if t:
                    is_cacheable = t.cacheable
                else:
                    is_cacheable = (tool_name not in DYNAMIC_TOOLS)

                if is_cacheable and final_text:
                    self.cache.set(
                        prompt=user_text,
                        response=final_text,
                        tool_executed=tool_executed,
                        context_key=active_entity,
                        entity=active_entity,
                        topic=active_topic
                    )

                if speak and final_text:
                    spoken_summary = _get_tool_speech_summary(tool_name, final_text)
                    self.tts.speak(spoken_summary, block=False)

                yield {
                    "type": "done",
                    "user_message": user_text,
                    "response": final_text,
                    "tool_executed": tool_executed,
                    "state": "speaking" if speak and final_text else "idle",
                    "cached": False
                }
                return

        # 5. Context-Aware Cache Lookup (Skipped on corrections or when tool is executed)
        if analysis.context_type != ContextType.CORRECTION and not tool_name:
            cached_entry = self.cache.get(
                prompt=user_text,
                context_key=active_entity,
                entity=active_entity,
                topic=active_topic
            )
            if cached_entry:
                cached_response = cached_entry["response"]
                cached_tool = cached_entry.get("tool_executed")
                yield {"type": "token", "content": cached_response}
                self.repo.add_message(
                    role="assistant",
                    content=cached_response,
                    session_id=session_id,
                    metadata_json=json.dumps(analysis.to_dict())
                )
                if speak:
                    self.tts.speak(cached_response, block=False)
                yield {
                    "type": "done",
                    "user_message": user_text,
                    "response": cached_response,
                    "tool_executed": cached_tool,
                    "state": "speaking" if speak else "idle",
                    "cached": True,
                    "source": cached_entry.get("source", "cache")
                }
                return

        # 6. Relevant Context Retrieval & Contextual Prompt Builder
        recent_messages = relevant_context_retriever.get_relevant_context_turns(
            session_id=session_id,
            analysis=analysis,
            current_entity=active_entity,
            current_topic=active_topic,
            max_tokens=1000
        )
        memories = get_long_term_memories()

        if tool_result_prefix:
            recent_messages.append({"role": "system", "content": tool_result_prefix})

        contextual_system_prompt = build_contextual_system_prompt(
            user_memories=memories,
            current_topic=active_topic,
            current_entity=active_entity,
            current_entity_type=analysis.entity_type or state.get("current_entity_type"),
            active_correction=active_correction,
            is_ambiguous=analysis.ambiguity_detected,
            ambiguity_candidates=analysis.candidate_entities
        )

        full_response = ""
        sentence_buffer = ""
        if speak and hasattr(self.tts, "start_streaming"):
            self.tts.start_streaming()

        try:
            async for token in self.llm.chat_stream(
                messages=recent_messages,
                system_prompt=contextual_system_prompt,
                memories=memories
            ):
                full_response += token
                yield {"type": "token", "content": token}
                if speak and hasattr(self.tts, "speak_stream_chunk"):
                    sentence_buffer += token
                    while True:
                        boundary_idx = self._find_sentence_boundary(sentence_buffer)
                        if boundary_idx == -1:
                            break
                        chunk = sentence_buffer[:boundary_idx].strip()
                        sentence_buffer = sentence_buffer[boundary_idx:].strip()
                        if chunk:
                            self.tts.speak_stream_chunk(chunk)
        except Exception as e:
            if speak and hasattr(self.tts, "stop"):
                self.tts.stop()
            logger.error(f"Error during LLM streaming: {e}")
            yield {"type": "error", "error": str(e)}
            return

        final_text = full_response.strip()
        lowered_final = final_text.lower()
        is_error_resp = "error communicating with ollama" in lowered_final or final_text.startswith("[Error") or final_text.startswith("[Ollama error")

        if not is_error_resp and final_text:
            self.repo.add_message(
                role="assistant",
                content=final_text,
                session_id=session_id,
                metadata_json=json.dumps(analysis.to_dict())
            )
            # Update conversational state with new entity/topic if established
            updated_entity = active_entity or analysis.entity
            updated_topic = active_topic or analysis.topic
            conversation_state_manager.update_state(
                session_id=session_id,
                topic=updated_topic,
                entity=updated_entity,
                last_user=user_text,
                last_assistant=final_text
            )

        is_cacheable = not is_error_resp and not analysis.ambiguity_detected
        if tool_name:
            from backend.tools.registry import tool_registry
            t = tool_registry.get(tool_name)
            if t:
                is_cacheable = is_cacheable and t.cacheable
            else:
                is_cacheable = is_cacheable and (tool_name not in DYNAMIC_TOOLS)

        if is_cacheable and final_text:
            self.cache.set(
                prompt=user_text,
                response=final_text,
                tool_executed=tool_executed,
                context_key=active_entity,
                entity=active_entity,
                topic=active_topic
            )

        if speak and final_text:
            if hasattr(self.tts, "speak_stream_chunk"):
                remainder = sentence_buffer.strip()
                if remainder:
                    self.tts.speak_stream_chunk(remainder)
                if hasattr(self.tts, "flush_streaming"):
                    self.tts.flush_streaming()
            else:
                self.tts.speak(final_text, block=False)

        yield {
            "type": "done",
            "user_message": user_text,
            "response": final_text,
            "tool_executed": tool_executed,
            "state": "speaking" if speak and final_text else "idle",
            "cached": False
        }


chat_service = ChatService()

