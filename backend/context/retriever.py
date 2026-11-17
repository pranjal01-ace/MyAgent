"""
Relevant Context Retriever
==========================
Selective context retrieval engine for token-budgeted Ollama prompting:
- Avoids dumping blind conversation history into the prompt.
- Extracts only the turns relevant to the active topic, entity, coreference, or correction.
- Strictly adheres to max token budgets.
"""

import logging
from typing import List, Dict, Optional, Any
from backend.conversations.repository import conversation_repository
from backend.context.models import ContextType, ContextAnalysis

logger = logging.getLogger("ace.context.retriever")


class RelevantContextRetriever:
    """
    Intelligently extracts dialogue turns relevant to the current query.
    """

    @staticmethod
    def estimate_tokens(text: str) -> int:
        return conversation_repository.estimate_tokens(text)

    def get_relevant_context_turns(
        self,
        session_id: str,
        analysis: ContextAnalysis,
        current_entity: Optional[str] = None,
        current_topic: Optional[str] = None,
        max_tokens: int = 1000,
        max_turns: int = 6
    ) -> List[Dict[str, str]]:
        """
        Retrieves a focused subset of recent dialogue turns matching the active context.
        """
        raw_budgeted = conversation_repository.get_budgeted_messages(
            session_id=session_id,
            max_tokens=max_tokens,
            max_count=max_turns
        )

        if not raw_budgeted:
            return []

        # If NEW_TOPIC or TOPIC_SWITCH without reference, return minimal immediate history (at most 2 turns)
        if analysis.context_type in {ContextType.NEW_TOPIC, ContextType.TOPIC_SWITCH} and not analysis.references_previous:
            # Return last 2 messages for natural conversation flow without polluting with old topic
            return raw_budgeted[-2:] if len(raw_budgeted) >= 2 else raw_budgeted

        # If CORRECTION, ensure the turn being corrected is included
        if analysis.context_type == ContextType.CORRECTION:
            # We want the last 2 to 4 messages leading up to this correction
            selected = raw_budgeted[-4:] if len(raw_budgeted) >= 4 else raw_budgeted
            return selected

        # If FOLLOW_UP or CONTINUATION, provide recent context where the entity was discussed
        if analysis.context_type in {ContextType.FOLLOW_UP, ContextType.CONTINUATION, ContextType.REFERENCE}:
            selected = raw_budgeted[-6:] if len(raw_budgeted) >= 6 else raw_budgeted
            return selected

        return raw_budgeted[-4:] if len(raw_budgeted) >= 4 else raw_budgeted


relevant_context_retriever = RelevantContextRetriever()
