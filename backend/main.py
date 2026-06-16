# main.py
# ─────────────────────────────────────────────
# FastAPI application entry point
# This is where everything connects together
# ─────────────────────────────────────────────

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import logging
import os
from fastapi.staticfiles import StaticFiles

# Import all routers
from routers import endpoints, webhooks, dashboard

# ── Setup logging ──
# This makes print statements better
# Shows timestamp + level + message
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s'
)
logger = logging.getLogger(__name__)


# ── Create FastAPI app ──
app = FastAPI(
    title="Webhook Monitor",
    description="Monitor webhook delivery in real time",
    version="1.0.0",
    # Swagger UI available at /docs
    # ReDoc available at /redoc
)

app.mount(
    "/static",
    StaticFiles(directory="../frontend"),
    name="static"
)
# ── CORS Middleware ──
# Allows frontend (different port) to call backend
# In development: frontend on :3000, backend on :8000
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # allow all origins in dev
    allow_credentials=True,
    allow_methods=["*"],      # allow GET, POST, etc
    allow_headers=["*"],      # allow all headers
)


# ── Global Error Handler ──
# Catches any unhandled exception
# Hides internal details from users
@app.exception_handler(Exception)
async def global_exception_handler(
    request: Request,
    exc: Exception
):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "Internal server error"
            # Never expose exc details to users
        }
    )


# ── Include Routers ──
# Each router handles a group of related endpoints
app.include_router(endpoints.router)
app.include_router(webhooks.router)
app.include_router(dashboard.router)


# ── Health Check ──
# Production systems always have this
# Load balancers ping /health to check if app is alive
@app.get("/health")
async def health_check():
    """
    Health check endpoint.
    Returns 200 if app is running correctly.
    """
    return {
        "status": "ok",
        "app": "Webhook Monitor",
        "version": "1.0.0"
    }


# ── Serve Frontend ──
# Serve HTML/CSS/JS files
frontend_path = os.path.join(
    os.path.dirname(__file__),
    "..",
    "frontend"
)

if os.path.exists(frontend_path):
    app.mount(
        "/static",
        StaticFiles(directory=frontend_path),
        name="static"
    )

    @app.get("/")
    async def serve_frontend():
        """Serve the main dashboard"""
        return FileResponse(
            os.path.join(frontend_path, "index.html")
        )
else:
    @app.get("/")
    async def root():
        return {
            "message": "Webhook Monitor API",
            "docs": "/docs",
            "health": "/health"
        }


# ── Startup Event ──
@app.on_event("startup")
async def on_startup():
    logger.info("=" * 50)
    logger.info("Webhook Monitor starting up")
    logger.info("Docs available at: http://localhost:8000/docs")
    logger.info("Dashboard at: http://localhost:8000")
    logger.info("=" * 50)


# ── Run directly with python main.py ──
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True  # auto-restart on code changes
    )