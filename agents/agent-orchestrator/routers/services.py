"""
Services router — returns all declared web URLs with live reachability status.

GET /api/services   → list of {name, url, agent_id, agent_name, reachable}
"""
import urllib.request
import urllib.error

from fastapi import APIRouter
import agent_registry as registry

router = APIRouter(prefix="/services", tags=["services"])


def _reachable(url: str, health_url: str | None = None) -> bool:
    check = health_url or url
    try:
        urllib.request.urlopen(check, timeout=2)
        return True
    except urllib.error.HTTPError:
        # Server responded with an HTTP error (4xx/5xx) — it's still up
        return True
    except Exception:
        # Connection refused, timeout, empty response (e.g. socat→nothing), etc.
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
