from __future__ import annotations

import asyncio

from fastapi import Request

from .comfy_client import ComfyClient
from .job_registry import JobRegistry
from .runtime import WorkerRuntime
from .service import GenerationService


def get_runtime(request: Request) -> WorkerRuntime:
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None:
        raise RuntimeError("Worker runtime has not been initialized.")
    return runtime


def get_comfy_client(request: Request) -> ComfyClient:
    return get_runtime(request).comfy_client


def get_generation_service(request: Request) -> GenerationService:
    return get_runtime(request).generation_service


def get_generation_semaphore(request: Request) -> asyncio.Semaphore:
    return get_runtime(request).generation_semaphore


def get_job_registry(request: Request) -> JobRegistry:
    return get_runtime(request).job_registry


def get_request_id(request: Request) -> str:
    return request.state.request_id
