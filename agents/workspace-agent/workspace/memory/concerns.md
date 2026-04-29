# Open Concerns & Flagged Anomalies
_Last updated: 2026-04-29 (Autonomous maintenance cycle #2)_

---

## 🔴 HIGH PRIORITY

### C-001 — `context.md` is stale
- **File:** `context.md`
- **Issue:** Still references `AlmaLinux 9`, `dnf`, `IMAGE_VERSION=1.3`, `ums-container/apigw-container` — but workspace.conf now shows `BASE_IMAGE=postgres:16`, `PKG_MANAGER=apt`, `IMAGE_VERSION=1.4`, `ums-app`
- **Risk:** Misleads Claude (or any reader) about the actual OS/environment and container names
- **Fix:** Update context.md to reflect current state: postgres:16 base, apt pkg manager, IMAGE_VERSION=1.4, PROJECT_NAME=mypostgresql_db, container=ums-app
- **Status:** OPEN — not fixed since Session 1

### C-002 — UMS `docker-compose.yml` references `.env` file ✅ PARTIALLY VERIFIED
- **File:** `projectspace/ums/dockerspace/host_scripts/docker-compose.yml`
- **Issue:** `env_file: ../../.env` — an `.env` file is used.
- **Verified 2026-04-29:** `ums/.gitignore` contains `.env` — credential leak risk is LOW. `.env` file exists on disk but is gitignored.
- **Remaining action:** Consider switching to `ums/project.conf` pattern to align with workspace convention.
- **Status:** PARTIALLY RESOLVED — gitignore confirmed; convention drift remains

---

## 🟡 MEDIUM PRIORITY

### C-012 — `docker-manager-agent` not built — server not on port 8889
- **File:** `agents/docker-manager-agent/`
- **Issue:** health.sh shows WARN: "Server not responding on port 8889 — run ./start.sh". Agent has .venv and shared.conf but is NOT started.
- **Update 2026-04-29 cycle #2:** health.sh now returns HEALTHY (exit 0) — .venv and keys exist. Agent simply needs `./start.sh` to be called.
- **Risk:** Agent is idle, not monitoring Docker. Non-critical but unused capacity.
- **Fix:** Run `cd agents/docker-manager-agent && ./start.sh`
- **Status:** UPDATED — was C-012 "never built"; now built but not started. Owner decision to start.

### C-013 — `dashboard-agent/` deleted from git index but not committed
- **File:** `agents/dashboard-agent/` (24 files staged as deleted in git status)
- **Context:** Commit `42656d6` moved dashboard-agent to `agents/agent-orchestrator/`. Deletions are correct but uncommitted.
- **Risk:** Low — agent-orchestrator is HEALTHY on port 8888. But git index is dirty.
- **Fix:** `git add -A && git commit -m "remove stale dashboard-agent path"`
- **Status:** OPEN — still dirty as of 2026-04-29 cycle #2

### C-014 — Several uncommitted modifications to workspace-agent
- **Files:** `agents/workspace-agent/health.sh`, `workspace/agent.py`, `workspace/tools.py`, `workspace/memory/change_log.md`, `workspace/memory/concerns.md`, `workspace/memory/sessions.md`
- **Untracked:** `agents/workspace-agent/start_daemon.sh`, `workspace/memory/daemon.log`
- **Context:** Additive improvements — daemon loop, new tool defs, daemon PID check. Not breakage.
- **Risk:** Changes lost on branch reset; `start_daemon.sh` not tracked by git
- **Fix:** `git add agents/workspace-agent/ && git commit -m "workspace-agent: daemon mode + new tools"`
- **Status:** OPEN — still dirty as of 2026-04-29 cycle #2

### C-003 — `mywritings.zip` in projectspace root
- **File:** `projectspace/mywritings.zip`
- **Issue:** Binary zip in projectspace root — wrong location
- **Fix:** Move to `mountspace/` or extract to `projectspace/mywrites/`
- **Status:** OPEN

### C-004 — `myapigw` has no `dockerspace/` structure
- **File:** `projectspace/myapigw/` — only README.md present
- **Issue:** Violates project convention (every project needs dockerspace/ with host_scripts/ and container_scripts/)
- **Status:** OPEN

### C-005 — `pc-maker` has no `dockerspace/`
- **File:** `projectspace/pc-maker/`
- **Risk:** Low — pc-maker is a native OS scripts collection
- **Status:** OPEN

### C-006 — `workspace-agent` scripts not in `dockerspace/host_scripts/`
- **File:** `workspace-agent/`
- **Issue:** Has build.sh, start.sh, stop.sh, health.sh directly in root — not in dockerspace/host_scripts/
- **Status:** OPEN

### C-010 — `claude-agent/host/` contains duplicate scripts outside `dockerspace/`
- **File:** `projectspace/ai-agents/claude-agent/host/`
- **Issue:** Duplicate build.sh, health.sh, start.sh, stop.sh outside dockerspace/host_scripts/
- **Status:** OPEN

### C-011 — `linux-lite-7.8-64bit.iso` binary in pc-maker
- **File:** `projectspace/pc-maker/ossetup/debian2debian/linux-lite-7.8-64bit.iso`
- **Issue:** Large binary ISO stored in projectspace
- **Fix:** Move to `mountspace/`
- **Status:** OPEN

### C-015 — `ums-app` and `mypostgresql_db-container` are exited (not running)
- **Containers:** `ums-app` (Exited 143, ~47h ago), `mypostgresql_db-container` (Exited 137, ~2 days ago)
- **Impact:** claude-agent health.sh reports UNHEALTHY — PostgreSQL down, Agent DB schema inaccessible
- **Note:** Exit codes 143 (SIGTERM) and 137 (SIGKILL/OOM) suggest clean/forced shutdowns, not crashes
- **Risk:** UMS API and DB are unavailable. claude-agent cannot run tests.
- **Fix:** Owner should restart: `cd projectspace/mypostgresql_db/dockerspace/host_scripts && ./start.sh` then `cd projectspace/ums/dockerspace/host_scripts && ./start_docker.sh`
- **Status:** NEW — identified 2026-04-29 cycle #2. NOT auto-started (service start requires owner decision).

---

## 🟢 LOW PRIORITY / MONITORING

### C-007 — Uncommitted changes to `dockerspace/project.conf` and `.vscode/settings.json`
- **File:** `dockerspace/project.conf`, `.vscode/settings.json`
- **Details:** Stray `r` typo in project.conf comment separator (line 17); LaTeX outDir setting in .vscode
- **Verified 2026-04-29:** `bash -n project.conf` passes — typo is cosmetic only, inside a comment
- **Status:** OPEN — still dirty, but non-functional

### C-009 — `mypostgresql_db/dockerspace/project.conf` EXPOSE_PORTS=8085:8085
- **File:** `projectspace/mypostgresql_db/dockerspace/project.conf`
- **Issue:** PostgreSQL standard port is 5432, not 8085
- **Status:** OPEN

---

## ✅ RESOLVED
_(none yet)_
