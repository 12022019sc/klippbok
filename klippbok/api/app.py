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
    from klippbok.api.routers.images import router as images_router

    app = FastAPI(
        title="klippbok",
        description="Dataset curation and preparation for LoRA training.",
        version="0.1.0",
    )

    # Store project_dir on app state for route handlers to access via request.app.state
    app.state.project_dir = project_dir if project_dir is not None else Path.cwd()

    # Register API routers BEFORE static files mount
    # (StaticFiles catch-all would intercept /api/ routes if mounted first)
    app.include_router(images_router, prefix="/api/v1")

    # Mount SPA static files (only if the static directory exists)
    # This is a catch-all that serves the React build; it must come last.
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        from fastapi.staticfiles import StaticFiles
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="spa")
        logger.info("SPA static files mounted from: %s", static_dir)
    else:
        logger.debug("No static directory found at %s; SPA not mounted", static_dir)

    return app
