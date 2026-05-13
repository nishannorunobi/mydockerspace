"""
claude-code-proxy — thin HTTP wrapper around `claude -p` on the host.

Agents inside Docker call this at http://host.docker.internal:8892
to use the Claude Code subscription as a cloud LLM layer.

POST /chat   { "messages": [...], "system": "..." }
             → { "content": "...", "model": "claude-code" }

GET  /health → { "status": "ok" }
"""
import json
import os
import subprocess
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

PORT = int(os.environ.get("PORT", 8892))

CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")   # resolved from PATH by default

app = FastAPI(title="claude-code-proxy", docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class ChatRequest(BaseModel):
    messages: list
    system:   str = ""


@app.get("/health")
def health():
    import shutil
    resolved = shutil.which(CLAUDE_BIN) or CLAUDE_BIN
    return {"status": "ok", "claude_bin": resolved, "bin_exists": bool(shutil.which(CLAUDE_BIN))}


@app.post("/chat")
def chat(body: ChatRequest):
    import shutil
    if not shutil.which(CLAUDE_BIN):
        raise HTTPException(status_code=503, detail=f"claude binary not found: {CLAUDE_BIN}")

    # Flatten message history into a single prompt string
    parts = []
    for m in body.messages:
        role    = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                p.get("text", "") or p.get("content", "")
                for p in content if isinstance(p, dict)
            )
        if content:
            parts.append(f"[{role.upper()}]: {content}")

    prompt = "\n".join(parts).strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="empty prompt")

    cmd = [
        CLAUDE_BIN,
        "--print",
        "--output-format", "json",
        "--dangerously-skip-permissions",
        "--no-session-persistence",
    ]
    if body.system:
        cmd += ["--system-prompt", body.system[:2000]]

    cmd.append(prompt)

    try:
        # Run from /tmp so claude finds no CLAUDE.md/git context to scan
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd="/tmp")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="claude timed out after 120s")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if result.returncode != 0:
        raise HTTPException(
            status_code=502,
            detail=f"claude exited {result.returncode}: {result.stderr[:300]}",
        )

    try:
        data = json.loads(result.stdout)
        text = data.get("result", data.get("content", result.stdout))
    except json.JSONDecodeError:
        text = result.stdout.strip()

    return {"content": text, "model": "claude-code"}


if __name__ == "__main__":
    import uvicorn
    print(f"claude-code-proxy → http://0.0.0.0:{PORT}")
    uvicorn.run("server:app", host="0.0.0.0", port=PORT, reload=False)
