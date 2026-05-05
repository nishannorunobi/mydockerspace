# Open Concerns & Flagged Anomalies
_Last updated: 2026-05-05 (Autonomous maintenance cycle #3)_

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

### C-013 — `dashboard-agent/` deleted from git index but not committed
- **File:** `agents/dashboard-agent/` (24 files staged as deleted in git status)
- **Context:** Commit `42656d6` moved dashboard-agent to `agents/agent-orchestrator/`. Deletions are correct but uncommitted.
- **Risk:** Low — agent-orchestrator is HEALTHY on port 8888. But git index is dirty.
- **Fix:** `git add -A && git commit -m "remove stale dashboard-agent path"`
- **Status:** OPEN — still dirty as of 2026-05-05 cycle #3

### C-014 — Large batch of uncommitted modifications (897 insertions, 16 files)
- **Files modified since last commit `c9dc3ac`:**
  - `agents/agent-orchestrator/` — agents.conf, agent_registry.py, routers/agents.py, routers/chat.py, server.py, static/css/style.css, static/index.html, static/js/dashboard.js
  - `agents/docker-manager-agent/docker_agent/` — monitor.py (start/stop/db-agent autostart), server.py (new endpoints + db-agent proxy), tools.py (extended)
  - `agents/docker-manager-agent/docker_agent/memory/` — docker_status.json, events.db (runtime data)
  - `.claude/settings.json`
- **Untracked:** `agents/agent-orchestrator/routers/config.py` (new API key management router)
- **All syntax checks pass** — no broken files found
- **No hardcoded IPs** — all container refs use names
- **Risk:** Significant feature work uncommitted. Changes lost on branch reset.
- **Fix:** Owner should commit: `git add agents/agent-orchestrator/ agents/docker-manager-agent/ .claude/settings.json && git commit -m "..."`
- **Status:** UPDATED from C-014 (was workspace-agent changes) — now covers full agent feature batch

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

### C-016 — UMS `/actuator/health` returns HTTP 500 (NEW)
- **Container:** `ums-app` (Spring Boot 3 / Java 21)
- **Issue:** `GET /actuator/health` → 500. Log shows: `NoResourceFoundException: No static resource actuator/health.` — Spring Boot Actuator is not enabled or not exposed on the management port.
- **Impact:** claude-agent health.sh marks UMS as OK (uses HTTP 500 as "reachable") but Actuator metrics/health are inaccessible. Monitoring blind spot.
- **API is functional:** `GET /api/v1/users` returns correct data. Application itself is working.
- **Fix:** Add to `application.properties` or `application.yml`: `management.endpoints.web.exposure.include=health,info` — rebuild and redeploy ums-app.
- **Status:** NEW — identified 2026-05-05 cycle #3. Not auto-fixed (requires rebuild).

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

### C-012 — `docker-manager-agent` not started from agent-orchestrator start button
- **Previous status:** Agent was not started. Updated 2026-04-29: health.sh was HEALTHY, agent needed ./start.sh
- **Current status (2026-05-05):** Agent IS running on port 8889 ✅ — concern downgraded to monitoring
- **Status:** MONITORING — running; flag if it goes down again

---

## ✅ RESOLVED

### C-015 — `ums-app` and `mypostgresql_db-container` were exited ✅ RESOLVED 2026-05-05
- Both containers are now running (Up 55+ min each as of cycle #3)
- Exit codes 143/137 from previous cycle were clean/forced shutdowns, not crashes
