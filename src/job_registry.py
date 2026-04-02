from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal

from .models import GenerateResponse


class WorkerBusyError(Exception):
    """Raised when the worker cannot start another unique generation immediately."""


@dataclass(slots=True)
class CachedJob:
    response: GenerateResponse
    expires_at: float


@dataclass(slots=True)
class JobClaim:
    status: Literal["completed", "inflight", "started"]
    response: GenerateResponse | None = None
    task: asyncio.Task[GenerateResponse] | None = None


class JobRegistry:
    def __init__(self, result_ttl_s: int) -> None:
        self._result_ttl_s = result_ttl_s
        self._lock = asyncio.Lock()
        self._inflight: dict[str, asyncio.Task[GenerateResponse]] = {}
        self._completed: dict[str, CachedJob] = {}

    async def claim(
        self,
        key: str,
        semaphore: asyncio.Semaphore,
        factory: Callable[[], Awaitable[GenerateResponse]],
    ) -> JobClaim:
        async with self._lock:
            now = time.monotonic()
            self._purge_expired_locked(now)

            cached = self._completed.get(key)
            if cached is not None:
                return JobClaim(
                    status="completed",
                    response=cached.response.model_copy(deep=True),
                )

            inflight = self._inflight.get(key)
            if inflight is not None:
                return JobClaim(status="inflight", task=inflight)

            # asyncio.Semaphore has no public try_acquire, so we guard the
            # private value behind a lock to enforce fail-fast admission.
            if getattr(semaphore, "_value", 0) <= 0:
                raise WorkerBusyError(
                    "Worker is busy processing another generation request."
                )

            await semaphore.acquire()
            task = asyncio.create_task(self._run_job(key, semaphore, factory))
            self._inflight[key] = task
            return JobClaim(status="started", task=task)

    async def _run_job(
        self,
        key: str,
        semaphore: asyncio.Semaphore,
        factory: Callable[[], Awaitable[GenerateResponse]],
    ) -> GenerateResponse:
        response: GenerateResponse | None = None
        try:
            response = await factory()
            return response
        finally:
            async with self._lock:
                self._inflight.pop(key, None)
                self._purge_expired_locked(time.monotonic())
                if response is not None and self._result_ttl_s > 0:
                    self._completed[key] = CachedJob(
                        response=response.model_copy(deep=True),
                        expires_at=time.monotonic() + self._result_ttl_s,
                    )
            semaphore.release()

    def _purge_expired_locked(self, now: float) -> None:
        expired = [
            key for key, cached_job in self._completed.items() if cached_job.expires_at <= now
        ]
        for key in expired:
            self._completed.pop(key, None)
