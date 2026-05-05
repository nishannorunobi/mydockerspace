"""
Services router — returns all declared web URLs with live reachability status.

GET /api/services   → list of {name, url, agent_id, agent_name, reachable}
"""
import socket
import urllib.request
from urllib.parse import urlparse

from fastapi import APIRouter
import agent_registry as registry

router = APIRouter(prefix="/services", tags=["services"])


def _reachable(url: str, health_url: str | None = None) -> bool:
    check = health_url or url
    parsed = urlparse(check)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        s = socket.create_connection((host, port), timeout=2)
        s.close()
        return True
    except Exception:
        return False


@router.get("")
def list_services():
    result = []
    for spec in registry.AGENT_SPECS:
        for svc in spec.services:
            result.append({
                "name":       svc["name"],
                "url":        svc["url"],
                "agent_id":   spec.id,
                "agent_name": spec.name,
                "reachable":  _reachable(svc["url"], svc.get("health_url")),
            })
    return {"services": result}
