"""
Memory Domain Router.

Provides HTTP REST endpoints for storing, retrieving, and deleting long-term user memories.
Includes dual routes supporting both '/memories' (plural RESTful) and '/memory' (singular legacy).
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status

from backend.memories.schemas import MemoryCreateSchema, MemoryResponseSchema
from backend.memories.service import memory_service
from backend.common.exceptions import EntityNotFoundError

logger = logging.getLogger("ace.memories.router")

# Primary RESTful router with prefix /memories
router = APIRouter(prefix="/memories", tags=["memories"])

# Backward-compatibility router with prefix /memory
memory_alias_router = APIRouter(prefix="/memory", tags=["memories"])


# ==============================================================================
# Plural Endpoints (/api/memories)
# ==============================================================================

@router.get(
    "",
    response_model=List[MemoryResponseSchema],
    summary="List long-term memories"
)
async def get_memories_endpoint(category: Optional[str] = Query(None)):
    """Retrieve all active long-term memories, optionally filtered by category."""
    return memory_service.list_memories(category=category)


@router.get(
    "/detailed",
    summary="Get detailed memories with audit timestamps"
)
async def get_detailed_memories_endpoint():
    """Retrieve all active memories with ISO audit timestamps."""
    detailed = memory_service.list_memories_detailed()
    return {"memories": detailed, "count": len(detailed)}


@router.post(
    "",
    response_model=MemoryResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create or update memory"
)
async def create_memory_endpoint(req: MemoryCreateSchema):
    """Store or update a user preference, personal detail, or project note."""
    record = memory_service.create_or_update_memory(
        key=req.key,
        value=req.value,
        category=req.category or "general"
    )
    return record


@router.get(
    "/{key}",
    response_model=MemoryResponseSchema,
    summary="Get single memory by key"
)
async def get_single_memory_endpoint(key: str):
    """Retrieve a specific memory by its unique key."""
    try:
        return memory_service.get_memory(key)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)


@router.delete(
    "/{key}",
    summary="Delete memory by key"
)
async def delete_memory_endpoint(key: str):
    """Delete a specific memory by its unique key."""
    try:
        memory_service.remove_memory(key)
        return {"success": True, "message": f"Memory '{key}' deleted successfully."}
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)


# ==============================================================================
# Legacy Singular Endpoints (/api/memory)
# ==============================================================================

@memory_alias_router.post(
    "",
    summary="Add or update memory (legacy format)"
)
async def add_memory_legacy(req: MemoryCreateSchema):
    """Legacy endpoint supporting singular /api/memory."""
    memory_service.create_or_update_memory(
        key=req.key,
        value=req.value,
        category=req.category or "user_info"
    )
    return {"status": "success", "key": req.key, "value": req.value}


@memory_alias_router.delete(
    "/{key}",
    summary="Delete memory (legacy format)"
)
async def remove_memory_legacy(key: str):
    """Legacy endpoint supporting singular /api/memory/{key}."""
    try:
        memory_service.remove_memory(key)
        return {"status": "success", "message": f"Memory '{key}' deleted"}
    except EntityNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Memory '{key}' not found")
