
import time
from typing import Callable
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import structlog


logger = structlog.get_logger()


class ASGILoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        
        structlog.contextvars.clear_contextvars()

        structlog.contextvars.bind_contextvars(
            path = request.url.path,
            method = request.method,
            client_ip = request.client.host if request.client else None
        )
        
        start_time = time.perf_counter()
        try:
            response = await call_next(request)
            process_time = (time.perf_counter() - start_time) * 1000

            logger.info(
                    "Request processed successfully",
                    status_code=response.status_code,
                    duration_ms=round(process_time, 2),
                )
            return response
        except Exception as exc:
            process_time = (time.perf_counter() - start_time) * 1000
            logger.error(
                "Request failed with error",
                error=str(exc),
                duration_ms=round(process_time, 2),
                exc_info=True
            )
            raise exc
        