#!/bin/bash
PORT="${PORT:-8892}"
curl -sf "http://localhost:$PORT/health" | python3 -c "import json,sys; d=json.load(sys.stdin); print('OK' if d['status']=='ok' else 'FAIL', '|', d.get('claude_bin','?'))" 2>/dev/null || echo "FAIL — not running"
