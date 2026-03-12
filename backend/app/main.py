"""Learning Management Service — FastAPI application."""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import verify_api_key
from app.routers import analytics, interactions, items, learners, pipeline
from app.settings import settings

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    description="A learning management service API.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(
    items.router,
    prefix="/items",
    tags=["items"],
    dependencies=[Depends(verify_api_key)],
)

if settings.enable_interactions:
    app.include_router(
        interactions.router,
        prefix="/interactions",
        tags=["interactions"],
        dependencies=[Depends(verify_api_key)],
    )

if settings.enable_learners:
    app.include_router(
        learners.router,
        prefix="/learners",
        tags=["learners"],
        dependencies=[Depends(verify_api_key)],
    )

app.include_router(
    pipeline.router,
    prefix="/pipeline",
    tags=["pipeline"],
    dependencies=[Depends(verify_api_key)],
)

app.include_router(
    analytics.router,
    prefix="/analytics",
    tags=["analytics"],
    dependencies=[Depends(verify_api_key)],
)
