# Runbook: OpenBrain Monitoring (Grafana + Prometheus)

## Architecture

```
OpenBrain unified-server (Docker :80)
    │  /metrics — requires X-Internal-Key header
    │
    ▼
openbrain-metrics-bridge.py   ← runs on HOST at 127.0.0.1:9180
    │  adds X-Internal-Key from .env
    │  exposes plain /metrics (no auth)
    │
    ▼
Prometheus (Docker)   ← scrapes host.docker.internal:9180
    │
    ▼
Grafana (Docker :3001)  ← dashboard reads from Prometheus
```

The bridge follows the same pattern as the `mailai` exporter on port 9177.

---

## Secret location

`INTERNAL_API_KEY` is stored in `/Users/gniewkob/Repos/openbrain/.env`
(gitignored — never committed).

The bridge reads it automatically at startup. To rotate:
1. Update `INTERNAL_API_KEY` in `.env` (the compose stack already consumes it from the environment; do not hardcode it in `docker-compose.unified.yml`)
2. Restart the bridge: `launchctl kickstart -k gui/$(id -u)/com.openbrain.metrics.bridge`
3. Restart unified-server: `docker compose -f docker-compose.unified.yml restart unified-server`

---

## Managing the bridge (launchd)

**LaunchAgent plist:** `~/Library/LaunchAgents/com.openbrain.metrics.bridge.plist`

```bash
# Start
launchctl load ~/Library/LaunchAgents/com.openbrain.metrics.bridge.plist

# Stop
launchctl unload ~/Library/LaunchAgents/com.openbrain.metrics.bridge.plist

# Restart
launchctl kickstart -k gui/$(id -u)/com.openbrain.metrics.bridge

# Status
launchctl list | grep openbrain

# Logs
tail -f /Users/gniewkob/Repos/openbrain/monitoring/bridge-stdout.log
tail -f /Users/gniewkob/Repos/openbrain/monitoring/bridge-stderr.log
```

The plist has `RunAtLoad=true` and `KeepAlive=true` — the bridge starts automatically at login and restarts on crash.

---

## Validation checklist

```bash
# 1. Bridge is running
launchctl list | grep openbrain          # expect: <pid>  0  com.openbrain.metrics.bridge

# 2. Bridge returns real metrics
curl http://127.0.0.1:9180/metrics | head -5

# 3. Prometheus target is up
curl -s 'http://127.0.0.1:9090/api/v1/targets' | python3 -c "
import json,sys; d=json.load(sys.stdin)
for t in d['data']['activeTargets']:
    print(t['labels']['job'], t['health'], t.get('lastError',''))
"
# expect: openbrain-unified  up

# 4. Metric data in Prometheus
curl -s 'http://127.0.0.1:9090/api/v1/query?query=active_memories_total'
# expect: value != 0

# 5. Dashboard
# Open http://127.0.0.1:3001 → OpenBrain Overview → panels show real data
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Bridge returns `401` | Wrong/missing API key in `.env` | Check `INTERNAL_API_KEY` in `.env` |
| Bridge returns `502` | OpenBrain container not running | `docker compose ... up -d unified-server` |
| Prometheus target `down` | Bridge not running | `launchctl load ... com.openbrain.metrics.bridge.plist` |
| Dashboard `No data` | Prometheus can't reach bridge | Check port 9180 is bound: `lsof -i :9180` |
| After Mac restart, bridge not up | LaunchAgent not loaded | Load the plist once: `launchctl load ~/Library/LaunchAgents/com.openbrain.metrics.bridge.plist` |

---

## Files

| File | Description |
|------|-------------|
| `monitoring/openbrain-metrics-bridge.py` | Bridge script (committed) |
| `monitoring/prometheus/prometheus.yml` | Prometheus scrape config (committed) |
| `~/Library/LaunchAgents/com.openbrain.metrics.bridge.plist` | LaunchAgent (local, not committed) |
| `.env` | Contains `INTERNAL_API_KEY` (gitignored) |
