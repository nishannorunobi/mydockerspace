# Proposed .gitignore
_Generated: 2026-04-27_
_Based on full workspace scan_

## What the current .gitignore covers (4 lines):
- claude/
- projectspace/
- mountspace/
- .vscode/

## What is MISSING:
- .claude/           (untracked, seen in git status)
- workspace-agent/   (untracked, seen in git status — contains agent.conf with secrets)
- agent.conf         (any secrets file at root level)
- .env               (used by ums docker-compose — must never be committed)
- Common OS/IDE/tool noise (DS_Store, __pycache__, *.pyc, etc.)
- Docker/build artifacts
- Java/Maven build artifacts (in case ums src ever lands at workspace level)
- Backup files
