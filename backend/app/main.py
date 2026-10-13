from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import Settings
from app.services.condor_source import HTCondorSource, SourceUnavailable
from app.services.events import EventStore
from app.services.monitor import Monitor
from app.services.outputs import OutputInspector

LOGGER = logging.getLogger("dashboard")


def build_monitor(settings: Settings) -> Monitor:
    return Monitor(
        source=HTCondorSource(settings.collector_host, settings.schedd_name),
        events=EventStore(settings.event_log_path),
        outputs=OutputInspector(settings.output_root, settings.preview_bytes),
        settings=settings,
    )


async def _source_unavailable(_: Request, exc: Exception) -> JSONResponse:
    LOGGER.warning("HTCondor unavailable: %s", exc)
    return JSONResponse(
        status_code=503,
        content={
            "error": "htcondor_unavailable",
            "message": "The monitoring backend could not query the HTCondor pool.",
        },
    )


def create_app(monitor: Monitor | None = None) -> FastAPI:
    app = FastAPI(title="HTCondor Job Lifecycle Dashboard API", version="1.0.0")
    app.state.monitor = monitor or build_monitor(Settings.from_environment())
    app.include_router(router)
    app.add_exception_handler(SourceUnavailable, _source_unavailable)
    return app


app = create_app()
