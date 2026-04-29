# Agent Orchestrator

Routes tasks across all registered agents. Web UI on port **8888**.

## First-time setup

```bash
cd agents/agent-orchestrator
./build.sh
```

Set your API key in `../shared.conf`:
```
ANTHROPIC_API_KEY=your-key-here
```

## Start

```bash
./start_web.sh
```

Open **http://localhost:8888**

## Stop

Press `Ctrl+C` in the terminal running the server.

## Chat with the Orchestrator

1. Open the dashboard
2. Click the **Orchestrator** card
3. Click **Chat**
4. Type a task — e.g. *"check all agents health"* or *"run workspace maintenance"*

The orchestrator routes your task to the right agent automatically.

## Add a new agent

Edit `agents.conf` — no code changes needed:

```ini
[my-agent]
name         = My Agent
capabilities = what it can do (shown to the orchestrator for routing)
connector    = http                        # or: direct, subprocess
api_url      = http://localhost:8003       # (http connector)
home         = {AGENTS_DIR}/my-agent
start_script = start.sh
stop_script  = stop.sh
health_script = health.sh
```

## Config files

| File | Purpose |
|---|---|
| `agents.conf` | Agent registry — add/remove agents here |
| `server.conf` | Port, log level |
| `../shared.conf` | API keys, shared credentials |
