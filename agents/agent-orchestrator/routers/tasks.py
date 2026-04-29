from fastapi import APIRouter, HTTPException
from managers import task_executor as executor

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("")
def list_tasks():
    """List all tasks defined in tasks.json with their current state."""
    return {"tasks": executor.get_all()}


@router.get("/{task_id}")
def get_task(task_id: str):
    task = executor.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return task


@router.post("/{task_id}/run")
def run_task(task_id: str):
    """Trigger a task immediately (works for any schedule type)."""
    if not executor.trigger(task_id):
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return {"ok": True, "task_id": task_id, "message": "Task dispatched"}
