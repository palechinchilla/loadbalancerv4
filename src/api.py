from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request, Response, status

from . import runtime as runtime_module
from .comfy_client import ComfyClient
from .dependencies import (
    get_comfy_client,
    get_generation_semaphore,
    get_generation_service,
    get_job_registry,
    get_request_id,
)
from .http_errors import register_exception_handlers
from .http_middleware import install_request_context_middleware
from .job_registry import JobRegistry
from .models import GenerateRequest, GenerateResponse, HealthResponse
from .service import GenerationService
from .state import is_comfyui_process_alive, worker_state

logger = logging.getLogger(__name__)
router = APIRouter()


async def _build_health_response(comfy_client: ComfyClient) -> HealthResponse:
    reachable = await comfy_client.server_reachable()
    if reachable:
        worker_state.mark_ready()
    else:
        worker_state.mark_initializing(worker_state.last_error)
    return HealthResponse(
        status="ready" if worker_state.ready else "initializing",
        comfyui_reachable=reachable,
        comfyui_process_alive=is_comfyui_process_alive(),
    )


@router.get("/", response_model=HealthResponse)
async def root(
    comfy_client: ComfyClient = Depends(get_comfy_client),
) -> HealthResponse:
    return await _build_health_response(comfy_client)


@router.get("/health", response_model=HealthResponse)
async def health(
    comfy_client: ComfyClient = Depends(get_comfy_client),
) -> HealthResponse:
    return await _build_health_response(comfy_client)


@router.get("/ping", response_model=None)
async def ping(
    comfy_client: ComfyClient = Depends(get_comfy_client),
) -> Response | dict[str, str]:
    reachable = await comfy_client.server_reachable()
    if reachable:
        worker_state.mark_ready()
        return {"status": "healthy"}
    worker_state.mark_initializing("ComfyUI is still initializing")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/generate", response_model=GenerateResponse)
async def generate(
    request: Request,
    payload: GenerateRequest,
    generation_service: GenerationService = Depends(get_generation_service),
    generation_semaphore: asyncio.Semaphore = Depends(get_generation_semaphore),
    job_registry: JobRegistry = Depends(get_job_registry),
    request_id: str = Depends(get_request_id),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> GenerateResponse:
    if not idempotency_key:
        raise HTTPException(
            status_code=400, detail="Idempotency-Key header is required."
        )

    job_claim = await job_registry.claim(
        idempotency_key,
        generation_semaphore,
        lambda: generation_service.generate(payload),
    )

    if job_claim.response is not None:
        if not worker_state.ready:
            worker_state.mark_ready()
        logger.info(
            "generate_cache_hit request_id=%s idempotency_key=%s",
            request_id,
            idempotency_key,
        )
        return job_claim.response

    if job_claim.task is None:
        raise RuntimeError("Job registry returned no task for an active generation.")

    response = await job_claim.task
    if not worker_state.ready:
        worker_state.mark_ready()
    request.state.comfy_prompt_id = worker_state.last_prompt_id
    logger.info(
        "generate_%s request_id=%s idempotency_key=%s prompt_id=%s",
        job_claim.status,
        request_id,
        idempotency_key,
        worker_state.last_prompt_id,
    )
    return response


def create_main_app() -> FastAPI:
    app = FastAPI(
        title="Runpod Load-Balanced ComfyUI Worker",
        version="1.0.0",
        lifespan=runtime_module.runtime_lifespan,
    )
    install_request_context_middleware(app)
    register_exception_handlers(app)
    app.include_router(router)
    return app


app = create_main_app()
