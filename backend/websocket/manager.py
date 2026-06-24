# ws_manager.py
# ─────────────────────────────────────────────
# Central WebSocket connection manager.
#
# Holds every currently-connected browser tab and
# exposes one function — broadcast() — that the rest
# of the app calls whenever something worth showing
# live happens. None of the existing Phase 1-4 logic
# needs to know HOW WebSockets work; it just calls
# broadcast("event_type", {...}) and this file handles
# the rest.
# ─────────────────────────────────────────────

import json
import logging
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Tracks every active WebSocket connection and can
    push the same message to all of them at once.

    This app has no per-user accounts yet, so every
    connected browser sees every broadcast — there's
    no "rooms" or per-user filtering, just one shared
    list of connections.
    """

    def __init__(self):
        self.active_connections: list[WebSocket] = []
    
    async def connect(self, websocket):
        await websocket.accept()
        self.active_connections.append(websocket)

        print("WEBSOCKET CONNECTED")
        print("Active:", len(self.active_connections))

    async def connect(self, websocket: WebSocket):
        """Accept a new browser connection and track it"""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(
            f"WebSocket connected — "
            f"{len(self.active_connections)} active"
        )

    def disconnect(self, websocket: WebSocket):
        """Remove a connection that closed or errored"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(
            f"WebSocket disconnected — "
            f"{len(self.active_connections)} active"
        )

    async def broadcast(self, event_type: str, data: dict):
        """
        Send a message to every connected browser.

        event_type examples:
            "webhook_received", "health_status_changed",
            "delivery_retrying", "delivery_failed",
            "ai_diagnosis_ready"

        data is whatever payload makes sense for that
        event type — the frontend switches on event_type
        to decide how to handle it.
        """
        if not self.active_connections:
            # Nobody's watching the dashboard right now —
            # nothing to do, and that's perfectly fine.
            return

        message = json.dumps({
            "type": event_type,
            "data": data
        })

        # Send to every connection. If one has gone stale
        # (browser closed without a clean disconnect), track
        # it for removal instead of letting one bad connection
        # break the broadcast for everyone else.
        dead_connections = []

        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                dead_connections.append(connection)

        for dead in dead_connections:
            self.disconnect(dead)


# ── One shared instance, imported everywhere ──
manager = ConnectionManager()


async def broadcast(event_type: str, data: dict):
    """
    Convenience wrapper so other files can just do:
        from ws_manager import broadcast
        await broadcast("webhook_received", {...})

    instead of importing the manager instance directly.
    """
    await manager.broadcast(event_type, data)