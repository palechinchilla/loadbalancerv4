from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI, Response, status

from . import runtime as runtime_module
from .comfy_client import ComfyClient
from .dependencies import get_comfy_client
from .http_errors import register_exception_handlers
from .http_middleware import install_request_context_middleware
from .state import worker_state

router = APIRouter()


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


def create_health_app() -> FastAPI:
    app = FastAPI(
        title="Runpod Health Server",
        version="1.0.0",
        lifespan=runtime_module.runtime_lifespan,
    )
    install_request_context_middleware(app)
    register_exception_handlers(app)
    app.include_router(router)
    return app


health_app = create_health_app()
