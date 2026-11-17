from fastapi import APIRouter
from backend.llm.ollama_client import ollama_client

router = APIRouter()

@router.get("/health")
async def health_check():
    ollama_ok = await ollama_client.check_connection()
    return {
        "status": "online",
        "character": "Portgas D. Ace",
        "ollama_connected": ollama_ok,
        "ollama_model": ollama_client.model
    }
