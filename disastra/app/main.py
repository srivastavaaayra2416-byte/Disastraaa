import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.redis import redis_manager
from app.api.sos import router as sos_router
from app.api.zones import router as zones_router
from app.api.facilities import router as facilities_router
from app.api.route import router as route_router
from app.api.dispatch import router as dispatch_router
from app.api.road_reports import router as road_reports_router
from app.api.notifications import router as notifications_router
from app.api.websockets import router as ws_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("disastra")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Connect to redis
    await redis_manager.connect()
    logger.info("Disastra Backend API initialized.")
    yield
    # Shutdown
    await redis_manager.disconnect()
    logger.info("Disastra Backend API shutdown.")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Space-Based Disaster Management and Rescue Platform API (Disastra)",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global consistent error shape middleware
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_SERVER_ERROR", "message": str(exc)}}
    )

# Health & Observability (Section 15)
@app.get("/health", tags=["Observability"])
async def health_check():
    return {
        "status": "healthy",
        "service": "disastra-backend",
        "version": settings.VERSION,
        "redis_connected": redis_manager.client is not None
    }

# Include API v1 Routers (Section 12: /v1/...)
api_v1_prefix = settings.API_V1_STR

app.include_router(sos_router, prefix=api_v1_prefix)
app.include_router(zones_router, prefix=api_v1_prefix)
app.include_router(facilities_router, prefix=api_v1_prefix)
app.include_router(route_router, prefix=api_v1_prefix)
app.include_router(dispatch_router, prefix=api_v1_prefix)
app.include_router(road_reports_router, prefix=api_v1_prefix)
app.include_router(notifications_router, prefix=api_v1_prefix)

# Include top-level routes as well for direct compliance with PRD endpoints (/sos, /zones, etc.)
app.include_router(sos_router)
app.include_router(zones_router)
app.include_router(facilities_router)
app.include_router(route_router)
app.include_router(dispatch_router)
app.include_router(road_reports_router)
app.include_router(notifications_router)
app.include_router(ws_router)

# Serve the frontend from the same origin as the API when it is present.
# This keeps the browser API base same-origin and works in the Docker image,
# whose project directory is mounted at /app during local development.
frontend_dir = Path(__file__).resolve().parents[1] / "frontend"
if frontend_dir.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
