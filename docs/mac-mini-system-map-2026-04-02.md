# Mac Mini System Map: 2026-04-02

## Scope

This note captures the current operational split between the two systems running on the same Mac Mini:

- `openbrain`
- `mailai`

The goal is to make collisions, shared dependencies, and operational boundaries explicit.

## OpenBrain

### Docker services

- `openbrain-unified-server`
- `openbrain-unified-db`
- `openbrain-unified-prometheus`
- `openbrain-unified-grafana`
- `openbrain-unified-ollama`
- `openbrain-unified-ngrok`

### Host-bound ports

- `127.0.0.1:7010` -> unified server
- `127.0.0.1:5432` -> PostgreSQL
- `127.0.0.1:9090` -> Prometheus
- `127.0.0.1:3001` -> Grafana
- `127.0.0.1:9180` -> metrics bridge on host
- `127.0.0.1:11434` -> Ollama

### Public exposure

- Public ingress exists through ngrok.
- Current public base URL during the audit:
  - `https://poutily-hemispheroidal-pia.ngrok-free.dev`
- Verified behavior:
  - `/healthz` -> `200`
  - `/.well-known/oauth-protected-resource` -> `200`
  - `/sse` -> `401`

### Monitoring path

- Prometheus scrapes `host.docker.internal:9180`
- `9180` is provided by `com.openbrain.metrics.bridge`
- The bridge injects `X-Internal-Key` and proxies `/metrics` from the unified server

## MailAI

### Host services

- `com.mailai.multi.prod`
- `com.mailai.metrics.prod`

### Host-bound ports

- `127.0.0.1:9177` -> mail metrics exporter
- `127.0.0.1:9277` -> Warp local listener, unrelated to MailAI but present on host

### Monitoring path

- Prometheus scrapes `host.docker.internal:9177`
- `9177` serves `mailai_*` metrics, not OpenBrain metrics

## Shared Infrastructure

### Shared Prometheus stack

- One Prometheus instance serves both:
  - job `openbrain-unified`
  - job `mailai`
- Alert rules for both systems live in one file:
  - `docs/prometheus-alerts.yml`

### Shared Grafana stack

- One Grafana instance on `127.0.0.1:3001`
- Separate dashboards exist for:
  - `openbrain`
  - `mail`

### Shared host characteristics

- Same macOS host
- Same Docker Desktop daemon
- Same local operator account
- Same local launchd domain

## Verified During Audit

### OpenBrain

- Container stack healthy
- Public ngrok ingress working
- REST write/get/delete smoke passed with internal auth
- `/metrics` correctly returns `401` without auth
- `/metrics` returns `200` with internal auth
- stdio gateway initializes correctly
- Prometheus target for `openbrain-unified` is `up=1`

### MailAI

- Prometheus target exists and is `up`
- Exporter on `9177` is alive
- Launch agents for production and metrics are present

## Operational Risks

1. Port confusion between `9177` and `9180`
- `9177` is MailAI metrics
- `9180` is OpenBrain metrics bridge
- Manual checks can easily hit the wrong service

2. Shared blast radius on one host
- Docker saturation, disk pressure, host memory pressure, or launchd instability can affect both systems simultaneously

3. Mixed monitoring surface
- Shared Prometheus and Grafana are efficient, but mistakes in dashboards, alert queries, or target assumptions can cross-contaminate diagnosis

4. Unknown stray containers
- Additional containers with generated names are running and should be classified or removed:
  - `nostalgic_ganguly`
  - `stoic_wilson`
  - `frosty_leakey`
  - `zealous_bell`
  - `stoic_antonelli`

## Recommended Next Actions

1. Add a single host-level canary script that checks both systems end-to-end.
2. Add explicit documentation labels for metrics ports:
   - MailAI: `9177`
   - OpenBrain: `9180`
3. Classify or remove the stray Docker containers.
4. Add host-resource alerts:
   - disk pressure
   - memory pressure
   - restart loops
   - Docker daemon availability
5. Decide whether public ngrok exposure should remain continuously enabled or only be started on demand.

## Host Canary

The repository now includes a shared host-level canary:

- `scripts/host_dual_canary.sh`
- `scripts/host_resource_canary.sh`
- `scripts/host_full_canary.sh`
- `scripts/host_full_canary_runner.sh`
- `launchd/com.openbrain.host-full-canary.plist`

It checks:

- OpenBrain Docker containers
- OpenBrain local `healthz` and `readyz`
- OpenBrain metrics bridge on `9180`
- MailAI launchd services
- MailAI exporter on `9177`
- Prometheus target health for both jobs
- Public OpenBrain `healthz`
- Public OpenBrain `/sse` auth posture

Recommended usage:

```bash
bash scripts/host_dual_canary.sh
bash scripts/host_resource_canary.sh
bash scripts/host_full_canary.sh
```

For automated execution on the Mac Mini:

```bash
cp launchd/com.openbrain.host-full-canary.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.openbrain.host-full-canary.plist
launchctl kickstart -k gui/$(id -u)/com.openbrain.host-full-canary
```

Logs:

- `monitoring/host-full-canary-stdout.log`
- `monitoring/host-full-canary-status.log`
- `monitoring/host-full-canary-launchd-stdout.log`
- `monitoring/host-full-canary-launchd-stderr.log`
