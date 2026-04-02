from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI

from .comfy_client import ComfyClient
from .config import settings
from .job_registry import JobRegistry
from .service import GenerationService
from .state import worker_state


@dataclass(slots=True)
class WorkerRuntime:
    comfy_client: ComfyClient
    generation_service: GenerationService
    generation_semaphore: asyncio.Semaphore
    job_registry: JobRegistry


def create_worker_runtime() -> WorkerRuntime:
    comfy_client = ComfyClient()
    return WorkerRuntime(
        comfy_client=comfy_client,
        generation_service=GenerationService(comfy_client),
        generation_semaphore=asyncio.Semaphore(settings.max_concurrent_generations),
        job_registry=JobRegistry(settings.job_result_ttl_s),
    )


@asynccontextmanager
async def runtime_lifespan(app: FastAPI):
    runtime = create_worker_runtime()
    app.state.runtime = runtime
    worker_state.mark_initializing()
    if await runtime.comfy_client.server_reachable():
        worker_state.mark_ready()
    try:
        yield
    finally:
        await runtime.comfy_client.aclose()
        if hasattr(app.state, "runtime"):
            delattr(app.state, "runtime")
