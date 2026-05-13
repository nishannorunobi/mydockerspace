# Open Concerns & Flagged Anomalies
_Last updated: 2026-05-06 (Autonomous maintenance cycle #7 — scheduled)_

---

## 🔴 HIGH PRIORITY

### C-001 — `context.md` is stale ✅ RESOLVED 2026-05-06
- Updated: IMAGE_VERSION=1.4, BASE_IMAGE=postgres:16, PKG_MANAGER=apt, ums-app container name, removed AlmaLinux curl note

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

### C-017 — `workspace.db` binary may not be gitignored ✅ RESOLVED 2026-05-06
- Created `agents/workspace-agent/workspace/memory/.gitignore` with `workspace.db` — binary no longer appears in git status

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

### C-018 — db-agent services.json returns empty services
- **File:** `projectspace/mypostgresql_db/db-agent/memory/services.json`
- **Issue:** `{"services": {}}` — discover_services tool ran but found no services. Dashboard Controls tab says "Run discover_services in chat to populate services" — it is manual-trigger only.
- **Root cause hypothesis:** The workspace mount path inside db-agent container may not match what the tool scans for host_scripts/start.sh files.
- **Fix:** Run discover_services in the db-agent chat panel; verify mount paths; make it auto-run on startup.
- **Status:** NEW cycle #6

### C-019 — ums-app container not running (only mypostgresql_db-container up)
- **Observed:** `docker ps` shows only `mypostgresql_db-container` as of 2026-05-06 self-scan.
- **Confirmed cycle #7:** ums-app still exited. Exit code 143 (SIGTERM) at 2026-05-06T01:19:01Z — clean/intentional shutdown, NOT a crash. mypostgresql_db-container HEALTHY (pg_isready confirmed).
- **Impact:** UMS API unavailable. UMS ums-agent will report health failures.
- **Fix:** Run `./start.sh` from `projectspace/ums/dockerspace/host_scripts/` or restart via dashboard.
- **Status:** CONFIRMED cycle #7 — awaiting owner action

### C-020 — Two new untracked directories: agents/docs/ and agents/llm-router/
- **Observed cycle #7:** `git status` shows `?? agents/docs/` and `?? agents/llm-router/` as untracked
- **agents/docs/:** Contains `generate_architecture_pdf.py` + `llm_router_architecture.pdf` (binary PDF)
- **agents/llm-router/:** Contains `classifier.py`, `evaluator.py`, `router.py`, `router.yaml`, `layers/` (anthropic_layer.py, ollama.py, base.py) — all syntax checks PASS
- **Assessment:** New LLM router feature work. All Python files pass syntax check. PDF binary should be gitignored or moved to mountspace/. No hardcoded IPs found.
- **Fix:** Owner should commit llm-router source files; add `*.pdf` to agents/docs/.gitignore or move PDF to mountspace/
- **Status:** NEW cycle #7

### C-014 — Uncommitted modifications update (cycle #7)
- **Current dirty files (12 modified):** `.claude/settings.json`, `agents/agent-orchestrator/routers/agents.py` (+10 lines), `routers/chat.py` (+134/-134 lines refactor), `static/css/style.css`, `static/js/dashboard.js` (+39 lines), `static/js/sounds.js` (+30 lines NEW), `docker-manager-agent/agent.py` (+52/-52), `server.py` (+67/-67), `workspace-agent/agent.py` (+80/-80), memory files (change_log.md, concerns.md, sessions.md)
- **All 12 modified files pass syntax checks** — no broken code
- **No hardcoded IPs in source** (one comment-only reference in server.py, safe)
- **Status:** UPDATED cycle #7 — still awaiting owner commit

---

## ✅ RESOLVED

### C-015 — `ums-app` and `mypostgresql_db-container` were exited ✅ RESOLVED 2026-05-05
- Both containers are now running (Up 27 min / Up 4h as of cycle #5)
- Exit codes 143/137 from previous cycle were clean/forced shutdowns, not crashes
