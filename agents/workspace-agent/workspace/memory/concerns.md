# Open Concerns & Flagged Anomalies
_Last updated: 2026-05-05 (Autonomous maintenance cycle #5)_

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
- **Verified 2026-05-05 cycle #5:** `git ls-files "*.env"` returns empty — no .env files tracked in git ✅
- **Remaining action:** Consider switching to `ums/project.conf` pattern to align with workspace convention.
- **Status:** PARTIALLY RESOLVED — gitignore confirmed; convention drift remains

---

## 🟡 MEDIUM PRIORITY

### C-013 — `dashboard-agent/` deleted from git index but not committed
- **File:** `agents/dashboard-agent/` (24 files staged as deleted in git status)
- **Context:** Commit `42656d6` moved dashboard-agent to `agents/agent-orchestrator/`. Deletions are correct but uncommitted.
- **Risk:** Low — agent-orchestrator is HEALTHY on port 8888. But git index is dirty.
- **Fix:** Owner should commit these deletions along with C-014 feature work
- **Status:** OPEN — still dirty as of 2026-05-05 cycle #5

### C-014 — Large batch of uncommitted modifications (1,358 insertions, 21 files)
- **Files modified since last commit `c9dc3ac` (2026-04-29):**
  - `agents/agent-orchestrator/` — agents.conf, connectors/http.py, routers/events.py, static/css/style.css, static/index.html, static/js/dashboard.js
  - `agents/docker-manager-agent/docker_agent/` — agent.py, database.py (NEW), monitor.py, server.py, tools.py
  - `agents/docker-manager-agent/docker_agent/memory/docker_status.json` — runtime data
  - `agents/docker-manager-agent/docker_agent/memory/events.db` — runtime data (binary)
  - `agents/docker-manager-agent/server.conf` — BELL_RINGS config added
  - `.claude/settings.json` — permission list expanded
  - `agents/workspace-agent/workspace/` — monitor.py, tools.py, memory files
- **New untracked files (all syntax ✅):**
  - `agents/workspace-agent/workspace/db.py` — SQLite database module
  - `agents/workspace-agent/workspace/scanner.py` — background workspace scanner
  - `agents/workspace-agent/workspace/memory/scan_status.md` — scanner output
  - `agents/workspace-agent/workspace/memory/workspace.db` — SQLite DB (binary, should be gitignored)
- **All syntax checks pass** — no broken files found
- **No hardcoded IPs in code** — one comment-only reference at server.py:367 (safe)
- **Risk:** Significant feature work (db.py + scanner.py = new persistence layer for workspace-agent). workspace.db binary not in .gitignore — should be checked.
- **Fix:** Owner should commit feature work; ensure workspace.db is in .gitignore
- **Status:** UPDATED cycle #5 — db.py and scanner.py are new additions (workspace scanner feature)

### C-017 — `workspace.db` binary may not be gitignored (NEW — cycle #5)
- **File:** `agents/workspace-agent/workspace/memory/workspace.db`
- **Issue:** This SQLite binary is untracked (`??`) in git status — which is correct behaviour IF it is in .gitignore. Needs verification that .gitignore covers it.
- **Risk:** If not gitignored, the binary could be accidentally committed on next `git add -A`
- **Fix:** Verify `agents/workspace-agent/.gitignore` or root `.gitignore` covers `*.db` / `workspace.db`; add if missing
- **Status:** NEW — flagged cycle #5, not yet verified

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

### C-016 — UMS `/actuator/health` returns HTTP 500 (confirmed cycle #5)
- **Container:** `ums-app` (Spring Boot 3 / Java 21) — Up 27 min as of this cycle
- **Root cause confirmed:** `spring-boot-starter-actuator` is **not present in pom.xml** at all.
- **API is functional:** `GET /api/v1/users` → HTTP 200 ✅. Application working correctly.
- **Impact:** No Actuator health/metrics available. health.sh shows failures from host (expected — runs outside container). UMS ums-agent/health.sh reports FAIL for this reason.
- **Fix:** Add `spring-boot-starter-actuator` to pom.xml, expose endpoint in application.yml, rebuild ums-app.
- **Status:** CONFIRMED cycle #5 — not auto-fixed (requires pom.xml change + rebuild + redeploy)

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

### C-012 — `docker-manager-agent` agent monitoring
- **Current status (2026-05-05 cycle #5):** Agent IS running on port 8889 ✅ — HTTP 200 on /health
- **Status:** MONITORING — running; flag if it goes down again

---

## ✅ RESOLVED

### C-015 — `ums-app` and `mypostgresql_db-container` were exited ✅ RESOLVED 2026-05-05
- Both containers are now running (Up 27 min / Up 4h as of cycle #5)
- Exit codes 143/137 from previous cycle were clean/forced shutdowns, not crashes
