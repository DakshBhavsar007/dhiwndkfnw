"""Middleware for request-id tracking and structured JSON logging."""

import json
import logging
import time
import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("api_access")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware that assigns a unique request ID and logs structured JSON access entries."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Extract or generate a clean request ID
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        request.state.request_id = request_id

        start_time = time.perf_counter()
        response: Response = await call_next(request)
        duration_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

        # Attach request ID to response header
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Debug-Path"] = request.url.path

        # Build structured JSON log payload
        log_payload = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "query": str(request.query_params),
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        }

        logger.info(json.dumps(log_payload))
        return response


class VercelPathCorrectionMiddleware:
    """ASGI middleware to correct path when Vercel serverless rewrites modify scope['path']."""

    def __init__(self, app: Callable):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") in ("http", "websocket"):
            headers = dict(scope.get("headers", []))
            matched_path = headers.get(b"x-matched-path")
            if matched_path:
                decoded = matched_path.decode("utf-8")
                scope["path"] = decoded.split("?")[0]
            else:
                current_path = scope.get("path", "")
                for prefix in (
                    "/app/main.py",
                    "/api/index.py",
                    "/main.py",
                    "/api/index",
                ):
                    if current_path.startswith(prefix):
                        scope["path"] = current_path[len(prefix):] or "/"
                        break
        await self.app(scope, receive, send)

