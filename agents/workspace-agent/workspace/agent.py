#!/usr/bin/env python3
import os
import sys
import json
from pathlib import Path
from datetime import datetime
import anthropic
from dotenv import load_dotenv
from tools import TOOL_DEFINITIONS, execute_tool, MEMORY_DIR, WORKSPACE_ROOT
from monitor import WorkspaceMonitor

AGENT_DIR = Path(__file__).parent
ROOT_DIR  = AGENT_DIR.parent.parent  # workspace-agent/
load_dotenv(ROOT_DIR.parent / "shared.conf")

SYSTEM_PROMPT = f"""You are a Workspace Management Agent for a Docker-based development workspace.

Workspace root: {WORKSPACE_ROOT}
Your memory:    {MEMORY_DIR}
Today:          {datetime.now().strftime('%Y-%m-%d')}

YOUR PURPOSE:
You are the guardian of this workspace. You understand its structure, track its evolution,
detect problems early, and ensure it stays clean, purposeful, and easy to clone and resume.

WORKSPACE STRUCTURE YOU KNOW:
- dockerspace/        — workspace-level Docker setup (Dockerfile, workspace.conf, scripts)
- claude/             — Claude CLI config, shared across host and container
- projectspace/       — all active projects (gitignored from main repo)
  - ums/              — Spring Boot 3 / Java 21 User Management System API
  - mypostgresql_db/  — PostgreSQL 16 dev container for UMS database
  - ai-agents/
    - claude-agent/   — Claude API testing agent (tests UMS endpoints)
  - myapigw/          — API gateway project
  - pc-maker/         — PC setup and OS scripts
  - mywrites/         — Academic/writing projects
- mountspace/         — local files, never committed
- workspace-agent/    — YOU live here

PROJECT CONVENTIONS (always enforce):
- Every project has a dockerspace/ folder with host_scripts/ and container_scripts/
- Scripts follow the pattern: build.sh, start.sh, stop.sh, health.sh, login_docker.sh
- Shared Docker network: ums-network
- Config files: agent.conf (not .env) for AI agents, project.conf for workspace containers
- Host stays clean — everything runs in Docker
- No hardcoded IPs — use container names on shared networks

YOUR RESPONSIBILITIES:
1. OBSERVE — Scan structure and git history to understand current state
2. REMEMBER — Always save key observations to memory/ before ending a session
3. DETECT — Flag abnormal changes: mass deletions, structural rewrites, files in wrong places,
   hardcoded values, broken conventions
4. ADVISE — Suggest specific improvements with clear reasoning
5. INFORM — Keep meta.json updated so other agents (like claude-agent) know the workspace state
6. TRACK — Log notable changes with timestamps in change_log.md

WHAT COUNTS AS ABNORMAL:
- A single commit touching >15 files across multiple projects
- Deletion of Dockerfile, docker-compose.yml, or *.conf files without replacement
- New scripts added outside dockerspace/ or host_scripts/ folders
- Hardcoded IPs (172.x.x.x) in source files (not scripts)
- .env files committed to git
- Large binary files added to projectspace/
- Project structure diverging from the established pattern

MEMORY FILES YOU MAINTAIN:
- workspace_structure.md — last known directory tree snapshot
- projects.md            — per-project knowledge (purpose, stack, status, conventions)
- change_log.md          — log of notable changes with dates (also auto-updated by monitor)
- concerns.md            — open issues and flagged anomalies
- sessions.md            — log of agent sessions
- meta.json              — machine-readable summary for other agents

ACTIONS YOU CAN TAKE:
- run_command   — run any Linux shell command; use to test, verify, and diagnose
- write_file    — fix a broken file; always read first, change minimally, re-run to verify
- send_email    — notify the owner; required after any autonomous fix or unresolvable issue

IMPORTANT:
- Always read relevant memory files before making assessments
- Always save findings to memory before ending a session
- Be specific in suggestions — name the file, the line, the pattern
- Keep meta.json current — other agents depend on it
- When running autonomously: fix only what is clearly broken; email the owner after every change
"""

BOLD   = "\033[1m"
GREEN  = "\033[32m"
RED    = "\033[31m"
CYAN   = "\033[36m"
DIM    = "\033[2m"
YELLOW = "\033[33m"
RESET  = "\033[0m"


def print_tool_call(name: str, inp: dict):
    print(f"\n  {CYAN}[{name}]{RESET}", end=" ")
    if name == "scan_workspace":
        print(f"depth={inp.get('max_depth', 4)} path={inp.get('path', '/')}")
    elif name == "read_file":
        print(inp.get("path", ""))
    elif name in ("git_log", "git_status", "git_diff"):
        print(inp.get("path", "workspace") + (f" commit={inp['commit']}" if inp.get("commit") else ""))
    elif name in ("write_memory", "read_memory"):
        print(inp.get("filename", ""))
    elif name == "update_meta":
        print(f"keys={list(inp.get('meta', {}).keys())}")
    else:
        print()


def print_tool_result(name: str, result: dict):
    if result.get("error"):
        print(f"  {RED}  → error: {result['error']}{RESET}")
    elif name == "scan_workspace":
        lines = result.get("tree", "").split("\n")
        for line in lines[:30]:
            print(f"  {DIM}  {line}{RESET}")
        if len(lines) > 30:
            print(f"  {DIM}  ... +{len(lines)-30} more{RESET}")
    elif name in ("git_log", "git_diff"):
        out = result.get("log") or result.get("diff", "")
        for line in out.split("\n")[:15]:
            print(f"  {DIM}  {line}{RESET}")
    elif name == "write_memory":
        print(f"  {GREEN}  → saved: {result.get('saved')}{RESET}")
    elif name == "update_meta":
        print(f"  {GREEN}  → meta.json updated{RESET}")
    elif name == "list_memory":
        print(f"  {DIM}  {result.get('files', [])}{RESET}")
    else:
        preview = str(result)[:120]
        print(f"  {DIM}  → {preview}{RESET}")


def log_session(note: str):
    entry = f"\n---\n**{datetime.now().strftime('%Y-%m-%d %H:%M')}** — {note}"
    sessions = MEMORY_DIR / "sessions.md"
    existing = sessions.read_text() if sessions.exists() else "# Agent Sessions\n"
    sessions.write_text(existing + entry)


def run_agent(user_message: str, history: list) -> list:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    history.append({"role": "user", "content": user_message})
    print(f"\n{BOLD}You:{RESET} {user_message}\n")

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8096,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=history
        )

        tool_calls  = [b for b in response.content if b.type == "tool_use"]
        text_blocks = [b for b in response.content if b.type == "text"]

        for block in text_blocks:
            if block.text.strip():
                print(f"\n{BOLD}Agent:{RESET} {block.text}")

        if response.stop_reason == "end_turn" or not tool_calls:
            final = " ".join(b.text for b in text_blocks if b.type == "text").strip()
            if final:
                history.append({"role": "assistant", "content": final})
            break

        history.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in tool_calls:
            print_tool_call(block.name, block.input)
            result = execute_tool(block.name, block.input)
            print_tool_result(block.name, result)
            tool_results.append({
                "type":        "tool_result",
                "tool_use_id": block.id,
                "content":     json.dumps(result)
            })

        history.append({"role": "user", "content": tool_results})

    print()
    return history


def chat_loop():
    MEMORY_DIR.mkdir(exist_ok=True)

    print(f"\n{BOLD}╔══════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}║     Workspace Management Agent           ║{RESET}")
    print(f"{BOLD}║     {str(WORKSPACE_ROOT):<38}║{RESET}")
    print(f"{BOLD}╚══════════════════════════════════════════╝{RESET}")
    print(f"{DIM}Type your request or 'exit' to quit.{RESET}")
    print(f"{DIM}Suggested: 'scan and update memory' | 'check for issues' | 'what changed recently?'{RESET}")
    print(f"{DIM}Background monitor active — silently tracking workspace changes every {WorkspaceMonitor.INTERVAL}s.{RESET}\n")

    monitor = WorkspaceMonitor(workspace_root=WORKSPACE_ROOT, memory_dir=MEMORY_DIR)
    monitor.start()

    log_session("session started")
    history = []

    try:
        while True:
            try:
                user_input = input(f"{BOLD}>{RESET} ").strip()
            except (EOFError, KeyboardInterrupt):
                print(f"\n{DIM}Session ended.{RESET}")
                log_session("session ended by user")
                break

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit"):
                log_session("session ended")
                print("Bye.")
                break

            history = run_agent(user_input, history)
    finally:
        monitor.stop()


AUTONOMOUS_PROMPT = """You are running a scheduled autonomous maintenance cycle. Work through these steps:

1. Run health checks — find and execute any health.sh scripts for active services (docker ps, ./health.sh, etc.)
2. Check git status for recent uncommitted or suspicious changes
3. If a command fails (non-zero exit code): read the relevant file, identify the exact problem, fix it with write_file, then re-run to confirm
4. Only fix things you are certain about — wrong port, syntax error, missing directory, bad path. If unsure, log to concerns.md instead
5. After any fix OR if you found an issue you could not resolve, send an email: what was broken, file changed, old vs new value, verification result
6. Update sessions.md with a one-line summary of what happened this cycle

Be minimal — do not reorganize, refactor, or improve things. Only fix actual failures."""


def daemon_loop():
    """Background mode: monitor + hourly autonomous AI maintenance cycle."""
    import signal
    import time

    MEMORY_DIR.mkdir(exist_ok=True)
    log_session("daemon started")

    monitor = WorkspaceMonitor(workspace_root=WORKSPACE_ROOT, memory_dir=MEMORY_DIR)
    monitor.start()

    def _shutdown(sig, frame):
        log_session("daemon stopped")
        monitor.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT,  _shutdown)

    cycle_interval = int(os.environ.get("AGENT_CYCLE_INTERVAL", "3600"))
    last_cycle = 0.0

    while True:
        now = time.time()
        if now - last_cycle >= cycle_interval:
            try:
                run_agent(AUTONOMOUS_PROMPT, [])
            except Exception as e:
                entry = f"\n---\n**{datetime.now().strftime('%Y-%m-%d %H:%M')}** — autonomous cycle error: {e}"
                sessions = MEMORY_DIR / "sessions.md"
                existing = sessions.read_text() if sessions.exists() else "# Agent Sessions\n"
                sessions.write_text(existing + entry)
            last_cycle = time.time()
        time.sleep(60)


if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(f"{RED}Error:{RESET} ANTHROPIC_API_KEY not set in agent.conf")
        sys.exit(1)

    MEMORY_DIR.mkdir(exist_ok=True)

    if "--daemon" in sys.argv:
        daemon_loop()
    elif len(sys.argv) > 1:
        run_agent(" ".join(sys.argv[1:]), [])
    else:
        chat_loop()
