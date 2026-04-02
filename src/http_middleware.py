from __future__ import annotations

import logging
import time
from uuid import uuid4

from fastapi import FastAPI, Request

logger = logging.getLogger(__name__)


def install_request_context_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        request.state.request_id = request_id
        request.state.idempotency_key = request.headers.get("Idempotency-Key")
        request.state.comfy_prompt_id = None

        started_at = time.perf_counter()
        response = await call_next(request)
        duration_ms = int((time.perf_counter() - started_at) * 1000)

        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_completed method=%s path=%s status=%s duration_ms=%s "
            "request_id=%s idempotency_key=%s prompt_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request_id,
            request.state.idempotency_key,
            request.state.comfy_prompt_id,
        )
        return response
