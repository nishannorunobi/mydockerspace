# Open Concerns & Flagged Anomalies
_Last updated: 2026-04-27 (Session 2 — re-scan)_

---

## 🔴 HIGH PRIORITY

### C-001 — `context.md` is stale
- **File:** `context.md`
- **Issue:** Still references `AlmaLinux 9`, `dnf`, `IMAGE_VERSION=1.3`, `ums-container/apigw-container` — but workspace.conf now shows `BASE_IMAGE=postgres:16`, `PKG_MANAGER=apt`, `IMAGE_VERSION=1.4`, `ums-app`
- **Risk:** Misleads Claude (or any reader) about the actual OS/environment and container names
- **Fix:** Update context.md to reflect current state: postgres:16 base, apt pkg manager, IMAGE_VERSION=1.4, PROJECT_NAME=mypostgresql_db, container=ums-app
- **Status:** OPEN — not fixed since Session 1

### C-002 — UMS `docker-compose.yml` references `.env` file
- **File:** `projectspace/ums/dockerspace/host_scripts/docker-compose.yml`
- **Issue:** `env_file: ../../.env` — an `.env` file is used. Must verify it is gitignored and not committed.
- **Risk:** Credential leak if `.env` was ever committed
- **Fix:** Confirm `ums/.env` is in `.gitignore`. If not, add immediately. Consider switching to `ums/project.conf` pattern.
- **Status:** OPEN — not verified since Session 1

---

## 🟡 MEDIUM PRIORITY

### C-003 — `mywritings.zip` in projectspace root
- **File:** `projectspace/mywritings.zip`
- **Issue:** A binary zip file sitting in the projectspace root — wrong location, not a project folder
- **Risk:** Clutter; if projectspace were ever committed, binary would pollute git history
- **Fix:** Move to `mountspace/` or extract to `projectspace/mywrites/` if it belongs there
- **Status:** OPEN

### C-004 — `myapigw` has no `dockerspace/` structure
- **File:** `projectspace/myapigw/` — only README.md present
- **Issue:** Violates project convention (every project needs dockerspace/ with host_scripts/ and container_scripts/)
- **Risk:** Incomplete project; whoever picks it up has no starting point
- **Fix:** Create `myapigw/dockerspace/host_scripts/` with stub scripts (build.sh, start.sh, stop.sh, health.sh, login_docker.sh) when ready to develop
- **Status:** OPEN

### C-005 — `pc-maker` has no `dockerspace/`
- **File:** `projectspace/pc-maker/`
- **Issue:** No dockerspace/ folder — convention says every project should have one
- **Risk:** Low — pc-maker is a native OS scripts collection, Docker may not apply
- **Fix:** Either add a minimal dockerspace/ stub or formally document this as a Docker-exempt project
- **Status:** OPEN

### C-006 — `workspace-agent` scripts not in `dockerspace/host_scripts/`
- **File:** `workspace-agent/`
- **Issue:** Has build.sh, start.sh, stop.sh, health.sh directly in root — not in dockerspace/host_scripts/ as per convention
- **Risk:** Convention drift — the guardian of conventions doesn't follow them
- **Fix:** Reorganize into workspace-agent/dockerspace/host_scripts/ — or formally document this as an exception
- **Status:** OPEN

### C-010 — `claude-agent/host/` contains duplicate scripts outside `dockerspace/`
- **File:** `projectspace/ai-agents/claude-agent/host/`
- **Issue:** host/ folder has build.sh, health.sh, start.sh, stop.sh — same names as those in dockerspace/host_scripts/. Unclear which is canonical.
- **Risk:** Confusion about which scripts to use; maintenance of two sets
- **Fix:** Verify if host/ is a legacy folder. If dockerspace/host_scripts/ is the canonical location, delete host/ or document its purpose.
- **Status:** NEW — identified in Session 2

### C-011 — `linux-lite-7.8-64bit.iso` binary in pc-maker
- **File:** `projectspace/pc-maker/ossetup/debian2debian/linux-lite-7.8-64bit.iso`
- **Issue:** A large binary ISO file stored in projectspace. projectspace is gitignored so it won't be committed, but it's poor hygiene to keep ISOs alongside scripts.
- **Risk:** Disk space; accidental re-introduction if gitignore changes
- **Fix:** Move to `mountspace/` which is explicitly for local-only files
- **Status:** NEW — identified in Session 2

---

## 🟢 LOW PRIORITY / MONITORING

### C-007 — Uncommitted changes to `dockerspace/project.conf` and `.vscode/settings.json`
- **File:** `dockerspace/project.conf`, `.vscode/settings.json`
- **Details:**
  - `project.conf`: stray `r` character in comment separator line (cosmetic typo — `# ─── Project git clone ───────────────r  ───`)
  - `.vscode/settings.json`: added `latex-workshop.latex.outDir: "%DIR%/output"` (intentional — LaTeX output dir config)
- **Risk:** Changes may be lost or cause confusion if not committed
- **Fix:**
  - Fix the typo in project.conf separator, then commit both files together
- **Status:** OPEN — still dirty (confirmed Session 2)

### C-008 — `context.md` references API-Gateway (APISIX) as active
- **File:** `context.md`
- **Issue:** Says "API-Gateway (APISIX)" with container `apigw-container` — but only a README stub exists in myapigw/. Also references wrong container name (now `ums-app`, not `ums-container`)
- **Fix:** Update context.md (folded into C-001 fix)
- **Status:** OPEN (absorbed into C-001)

### C-009 — `mypostgresql_db/dockerspace/project.conf` EXPOSE_PORTS=8085:8085
- **File:** `projectspace/mypostgresql_db/dockerspace/project.conf`
- **Issue:** PostgreSQL standard port is 5432, not 8085. Port 8085 may be for a management/UI service.
- **Risk:** Confusion — claude-agent connects to port 5432 (from agent.conf.example). Inconsistent.
- **Fix:** Verify what 8085 is for. If it's a separate service, document it. Ensure 5432 is also exposed for DB connections.
- **Status:** OPEN

---

## ✅ RESOLVED
_(none yet)_
