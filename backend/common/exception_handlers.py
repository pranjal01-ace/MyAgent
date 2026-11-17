import logging
from fastapi import Request, status
from fastapi.responses import JSONResponse
from backend.common.exceptions import AppException

logger = logging.getLogger("ace.exceptions")


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handle custom application domain exceptions."""
    logger.warning(f"AppException on {request.method} {request.url.path}: {exc.message} (details: {exc.details})")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.message,
            "status_code": exc.status_code,
            "details": exc.details
        }
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler for unhandled server exceptions to prevent raw stack trace leakage."""
    logger.error(f"Unhandled Exception on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "An internal server error occurred.",
            "status_code": 500
        }
    )
