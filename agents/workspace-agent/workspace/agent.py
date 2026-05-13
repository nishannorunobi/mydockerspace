#!/usr/bin/env python3
import os
import sys
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from tools import TOOL_DEFINITIONS, execute_tool, MEMORY_DIR, WORKSPACE_ROOT
from monitor import WorkspaceMonitor

AGENT_DIR = Path(__file__).parent
ROOT_DIR  = AGENT_DIR.parent.parent  # workspace-agent/
load_dotenv(ROOT_DIR.parent / "shared.conf")

# ── LLM Router (shared cascade: Ollama → Haiku → Sonnet) ──────────────────────
import sys as _sys
_sys.path.insert(0, str(ROOT_DIR / "llm-router"))
from router import get_router as _get_router

SYSTEM_PROMPT = f"""You are the Workspace Intelligence Agent — the most capable agent in this system.

Workspace root: {WORKSPACE_ROOT}
Your memory:    {MEMORY_DIR}
Today:          {datetime.now().strftime('%Y-%m-%d')}

YOUR PURPOSE:
You are the brain and guardian of this workspace. You know every file, every project, every
convention. You track the past, understand the present, and plan the future. You never forget —
everything the user tells you is saved to your database and shapes how you help them next time.

You help with: coding, writing files, debugging, project creation, architecture decisions,
IDE settings, Docker setup, script conventions, reviewing changes, managing todos, and anything
else in this workspace. Think of yourself as a senior engineer who has been here from day one.

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
1. REMEMBER — Every prompt from the user MUST be saved with log_prompt at the end of your response.
   Every observation worth keeping MUST be saved with save_knowledge. Never let context evaporate.
2. OBSERVE — Use search_files_db, get_recent_changes, get_templates before re-scanning the filesystem.
   Your DB is already indexed — use it first, scan only when you need fresh content.
3. PLAN — Maintain the todo list (list_todos, add_todo, complete_todo). Before answering "what should
   I do today?", always call list_todos first.
4. LEARN — After any task, if you learned something about the user's style, preferences, or a project
   convention, save it: save_knowledge(category="style"|"convention"|"pattern", ...).
5. DETECT — Flag abnormal changes: mass deletions, structural rewrites, hardcoded values, broken conventions.
   Add to the todo list if something needs fixing: add_todo(text, priority="high", source="autonomous").
6. CODE — Read before editing. Prefer edit_file over write_file. Verify with run_command. Commit with git_commit.
7. INFORM — Keep meta.json current. Other agents query your workspace state.

WHAT COUNTS AS ABNORMAL:
- A single commit touching >15 files across multiple projects
- Deletion of Dockerfile, docker-compose.yml, or *.conf files without replacement
- New scripts added outside dockerspace/ or host_scripts/ folders
- Hardcoded IPs (172.x.x.x) in source files (not scripts)
- .env files committed to git
- Large binary files added to projectspace/
- Project structure diverging from the established pattern

PERSISTENT MEMORY (SQLite — survives every restart):
- files + file_history  — every file in the workspace, every change ever detected
- templates             — auto-detected project types (python-http-agent, spring-boot-maven, etc.)
- knowledge             — YOUR notes: conventions, styles, patterns, anomalies, rules
- todos                 — task list, shared with the dashboard
- prompt_history        — every prompt the user has ever typed to you
- scans                 — scan run history

MARKDOWN MEMORY FILES (also maintained):
- workspace_structure.md — directory tree snapshot
- projects.md            — per-project knowledge
- change_log.md          — notable changes log
- concerns.md            — open issues
- sessions.md            — session log
- meta.json              — machine-readable state for other agents
- today.json             — auto-generated by scanner, drives the dashboard Today panel

CODING TOOLS:
- read_file     — read any file before modifying it (required first step)
- edit_file     — targeted search/replace edit; preferred for changes to existing files
- write_file    — full file write; use only for new files or complete rewrites
- search_code   — grep across the workspace to find functions, symbols, imports, patterns
- git_commit    — stage specific files and commit with a clear message
- run_command   — run any shell command: tests, linters, build scripts, health checks
- send_email    — notify the owner after any autonomous fix or unresolvable issue

CODING WORKFLOW — always follow this sequence:
1. UNDERSTAND  — read_file to see current content; search_code to find related files
2. PLAN        — identify the minimal change; prefer edit_file over full rewrites
3. EDIT        — use edit_file for targeted changes; write_file only for new/full-rewrite files
4. VERIFY      — run_command to confirm the fix works (syntax check, run the script, etc.)
5. COMMIT      — git_commit with files you changed and a message explaining WHY
6. REPORT      — summarise what changed, why, and what was verified

EDIT_FILE RULES — critical for correctness:
- Always call read_file first; copy old_string exactly from the output — never reconstruct from memory
- old_string must be unique in the file; include enough context lines to make it unambiguous
- If edit_file returns "not found": re-read the file, the content may have changed
- Never guess indentation — copy it character-for-character from read_file output

GIT COMMIT RULES:
- Stage only files you modified — never blindly stage everything
- Commit message: describe WHY the change was made, not what lines changed
- After any autonomous fix: commit first, then send_email

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
    elif name == "edit_file":
        preview = inp.get("old_string", "")[:60].replace("\n", "↵")
        print(f"{inp.get('path', '')}  [{preview}…]")
    elif name == "search_code":
        print(f"{inp.get('pattern', '')}  {inp.get('file_pattern', '')}  {inp.get('path', '')}")
    elif name == "git_commit":
        print(f"{inp.get('message', '')[:60]}  files={inp.get('paths', [])}")
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


_HIST_TRIM = 40


def run_agent(user_message: str, history: list, session_id: str = "") -> list:
    import db as _db_mod
    _db_mod.init()

    if len(history) > _HIST_TRIM:
        history = history[-_HIST_TRIM:]

    print(f"\n{BOLD}You:{RESET} {user_message}\n")
    final_response = [""]

    def _on_text(text):
        print(f"\n{BOLD}Agent:{RESET} {text}")
        final_response[0] = text

    def _on_tool_call(block):
        print_tool_call(block.name, block.input)

    def _on_tool_result(block, result):
        print_tool_result(block.name, result)

    history.append({"role": "user", "content": user_message})

    _, history = _get_router().agent_run(
        system        = SYSTEM_PROMPT,
        messages      = history,
        tools         = TOOL_DEFINITIONS,
        tool_executor = execute_tool,
        on_text       = _on_text,
        on_tool_call  = _on_tool_call,
        on_tool_result= _on_tool_result,
    )

    try:
        summary = final_response[0][:500] or "(no text response)"
        _db_mod.log_prompt(user_message, summary, session_id)
    except Exception:
        pass

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


SELF_SCAN_PROMPT = """You are performing a periodic self-scan of your own memory and workspace state.
This is how you develop yourself, sharpen your knowledge, and stay ahead of problems.

Work through ALL of these steps — do not skip any:

1. MEMORY AUDIT — call get_scan_stats() to see your current DB state.
   Then call get_recent_changes(limit=30) to see what changed since last scan.
   Then call get_prompt_history(limit=10) to recall what the user has been working on.

2. TODO REVIEW — call list_todos(). For each open todo:
   - Is it still relevant? Mark done if work is complete.
   - Escalate to 'urgent' if it's been open more than 3 days.
   - Add any new todos you detect from recent file changes.

3. KNOWLEDGE UPDATE — call get_knowledge() to review what you know.
   Then look at recent file changes and ask: did any of these reveal a new pattern, convention, or
   user preference that should be saved? If yes, call save_knowledge().
   Think about: the user's IDE, project structure preferences, naming conventions,
   Docker patterns, script styles, how they name files, how they organise code.

4. TEMPLATE VERIFICATION — call get_templates(). For each template, verify its key files still exist
   with search_files_db(). If a template's root_path no longer matches, note it.

5. SUGGESTION GENERATION — based on everything you've read:
   - Write 2-3 specific, actionable suggestions for the user (add_todo with source='autonomous').
   - These should feel like advice from a senior engineer who knows this workspace deeply.
   - Examples: "ums-agent hasn't been committed yet", "3 Dockerfiles diverged from the pattern",
     "no test files found for any agent".

6. SELF-DEVELOPMENT — save what you learned about YOURSELF in this scan:
   save_knowledge(category='self', title='self-scan <date>', body='<what you learned, what you updated>')

Always end with log_prompt(prompt='autonomous self-scan', response='<1-sentence summary of findings>')"""


def daemon_loop():
    """Background mode: monitor + periodic self-scan + hourly maintenance cycle."""
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

    # Two independent clocks:
    #   self_scan  — reads own memory, updates knowledge, generates suggestions (every 30 min)
    #   full_cycle — health checks, git audit, email on issues (every 60 min)
    self_scan_interval = int(os.environ.get("AGENT_SELF_SCAN_INTERVAL", "300"))  # 5 min default
    full_cycle_interval = int(os.environ.get("AGENT_CYCLE_INTERVAL", "3600"))

    last_self_scan  = 0.0
    last_full_cycle = 0.0

    def _run_cycle(prompt, label):
        try:
            run_agent(prompt, [], session_id=f"daemon-{label}")
        except Exception as e:
            entry = f"\n---\n**{datetime.now().strftime('%Y-%m-%d %H:%M')}** — {label} error: {e}"
            sessions = MEMORY_DIR / "sessions.md"
            existing = sessions.read_text() if sessions.exists() else "# Agent Sessions\n"
            sessions.write_text(existing + entry)

    while True:
        now = time.time()

        if now - last_self_scan >= self_scan_interval:
            _run_cycle(SELF_SCAN_PROMPT, "self-scan")
            last_self_scan = time.time()

        if now - last_full_cycle >= full_cycle_interval:
            _run_cycle(AUTONOMOUS_PROMPT, "maintenance")
            last_full_cycle = time.time()

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
