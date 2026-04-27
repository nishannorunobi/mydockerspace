```
# ============================================================
#  myworkspace — .gitignore
#  Managed by workspace-agent | Last updated: 2026-04-27
# ============================================================

# ── Workspace directories (never committed) ─────────────────
projectspace/          # all project repos — cloned at runtime
mountspace/            # local files, media, never committed

# ── Agent & CLI config (may contain secrets) ────────────────
claude/                # Claude CLI config (legacy path)
.claude/               # Claude CLI config (current path)
workspace-agent/       # Workspace Management Agent (local only)

# ── Secret / credentials files ──────────────────────────────
agent.conf             # API keys and credentials (use agent.conf.example instead)
.env                   # Docker env files — NEVER commit
*.env                  # any variant (.env.local, .env.prod, etc.)
*.secret
*.secrets
*.key
*.pem
*.p12
*.pfx
id_rsa
id_ed25519
id_ecdsa

# ── VS Code ──────────────────────────────────────────────────
.vscode/               # local editor settings
.vscode-server/        # VS Code server extensions (generated)

# ── devcontainer ─────────────────────────────────────────────
.devcontainer.json     # local devcontainer config

# ── Docker build artifacts ───────────────────────────────────
.docker/
docker-compose.override.yml

# ── Python ───────────────────────────────────────────────────
__pycache__/
*.py[cod]
*.pyo
*.pyd
.Python
*.egg-info/
dist/
build/
.eggs/
.pytest_cache/
.mypy_cache/
.ruff_cache/
venv/
.venv/
env/
pip-log.txt

# ── Java / Maven ─────────────────────────────────────────────
target/
*.class
*.jar
*.war
*.ear
.mvn/wrapper/maven-wrapper.jar
hs_err_pid*

# ── Node.js ──────────────────────────────────────────────────
node_modules/
npm-debug.log*
yarn-error.log*
package-lock.json

# ── LaTeX (mywrites) ─────────────────────────────────────────
*.aux
*.log
*.out
*.toc
*.synctex.gz
*.fls
*.fdb_latexmk
*.bbl
*.blg
*.idx
*.ilg
*.ind
*.lof
*.lot
*.pdf

# ── Archives & binaries ──────────────────────────────────────
*.zip
*.tar.gz
*.tar.bz2
*.tar.xz
*.gz
*.rar
*.7z
*.iso
*.dmg
*.img
*.bin
*.exe
*.dll
*.so
*.dylib

# ── OS noise ─────────────────────────────────────────────────
.DS_Store
.DS_Store?
._*
.Spotlight-V100
.Trashes
Thumbs.db
ehthumbs.db
Desktop.ini
$RECYCLE.BIN/

# ── Logs & temp files ────────────────────────────────────────
*.log
*.tmp
*.temp
*.swp
*.swo
*~
.cache/

# ── SSH keys (safety net) ────────────────────────────────────
.ssh/
```
