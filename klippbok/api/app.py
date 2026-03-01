"""FastAPI application factory for the klippbok web GUI backend.

Usage:
    from klippbok.api.app import create_app
    app = create_app(project_dir=Path("/my/project"))

The factory pattern allows project_dir to be injected at startup time,
making the app testable without global state.

Router registration order matters: API routers MUST be registered before
the SPA StaticFiles mount, or the catch-all static mount will intercept
API requests.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

logger = logging.getLogger(__name__)


def create_app(project_dir: Path | None = None) -> FastAPI:
    """Create and configure the klippbok FastAPI application.

    Args:
        project_dir: Root of the klippbok project. Defaults to current
            working directory if not provided.

    Returns:
        Configured FastAPI application instance.
    """
    from klippbok.api.routers import import_ as import_router_module
    from klippbok.api.routers.browse import router as browse_router
    from klippbok.api.routers.images import router as images_router
    from klippbok.api.routers.settings import router as settings_router

    # project_dir starts as None when no --project-dir is passed.
    # The user selects a project directory from the web UI.
    resolved_project_dir = project_dir

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Lifespan context manager: cancel active import tasks on shutdown."""
        yield
        # Shutdown: cancel all in-flight import tasks to avoid resource leaks
        from klippbok.api.routers.import_ import _tasks
        if _tasks:
            logger.info("Cancelling %d active import task(s) on shutdown", len(_tasks))
            for op_id, task in list(_tasks.items()):
                if not task.done():
                    task.cancel()
                    logger.debug("Cancelled import task for operation %s", op_id)

    app = FastAPI(
        title="klippbok",
        description="Dataset curation and preparation for LoRA training.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Store project_dir on app state for route handlers to access via request.app.state
    app.state.project_dir = resolved_project_dir

    # Register API routers BEFORE static files mount
    # (StaticFiles catch-all would intercept /api/ routes if mounted first)
    app.include_router(browse_router, prefix="/api/v1")
    app.include_router(images_router, prefix="/api/v1")
    app.include_router(import_router_module.router, prefix="/api/v1")
    app.include_router(settings_router, prefix="/api/v1")

    # SPA static files + fallback to index.html for client-side routes.
    # StaticFiles(html=True) alone only serves index.html at "/" — it 404s
    # on sub-paths like "/import" or "/settings" that the React router handles.
    # Instead, mount StaticFiles for real assets, then add a catch-all GET
    # that returns index.html for any non-API path (SPA fallback).
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles

        # Serve real static assets (JS, CSS, images) at /assets/
        assets_dir = static_dir / "assets"
        if assets_dir.exists():
            app.mount(
                "/assets",
                StaticFiles(directory=str(assets_dir)),
                name="assets",
            )

        # SPA fallback: serve static files by exact match, or index.html
        # for client-side routes. Excludes /api/ paths so mismatched API
        # requests get a proper 404 instead of the SPA shell.
        @app.get("/{file_path:path}")
        async def spa_fallback(file_path: str):
            """Serve static files if they exist, otherwise return index.html.

            This enables client-side routing: /import, /settings, etc. all
            get the SPA shell, and React Router handles the actual routing.
            API paths are excluded to avoid masking real 404s.
            """
            from fastapi import HTTPException

            # Never serve SPA shell for API paths — let them 404 properly
            if file_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not found")
            # Try to serve a real file first (e.g. vite.svg, favicon.ico)
            candidate = static_dir / file_path
            if file_path and candidate.is_file():
                return FileResponse(str(candidate))
            # Fallback: serve index.html for all non-file routes (SPA)
            return FileResponse(str(static_dir / "index.html"))

        logger.info("SPA static files mounted from: %s", static_dir)
    else:
        logger.debug("No static directory found at %s; SPA not mounted", static_dir)

    return app
