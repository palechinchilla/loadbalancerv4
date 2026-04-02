from __future__ import annotations

import logging

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .exceptions import ComfyUnavailableError, ComfyValidationError
from .job_registry import WorkerBusyError
from .state import worker_state

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ComfyValidationError)
    async def handle_validation_error(
        request: Request, exc: ComfyValidationError
    ) -> JSONResponse:
        logger.warning(
            "validation_error request_id=%s detail=%s",
            getattr(request.state, "request_id", None),
            exc,
        )
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(ComfyUnavailableError)
    async def handle_comfy_unavailable(
        request: Request, exc: ComfyUnavailableError
    ) -> JSONResponse:
        worker_state.mark_initializing(str(exc))
        logger.warning(
            "comfy_unavailable request_id=%s detail=%s",
            getattr(request.state, "request_id", None),
            exc,
        )
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(httpx.TimeoutException)
    async def handle_http_timeout(
        request: Request, exc: httpx.TimeoutException
    ) -> JSONResponse:
        worker_state.mark_initializing(str(exc))
        logger.warning(
            "upstream_timeout request_id=%s detail=%s",
            getattr(request.state, "request_id", None),
            exc,
        )
        return JSONResponse(
            status_code=503,
            content={"detail": "ComfyUI upstream request timed out."},
        )

    @app.exception_handler(httpx.HTTPError)
    async def handle_http_error(
        request: Request, exc: httpx.HTTPError
    ) -> JSONResponse:
        worker_state.mark_initializing(str(exc))
        logger.warning(
            "upstream_http_error request_id=%s detail=%s",
            getattr(request.state, "request_id", None),
            exc,
        )
        return JSONResponse(
            status_code=503,
            content={"detail": "ComfyUI upstream request failed."},
        )

    @app.exception_handler(WorkerBusyError)
    async def handle_worker_busy(
        request: Request, exc: WorkerBusyError
    ) -> JSONResponse:
        logger.info(
            "worker_busy request_id=%s idempotency_key=%s detail=%s",
            getattr(request.state, "request_id", None),
            getattr(request.state, "idempotency_key", None),
            exc,
        )
        return JSONResponse(
            status_code=503,
            content={"detail": str(exc)},
            headers={"Retry-After": "1"},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception(
            "unexpected_error request_id=%s",
            getattr(request.state, "request_id", None),
            exc_info=exc,
        )
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
