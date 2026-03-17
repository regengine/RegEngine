"""Shared health check utilities for RegEngine.

Supports standard Phase 17/18 HealthCheck class and legacy health functions.
"""

from typing import Dict, Any, List, Optional, Callable
from fastapi import FastAPI, APIRouter
from fastapi.responses import JSONResponse
import inspect
import time
import socket
import os

class HealthCheck:
    """Standardized health check manager (Phase 17)."""
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.start_time = time.time()
        self._dependencies: Dict[str, Callable] = {}

    def add_dependency(self, name: str, check_fn: Callable):
        self._dependencies[name] = check_fn

    async def check(self) -> Dict[str, Any]:
        results = {}
        status = "healthy"
        for name, fn in self._dependencies.items():
            try:
                res = await fn() if inspect.iscoroutinefunction(fn) else fn()
                results[name] = res
                if res.get("status") != "healthy":
                    status = "unhealthy"
            except Exception as e:
                results[name] = {"status": "unhealthy", "error": str(e)}
                status = "unhealthy"

        return {
            "service": self.service_name,
            "status": status,
            "version": os.getenv("VERSION", "1.0.0"),
            "hostname": socket.gethostname(),
            "uptime": time.time() - self.start_time,
            "dependencies": results
        }

def install_health_router(app: FastAPI, service_name: str, health_check: Optional[HealthCheck] = None):
    """Install standard /health and /ready routes."""
    router = APIRouter(tags=["Health"])
    hc = health_check or HealthCheck(service_name)
    
    @router.get("/health")
    async def get_health():
        return await hc.check()

    @router.get("/ready")
    async def get_ready():
        res = await hc.check()
        return res if res["status"] == "healthy" else JSONResponse(status_code=503, content=res)

    app.include_router(router)

# --- Legacy Health Functions (for backward compatibility) ---
def check_health() -> Dict[str, Any]:
    return {"status": "healthy", "timestamp": time.time()}
