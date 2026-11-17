"""
Context Domain Models
=====================
Defines typed schemas and enums for conversational context analysis,
topic/entity tracking, reference resolution, and correction classification.
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ContextType(str, Enum):
    """Classification of how a message relates to current dialogue context."""
    NEW_TOPIC = "NEW_TOPIC"
    FOLLOW_UP = "FOLLOW_UP"
    CORRECTION = "CORRECTION"
    CLARIFICATION = "CLARIFICATION"
    REFERENCE = "REFERENCE"
    TOPIC_SWITCH = "TOPIC_SWITCH"
    CONTINUATION = "CONTINUATION"
    AMBIGUOUS = "AMBIGUOUS"


class ReferenceTarget(BaseModel):
    """Details of a resolved or candidate coreference in dialogue."""
    target_type: str = Field(default="previous_turn", description="'previous_turn', 'tracked_entity', or 'none'")
    turn_id: Optional[int] = Field(default=None, description="Referenced conversation turn ID")
    pronoun: Optional[str] = Field(default=None, description="Pronoun used (e.g. 'it', 'they', 'that', 'this')")
    resolved_entity: Optional[str] = Field(default=None, description="Resolved entity string")


class ContextAnalysis(BaseModel):
    """
    Structured context analysis payload produced by ContextAnalyzer.
    """
    context_type: ContextType = Field(default=ContextType.NEW_TOPIC, description="Primary message contextual relation")
    topic: Optional[str] = Field(default=None, description="Identified or active topic (e.g., 'apple', 'python')")
    entity: Optional[str] = Field(default=None, description="Specific entity (e.g., 'fruit', 'apple_inc', 'python_lang')")
    entity_type: Optional[str] = Field(default=None, description="Entity category (e.g., 'food', 'company', 'tool')")
    references_previous: bool = Field(default=False, description="True if message depends on preceding context")
    reference_turn_id: Optional[int] = Field(default=None, description="Turn ID being referred to")
    correction_target: Optional[str] = Field(default=None, description="Previous interpretation being corrected")
    new_context: Optional[str] = Field(default=None, description="Corrected or replacement interpretation")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score for this analysis")
    ambiguity_detected: bool = Field(default=False, description="True if prompt has multiple plausible interpretations without context")
    candidate_entities: List[str] = Field(default_factory=list, description="Plausible interpretations for ambiguous queries")
    raw_explanation: Optional[str] = Field(default=None, description="Optional reasoning explanation")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict with enum values represented as strings."""
        return {
            "context_type": self.context_type.value if isinstance(self.context_type, ContextType) else str(self.context_type),
            "topic": self.topic,
            "entity": self.entity,
            "entity_type": self.entity_type,
            "references_previous": self.references_previous,
            "reference_turn_id": self.reference_turn_id,
            "correction_target": self.correction_target,
            "new_context": self.new_context,
            "confidence": self.confidence,
            "ambiguity_detected": self.ambiguity_detected,
            "candidate_entities": self.candidate_entities,
            "raw_explanation": self.raw_explanation,
        }
