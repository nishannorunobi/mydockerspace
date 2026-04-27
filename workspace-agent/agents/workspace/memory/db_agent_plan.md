# db-agent Build Plan
_Created: 2026-04-27_

## Location
projectspace/mypostgresql_db/db-agent/

## Structure
```
db-agent/
├── memory/                        ← persistent JSON memory (no external DB needed)
│   ├── db_state.json              ← last known DB state snapshot
│   ├── sessions.json              ← session history
│   ├── issues.json                ← known issues log
│   ├── schema_snapshot.json       ← last known schema
│   └── connectivity.json         ← connectivity history
├── dockerspace/
│   └── container_scripts/
│       └── start_agent.sh         ← run agent inside container
├── agent.py                       ← main agent loop
├── tools.py                       ← all tool implementations
├── memory_store.py                ← memory read/write layer
├── agent.conf.example             ← config template
├── agent.conf                     ← real config (gitignored)
├── requirements.txt
└── README.md
```

## Tools the agent will have
- pg_status        — check if postgres process is running inside container
- pg_start / pg_stop / pg_restart — manage postgres inside container
- run_query        — SELECT/SHOW queries (read-only safe tool)
- run_admin_query  — DML/DDL with confirmation (write tool, guarded)
- check_connections — show pg_stat_activity
- check_db_size    — show database sizes
- check_table_sizes — show table sizes
- check_locks      — show pg_locks
- check_slow_queries — show slow queries from pg_stat_statements
- check_replication — show replication status
- scan_logs        — tail postgres log
- run_shell        — run bash command inside container (guarded)
- memory_read      — read a memory file
- memory_write     — write/update a memory file
- memory_list      — list all memory files
- take_snapshot    — capture full DB state to memory
- load_snapshot    — load and show last snapshot from memory

## Agent character
- Runs INSIDE the container (postgres:16 = Debian-based)
- Connects to postgres via psycopg2 on localhost:5432 as postgres superuser
- Memory is file-based JSON in db-agent/memory/ (no external dependencies)
- Reads agent.conf for config (ANTHROPIC_API_KEY, DB credentials)
- Tool outputs are always formatted for human reading in terminal
