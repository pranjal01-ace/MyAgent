from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from backend.common.schemas import BaseAuditSchema


class MemoryCreateSchema(BaseModel):
    """Schema for creating a new long-term memory."""
    key: str = Field(..., min_length=1, max_length=120, description="Unique memory identifier/title")
    value: str = Field(..., min_length=1, description="Memory factual text or preference value")
    category: Optional[str] = Field(default="general", max_length=50, description="Memory category tag")


class MemoryUpdateSchema(BaseModel):
    """Schema for updating an existing memory."""
    value: Optional[str] = Field(None, min_length=1)
    category: Optional[str] = Field(None, max_length=50)


class MemoryResponseSchema(BaseAuditSchema):
    """Response schema representing a persisted memory with audit metadata."""
    model_config = ConfigDict(from_attributes=True)

    key: str
    value: str
    category: str
