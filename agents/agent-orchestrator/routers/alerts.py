import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter

import alert_engine as alert_eng

router = APIRouter(prefix="/alerts", tags=["alerts"])

# CONFIG_DIR is set by server.py after import
CONFIG_DIR: Path = Path(__file__).parent.parent / "config"


@router.get("/settings")
async def get_settings():
    path = CONFIG_DIR / "alerts.json"
    return json.loads(path.read_text()) if path.exists() else {}


@router.put("/settings")
async def update_settings(body: dict):
    CONFIG_DIR.mkdir(exist_ok=True)
    (CONFIG_DIR / "alerts.json").write_text(json.dumps(body, indent=2))
    return {"ok": True}


@router.post("/test/{alert_type}")
async def test_alert(alert_type: str):
    alert_eng.broadcast({
        "type":       "alert",
        "id":         "test",
        "alert_type": alert_type,
        "severity":   "critical" if alert_type == "alarm" else "warning",
        "agent_id":   "test",
        "agent_name": "Test",
        "message":    f"Test alert: {alert_type}",
        "ts":         datetime.now().isoformat(),
    })
    return {"ok": True}
