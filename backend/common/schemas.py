from typing import TypeVar, Generic, Optional, List, Any
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime

DataT = TypeVar("DataT")


class GenericResponse(BaseModel, Generic[DataT]):
    """Standard unified response wrapper."""
    success: bool = True
    message: Optional[str] = None
    data: Optional[DataT] = None


class BaseAuditSchema(BaseModel):
    """Base Pydantic schema reflecting audit timestamps."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
    is_active: bool = True
