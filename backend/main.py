# main.py
# ─────────────────────────────────────────────
# FastAPI application entry point
# Phase 7: Added auth router + completed ownership
# scoping across every existing router
# ─────────────────────────────────────────────

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import logging
import os

from routers import endpoints, webhooks, dashboard, delivery, ai, alerts, auth
from routers import health as health_router
from scheduler import start_scheduler, stop_scheduler, get_scheduler_status
from redis_client import check_redis_connection
from services.retry_queue import get_queue_status
from websocket.manager import manager
from config import settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Webhook Monitor",
    description="Monitor webhook delivery in real time",
    version="7.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": "Internal server error"}
    )

# ── Routers ──
app.include_router(auth.router)
app.include_router(endpoints.router)
app.include_router(webhooks.router)
app.include_router(dashboard.router)
app.include_router(health_router.router)
app.include_router(delivery.router)
app.include_router(ai.router)
app.include_router(alerts.router)


# ── WebSocket route (Phase 5, auth-gated in Phase 7) ──
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str | None = None):
    """
    Browsers connect here for live dashboard updates.

    Phase 7 requires a valid token (passed as ?token=... since
    browser WebSocket connections can't carry custom headers)
    just to open the connection at all — an unauthenticated
    caller can no longer connect.

    Still NOT fixed: every connected browser receives every
    broadcast regardless of whose endpoint triggered it. That's
    a separate, larger piece of work — it means threading user_id
    through every broadcast() call site in webhooks.py,
    health_checker.py, retry_queue.py, and ai_diagnosis.py, and
    changing ConnectionManager to filter by user on send. Named
    here explicitly (see PHASE7_README.md) rather than left as
    a silent gap.
    """
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return

    try:
        from auth_deps import auth_client
        response = auth_client.auth.get_user(token)
        if not response.user:
            await websocket.close(code=4001, reason="Invalid token")
            return
    except Exception:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/health")
async def health_check():
    scheduler_status = get_scheduler_status()
    redis_ok = check_redis_connection()
    queue_status = get_queue_status()
    return {
        "status": "ok",
        "app": "Webhook Monitor",
        "version": "7.0.0",
        "scheduler": scheduler_status,
        "redis": {
            "connected": redis_ok,
            "queue": queue_status
        },
        "websocket": {
            "active_connections": len(manager.active_connections)
        },
        "alerting": {
            "slack_configured": bool(settings.slack_webhook_url),
            "email_configured": bool(settings.resend_api_key and settings.alert_email_to),
        },
        "auth": {
            "anon_key_configured": bool(settings.supabase_key),
        }
    }

# ── Serve Frontend ──
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
        return FileResponse(
            os.path.join(frontend_path, "index.html")
        )

    @app.get("/dashboard.html")
    async def dashboard_page():
        return FileResponse(
            os.path.join(frontend_path, "dashboard.html")
        )

    @app.get("/endpoints.html")
    async def endpoints_page():
        return FileResponse(
            os.path.join(frontend_path, "endpoints.html")
        )

    @app.get("/settings.html")
    async def settings_page():
        return FileResponse(
            os.path.join(frontend_path, "settings.html")
        )

    @app.get("/endpoint_detail.html")
    async def endpoint_detail_page():
        return FileResponse(
            os.path.join(frontend_path, "endpoint_detail.html")
        )

else:

    @app.get("/")
    async def root():
        return {
            "message": "Webhook Monitor API",
            "docs": "/docs"
        }

# ── Startup ──
@app.on_event("startup")
async def on_startup():
    logger.info("=" * 50)
    logger.info("Webhook Monitor v7 starting up")
    logger.info("Docs: http://localhost:8000/docs")
    logger.info("WebSocket live dashboard: ws://localhost:8000/ws")

    if check_redis_connection():
        logger.info("Redis connection: OK")
    else:
        logger.error(
            "Redis connection FAILED — retry queue will not work. "
            "Check UPSTASH_REDIS_URL in .env"
        )

    logger.info("AI features active — Groq (llama3-8b-8192)")

    if settings.slack_webhook_url:
        logger.info("Slack alerting: configured")
    else:
        logger.warning("Slack alerting: NOT configured (SLACK_WEBHOOK_URL missing)")

    if settings.resend_api_key and settings.alert_email_to:
        logger.info("Email alerting: configured")
    else:
        logger.warning("Email alerting: NOT configured (RESEND_API_KEY or ALERT_EMAIL_TO missing)")

    if settings.supabase_key:
        logger.info("Auth: configured (anon key present)")
    else:
        logger.error(
            "Auth: SUPABASE_KEY missing — every protected "
            "route will fail token verification"
        )

    logger.info("=" * 50)
    start_scheduler()

# ── Shutdown ──
@app.on_event("shutdown")
async def on_shutdown():
    stop_scheduler()
    logger.info("Webhook Monitor shut down")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)