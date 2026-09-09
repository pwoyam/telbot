"""
Health check endpoint for monitoring and load balancers.

Exposes:
- /health: Basic liveness check
- /ready: Readiness check (includes database connectivity)
- /metrics: Basic metrics (request counts, uptime, etc.)

Designed to work alongside the main Telegram bot on a separate port.
"""
import asyncio
import logging
import time
import json
from datetime import datetime, timezone
from typing import Dict, Any

from aiohttp import web

logger = logging.getLogger(__name__)


class HealthServer:
    """Lightweight HTTP server for health checks and metrics."""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8080):
        self.host = host
        self.port = port
        self.start_time = time.time()
        self._stats: Dict[str, int] = {
            "requests_processed": 0,
            "errors": 0,
            "searches": 0,
            "inline_queries": 0,
        }
        self._app = None
        self._runner = None
        self._site = None
    
    def increment(self, counter: str):
        """Increment a counter."""
        if counter in self._stats:
            self._stats[counter] += 1
    
    def get_uptime(self) -> float:
        """Get uptime in seconds."""
        return time.time() - self.start_time
    
    async def handle_health(self, request: web.Request) -> web.Response:
        """Basic liveness check - always returns 200 if server is up."""
        return web.json_response({
            "status": "healthy",
            "uptime_seconds": round(self.get_uptime(), 2),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    
    async def handle_ready(self, request: web.Request) -> web.Response:
        """
        Readiness check - verifies database connectivity.
        Returns 503 if not ready.
        """
        try:
            from database import get_connection
            conn = await get_connection()
            cursor = await conn.execute("SELECT 1")
            await cursor.fetchone()
            
            return web.json_response({
                "status": "ready",
                "database": "connected",
                "uptime_seconds": round(self.get_uptime(), 2),
            })
        except Exception as e:
            logger.error("Readiness check failed: %s", e)
            return web.json_response(
                {
                    "status": "not_ready",
                    "error": str(e),
                },
                status=503
            )
    
    async def handle_metrics(self, request: web.Request) -> web.Response:
        """Expose basic metrics in JSON format."""
        return web.json_response({
            "uptime_seconds": round(self.get_uptime(), 2),
            "stats": self._stats,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    
    async def handle_root(self, request: web.Request) -> web.Response:
        """Root endpoint with links to other endpoints."""
        return web.json_response({
            "service": "telbot-health",
            "endpoints": {
                "/health": "Liveness check",
                "/ready": "Readiness check",
                "/metrics": "Basic metrics",
            }
        })
    
    async def start(self):
        """Start the health server."""
        self._app = web.Application()
        self._app.router.add_get('/', self.handle_root)
        self._app.router.add_get('/health', self.handle_health)
        self._app.router.add_get('/ready', self.handle_ready)
        self._app.router.add_get('/metrics', self.handle_metrics)
        
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()
        
        logger.info("🏥 Health server started on http://%s:%d", self.host, self.port)
    
    async def stop(self):
        """Stop the health server gracefully."""
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()
        logger.info("🏥 Health server stopped")


# Global health server instance
health_server = HealthServer()
