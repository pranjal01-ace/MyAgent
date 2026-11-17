"""
Context Analyzer Engine
=======================
Performs two-tier hybrid conversational context analysis:
1. Tier 1: Microsecond rule/regex pattern matcher for explicit corrections,
   follow-up pronouns ('it', 'they', 'that'), continuations, and topic switches.
2. Tier 2: LLM Structured JSON analyzer for nuanced conversational references,
   with strict timeout and non-blocking fallback to ensure zero downtime.
"""

import re
import json
import logging
from typing import Optional, List, Dict, Any, Tuple
from backend.context.models import ContextType, ContextAnalysis

logger = logging.getLogger("ace.context.analyzer")

# Pre-compiled regex patterns for zero-overhead matching
CORRECTION_PATTERNS = [
    re.compile(r"^(?:no,?\s+)?(?:i\s+mean|i\s+meant|actually,?\s+(?:i\s+mean|i\s+meant)|not\s+that,?\s*|i['’]m\s+talking\s+about|i['’]m\s+referring\s+to|no,?\s+the\s+)(.+)$", re.IGNORECASE),
    re.compile(r"^(?:no,?\s+)(?:not\s+.+?,?\s*)?(?:the\s+)?([a-zA-Z0-9_\s]+?)(?:\s+(?:please|instead|brother|bro))?$", re.IGNORECASE),
    re.compile(r"^i\s+meant\s+(?:the\s+)?other\s+one$", re.IGNORECASE),
]

TOPIC_SWITCH_PATTERNS = [
    re.compile(r"^(?:forget\s+that[.,;]?\s*|never\s+mind[.,;]?\s*|moving\s+on[.,;]?\s*|instead[.,;]?\s*)?(?:tell\s+me\s+about|what\s+about|let['’]s\s+talk\s+about|how\s+about|switch\s+to)\s+(.+)$", re.IGNORECASE),
    re.compile(r"^actually[.,;]?\s+(?:tell\s+me\s+about|what\s+about|let['’]s\s+talk\s+about)\s+(.+)$", re.IGNORECASE),
]

PRONOUN_PATTERNS = [
    re.compile(r"\b(it|its|they|them|their|theirs|that|this|these|those)\b", re.IGNORECASE),
]

CONTINUATION_PATTERNS = [
    re.compile(r"^(?:tell\s+me\s+more|continue|go\s+on|elaborate|what\s+else\??|keep\s+going|more\s+info\??)$", re.IGNORECASE),
]

AMBIGUOUS_ENTITIES: Dict[str, Tuple[str, List[str]]] = {
    "apple": ("apple", ["fruit", "technology_company"]),
    "java": ("java", ["programming_language", "island", "coffee"]),
    "python": ("python", ["programming_language", "snake"]),
    "amazon": ("amazon", ["technology_company", "rainforest", "river"]),
    "tesla": ("tesla", ["automotive_company", "scientist_nikola_tesla", "unit_of_measurement"]),
    "mercury": ("mercury", ["planet", "element_metal", "roman_god"]),
}


class ContextAnalyzer:
    """
    Hybrid Context Analyzer for Ace AI Companion.
    """

    def __init__(self, confidence_threshold: float = 0.75):
        self.confidence_threshold = confidence_threshold

    def analyze_fast(
        self,
        user_message: str,
        current_topic: Optional[str] = None,
        current_entity: Optional[str] = None,
        last_turn: Optional[Dict[str, Any]] = None
    ) -> Optional[ContextAnalysis]:
        """
        Sub-millisecond heuristic & pattern classifier.
        Returns a ContextAnalysis if a high-confidence pattern matches, else None.
        """
        text = user_message.strip()
        lowered = text.lower()

        # 1. Continuation check
        for pat in CONTINUATION_PATTERNS:
            if pat.search(lowered):
                return ContextAnalysis(
                    context_type=ContextType.CONTINUATION,
                    topic=current_topic,
                    entity=current_entity,
                    references_previous=True,
                    confidence=0.98,
                    raw_explanation="Matched continuation phrase."
                )

        # 2. Topic Switch check
        for pat in TOPIC_SWITCH_PATTERNS:
            m = pat.match(lowered)
            if m:
                switched_topic = m.group(1).strip()
                switched_topic = re.sub(r"[?!.,;]+$", "", switched_topic).strip()
                return ContextAnalysis(
                    context_type=ContextType.TOPIC_SWITCH,
                    topic=switched_topic,
                    entity=switched_topic,
                    entity_type="general",
                    references_previous=False,
                    confidence=0.92,
                    raw_explanation=f"Topic switch detected to '{switched_topic}'"
                )

        # 3. Explicit Correction check
        for pat in CORRECTION_PATTERNS:
            m = pat.match(lowered)
            if m:
                extracted = m.group(1).strip() if m.groups() else "alternative"
                # Strip trailing punctuation or filler words
                extracted = re.sub(r"[?!.,;]+$", "", extracted).strip()
                extracted = re.sub(r"^(?:tell\s+me\s+about|what\s+about|how\s+about)\s+", "", extracted, flags=re.IGNORECASE).strip()
                new_entity = extracted
                new_topic = current_topic or extracted

                # If correcting 'fruit' vs 'company' for apple
                entity_type = "concept"
                if any(w in extracted for w in ["fruit", "food", "eat", "tree", "grow"]):
                    entity_type = "fruit"
                elif any(w in extracted for w in ["company", "tech", "iphone", "mac", "stock", "inc"]):
                    entity_type = "technology_company"

                return ContextAnalysis(
                    context_type=ContextType.CORRECTION,
                    topic=new_topic,
                    entity=new_entity,
                    entity_type=entity_type,
                    references_previous=True,
                    correction_target=current_entity or "previous_interpretation",
                    new_context=extracted,
                    confidence=0.95,
                    raw_explanation=f"Explicit correction matched: target='{current_entity}' -> new='{extracted}'"
                )

        # 4. Pronoun / Follow-Up check
        # If message contains coreference pronouns and we have an active entity/topic
        has_pronoun = any(pat.search(lowered) for pat in PRONOUN_PATTERNS)
        if has_pronoun and (current_entity or current_topic):
            resolved = current_entity or current_topic
            return ContextAnalysis(
                context_type=ContextType.FOLLOW_UP,
                topic=current_topic,
                entity=resolved,
                references_previous=True,
                confidence=0.90,
                raw_explanation=f"Coreference pronoun resolved to current entity '{resolved}'"
            )

        # 5. Introductory Entity query check (e.g. "what is apple?", "tell me about apple fruit", "who is X")
        topic_match = re.match(r"^(?:what\s+is|who\s+is|tell\s+me\s+about|define|explain)\s+(?:a\s+|an\s+|the\s+)?(.+)", lowered)
        if topic_match:
            raw_extracted = topic_match.group(1)
            cleaned_query = re.sub(r"[?!.,;]+$", "", raw_extracted).strip()

            if cleaned_query in AMBIGUOUS_ENTITIES:
                base_topic, candidates = AMBIGUOUS_ENTITIES[cleaned_query]
                if not current_entity:
                    return ContextAnalysis(
                        context_type=ContextType.AMBIGUOUS,
                        topic=base_topic,
                        entity=None,
                        entity_type="ambiguous",
                        references_previous=False,
                        ambiguity_detected=True,
                        candidate_entities=candidates,
                        confidence=0.88,
                        raw_explanation=f"Identified inherently ambiguous query '{cleaned_query}' with candidate interpretations {candidates}"
                    )
                else:
                    # User repeated the ambiguous term, but an active disambiguated context already exists
                    return ContextAnalysis(
                        context_type=ContextType.FOLLOW_UP,
                        topic=base_topic,
                        entity=current_entity,
                        references_previous=True,
                        confidence=0.90,
                        raw_explanation=f"Re-query of '{cleaned_query}' resolved to active context entity '{current_entity}'"
                    )
            else:
                return ContextAnalysis(
                    context_type=ContextType.NEW_TOPIC,
                    topic=cleaned_query,
                    entity=cleaned_query,
                    entity_type="general",
                    references_previous=False,
                    confidence=0.88,
                    raw_explanation=f"Identified specific query subject '{cleaned_query}'"
                )

        return None

    async def analyze_with_llm(
        self,
        user_message: str,
        current_topic: Optional[str] = None,
        current_entity: Optional[str] = None,
        recent_turns: Optional[List[Dict[str, str]]] = None
    ) -> Optional[ContextAnalysis]:
        """
        Fast structured LLM classifier using Ollama JSON schema generation.
        Strictly times out in 2.0s to avoid latency drag.
        """
        try:
            from backend.llm.ollama_client import ollama_client
            import httpx

            turns_summary = ""
            if recent_turns:
                for t in recent_turns[-3:]:
                    r = t.get("role", "user")
                    c = (t.get("content", "") or "")[:120]
                    turns_summary += f"{r.upper()}: {c}\n"

            system_instruction = (
                "You are an ultra-fast conversational intent analyzer. "
                "Classify the user message into JSON with keys: "
                "context_type (NEW_TOPIC, FOLLOW_UP, CORRECTION, CLARIFICATION, REFERENCE, TOPIC_SWITCH, CONTINUATION, AMBIGUOUS), "
                "topic (string or null), entity (string or null), entity_type (string or null), "
                "references_previous (boolean), correction_target (string or null), new_context (string or null), confidence (float 0.0-1.0). "
                "Output ONLY valid JSON."
            )

            user_prompt = (
                f"Current active topic: {current_topic or 'None'}\n"
                f"Current active entity: {current_entity or 'None'}\n"
                f"Recent Turns:\n{turns_summary}\n"
                f"User Message: {user_message}\n"
                "Return JSON:"
            )

            client = ollama_client._get_client()
            payload = {
                "model": ollama_client.model,
                "messages": [
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_prompt}
                ],
                "stream": False,
                "format": "json",
                "keep_alive": "30m",
                "options": {
                    "num_predict": 128,
                    "temperature": 0.1,
                    "num_thread": 4
                }
            }

            res = await client.post(
                f"{ollama_client.base_url}/api/chat",
                json=payload,
                timeout=2.0
            )
            if res.status_code == 200:
                data = res.json()
                content = data.get("message", {}).get("content", "")
                parsed = json.loads(content)
                c_type_str = str(parsed.get("context_type", "NEW_TOPIC")).upper()
                c_type = ContextType[c_type_str] if c_type_str in ContextType.__members__ else ContextType.NEW_TOPIC

                return ContextAnalysis(
                    context_type=c_type,
                    topic=parsed.get("topic") or current_topic,
                    entity=parsed.get("entity") or current_entity,
                    entity_type=parsed.get("entity_type"),
                    references_previous=bool(parsed.get("references_previous", False)),
                    correction_target=parsed.get("correction_target"),
                    new_context=parsed.get("new_context"),
                    confidence=float(parsed.get("confidence", 0.85)),
                    raw_explanation="Classified via structured Ollama JSON."
                )
        except Exception as e:
            logger.debug(f"Structured LLM context analysis skipped or timed out: {e}")
        return None

    async def analyze(
        self,
        user_message: str,
        current_topic: Optional[str] = None,
        current_entity: Optional[str] = None,
        recent_turns: Optional[List[Dict[str, str]]] = None,
        use_llm_if_needed: bool = True
    ) -> ContextAnalysis:
        """
        Main analysis entrypoint:
        1. Evaluates fast rule-based classifier (0.1ms).
        2. If high confidence, returns immediately.
        3. If ambiguous or nuanced and use_llm_if_needed is True, queries structured LLM.
        4. Gracefully defaults to robust safe fallback.
        """
        # 1. Tier 1: Fast rule analysis
        fast_res = self.analyze_fast(
            user_message=user_message,
            current_topic=current_topic,
            current_entity=current_entity,
            last_turn=recent_turns[-1] if recent_turns else None
        )
        if fast_res and fast_res.confidence >= self.confidence_threshold:
            return fast_res

        # 2. Tier 2: LLM analysis for non-obvious queries if context is active
        if use_llm_if_needed and (current_topic or current_entity or recent_turns):
            llm_res = await self.analyze_with_llm(
                user_message=user_message,
                current_topic=current_topic,
                current_entity=current_entity,
                recent_turns=recent_turns
            )
            if llm_res and llm_res.confidence >= self.confidence_threshold:
                return llm_res

        # 3. Fallback: Return fast result if any, else safe NEW_TOPIC default
        if fast_res:
            return fast_res

        clean_topic = user_message.strip()
        return ContextAnalysis(
            context_type=ContextType.NEW_TOPIC,
            topic=clean_topic[:60],
            entity=clean_topic[:60],
            references_previous=False,
            confidence=0.70,
            raw_explanation="Defaulted to new topic via fallback."
        )


context_analyzer = ContextAnalyzer()
