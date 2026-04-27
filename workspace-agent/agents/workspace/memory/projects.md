# Projects Knowledge Base
_Last updated: 2026-04-27 (Session 3)_

---

## 1. myworkspace (workspace orchestrator)
- **Purpose:** Dashboard/orchestrator — manages all project containers and Docker UI (Portainer)
- **Git repo:** main workspace repo (committed)
- **Stack:** Bash scripts, Docker
- **Key config:**
  - `dockerspace/project.conf` → `PROJECT_NAME=mypostgresql_db` (active workspace container target)
  - `dockerspace/workspace.conf` → `IMAGE_VERSION=1.4`, `BASE_IMAGE=postgres:16`, `PKG_MANAGER=apt`
  - `CONTAINER_NAME` → `${PROJECT_NAME}-container` (derived)
- **Scripts:** start_project_container.sh, stop_project_container.sh, start/stop_system_docker.sh, start/stop_docker_ui.sh, restart/stop_the_world.sh, docker_backup.sh, docker_clean.sh, docker_dashboard.sh, troubleshoot.sh
- **File transfer:** INPUT_FILE=amaro_porano_jaha_chay.mp4, SRC_DIR=/home/nishan/Downloads/ (in project.conf)
- **Status:** Active ✅

---

## 2. ums (User Management System)
- **Purpose:** Spring Boot 3 / Java 21 REST API — User Management System
- **Git repo:** `git@github.com:nishannorunobi/ums.git`
- **Stack:** Java 21, Spring Boot 3, Maven, Docker (multi-stage build)
- **Container name:** `ums-app`
- **Port:** 8080
- **Docker:** Multi-stage Dockerfile — `maven:3.9-eclipse-temurin-21-alpine` (build) → `eclipse-temurin:21-jre-alpine` (runtime)
- **Network:** `ums-network` (external)
- **Env:** reads `../../.env` via docker-compose (⚠️ .env file — verify not committed)
- **Script convention:** host_scripts/ has: start_docker.sh, stop_docker.sh, restart_docker.sh, health_from_host.sh, login_docker.sh, Makefile ✅
- **Container scripts:** start.sh, stop.sh, health.sh ✅
- **Extras:** k8s/ folder (Kubernetes manifests), prometheus.yml
- **Status:** Active ✅

---

## 3. mypostgresql_db
- **Purpose:** PostgreSQL 16 dev database container for UMS
- **Git repo:** `git@github.com:nishannorunobi/mypostgresql_db.git`
- **Stack:** PostgreSQL 16 (official image)
- **Container name:** `mypostgresql_db-container`
- **Image:** `mypostgresql_db-image:1.0`
- **Dockerfile:** `ARG BASE_IMAGE=postgres:16`
- **Port:** 8085:8085 (via EXPOSE_PORTS in project.conf) ⚠️ standard PG port is 5432
- **Network:** `ums-network` (assumed, since claude-agent connects to it)
- **Script convention:** host_scripts/ has: start.sh, stop.sh, loginto_docker.sh, run_in_host.sh ✅
- **Container scripts:** db_ui.sh ✅
- **DB:** umsdb — init/ scripts in umsdb/ folder (01-04 SQL scripts + scripts/)
- **Status:** Active ✅

---

## 4. db-agent (Database Management Agent) 🆕 NEW
- **Purpose:** AI agent that runs INSIDE the mypostgresql_db container to monitor, query and manage PostgreSQL
- **Location:** `projectspace/mypostgresql_db/db-agent/`
- **Stack:** Python, Anthropic Claude API, psycopg2 (connects on localhost:5432 as postgres superuser)
- **Memory:** File-based JSON in `db-agent/memory/` — no external DB needed
  - memory files: db_state.json, sessions.json, issues.json, schema_snapshot.json, connectivity.json
- **Config:** `agent.conf` (gitignored), `agent.conf.example` (committed template)
  - Keys: ANTHROPIC_API_KEY, DB credentials
- **Script convention:**
  - Root scripts: build.sh, start.sh, stop.sh, health.sh ⚠️ not in dockerspace/host_scripts/ — convention drift (see C-006 pattern)
  - `dockerspace/container_scripts/start_agent.sh` ✅
- **Tools the agent has:**
  - pg_status, pg_start, pg_stop, pg_restart
  - run_query (read-only), run_admin_query (write, guarded)
  - check_connections, check_db_size, check_table_sizes, check_locks, check_slow_queries, check_replication
  - scan_logs, run_shell (guarded)
  - memory_read, memory_write, memory_list
  - take_snapshot, load_snapshot
- **Files:** agent.py, tools.py, requirements.txt
- **Status:** 🆕 Newly created — structure in place, not yet running ⚠️ agent.conf not yet created (needs real keys)

---

## 5. claude-agent (AI Testing Agent)
- **Purpose:** Claude API-powered agent that tests UMS endpoints and logs to PostgreSQL
- **Location:** `projectspace/ai-agents/claude-agent/`
- **Stack:** Python, Anthropic Claude API, PostgreSQL (psycopg2)
- **Container name:** `claude-agent`
- **Network:** `ums-network` (external)
- **Connections:** `ums-app:8080` (UMS API), `mypostgresql_db-container:5432` (DB)
- **Config:** `agent.conf` (gitignored real secrets), `agent.conf.example` (committed template)
  - Keys: ANTHROPIC_API_KEY, AGENT_DB_NAME/USER/PASSWORD/PORT, PG_CONTAINER, UMS_CONTAINER, UMS_PORT
- **Script convention:** dockerspace/host_scripts/ has: build.sh, start.sh, stop.sh, health.sh, login_docker.sh ✅
- **Container scripts:** check_env.sh ✅
- **Extra:** host/ folder also has build.sh, health.sh, start.sh, stop.sh ⚠️ duplicate/stale scripts outside dockerspace/
- **SQL:** sql/init_agent_schema.sql + init_db.sh
- **Files:** agent.py, db.py, tools.py, requirements.txt
- **Status:** Active ✅

---

## 6. myapigw (API Gateway)
- **Purpose:** API gateway (APISIX planned)
- **Git repo:** `git@github.com:nishannorunobi/myapigw.git`
- **Stack:** TBD
- **Status:** Stub only — README.md exists, no dockerspace/ yet ⚠️

---

## 7. pc-maker
- **Purpose:** PC setup scripts and OS configuration
- **Stack:** Bash
- **Contents:**
  - `home/user/` — empty placeholder for dotfiles
  - `ossetup/debian2debian/utility/` — install scripts: chrome, docker, git, ssh, vim, vscode, guake, xclip
  - `ossetup/debian2debian/` — USB drive tools + linux-lite-7.8-64bit.iso ⚠️ binary ISO
  - `pchealth/` — disk_health.sh, system_info.sh
- **Note:** Not a Docker project — no dockerspace/ (acceptable for this type)
- **Status:** Utility scripts ✅

---

## 8. mywrites
- **Purpose:** Academic writing projects
- **Contents:**
  - `amazon/` — "quantum_machine_is_here" LaTeX paper, Python export, cover images, compiled PDF output
  - `springer/` — empty placeholder
- **VS Code:** latex-workshop.latex.outDir configured to %DIR%/output (in .vscode/settings.json)
- **Status:** Active writing ✅

---

## 9. workspace-agent (this agent)
- **Purpose:** Workspace Management Agent — observes, tracks, advises, maintains memory
- **Location:** `workspace-agent/`
- **Stack:** Python, Claude API
- **Scripts:** build.sh, start.sh, stop.sh, health.sh (directly in root — not in dockerspace/host_scripts/)
- **Config:** agent.conf (gitignored), agent.conf.example
- **Status:** Active ✅

---

## Shared Infrastructure
- **Docker network:** `ums-network` (external, must be created before starting any project)
- **Docker UI:** Portainer CE on `http://localhost:9000`
- **Network rule:** Use container names (not IPs) — enforced across all projects ✅
