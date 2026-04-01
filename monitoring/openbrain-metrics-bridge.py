#!/usr/bin/env python3
"""
OpenBrain Metrics Bridge
========================
Runs on the host at 127.0.0.1:9180.  Proxies /metrics from the OpenBrain
unified server (http://127.0.0.1:7010/metrics) by adding the X-Internal-Key
header, then re-serves the response without auth so Prometheus can scrape it
from inside Docker via host.docker.internal:9180.

Secret loading order (first found wins):
  1. INTERNAL_API_KEY env var
  2. OPENBRAIN_INTERNAL_API_KEY env var
  3. .env file in the repo root (same directory as this script's parent dir)

Usage:
  python3 monitoring/openbrain-metrics-bridge.py [--port 9180]

Managed by: ~/Library/LaunchAgents/com.openbrain.metrics.bridge.plist
"""
from __future__ import annotations

import argparse
import http.server
import logging
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [openbrain-bridge] %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("openbrain-bridge")

# ---------------------------------------------------------------------------
# Secret resolution
# ---------------------------------------------------------------------------

def _load_env_file(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def resolve_api_key() -> str:
    # 1. Environment variables
    for var in ("INTERNAL_API_KEY", "OPENBRAIN_INTERNAL_API_KEY"):
        val = os.environ.get(var, "").strip()
        if val:
            log.info("API key loaded from env var %s", var)
            return val

    # 2. .env file two levels up from this script (repo root)
    repo_root = Path(__file__).resolve().parent.parent
    for candidate in (repo_root / ".env", repo_root / ".env.local"):
        env = _load_env_file(candidate)
        val = env.get("INTERNAL_API_KEY", "").strip()
        if val:
            log.info("API key loaded from %s", candidate)
            return val

    log.warning(
        "INTERNAL_API_KEY not found — bridge will forward requests without auth "
        "(metrics endpoint will return 401 if the key is required)"
    )
    return ""


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

UPSTREAM = "http://127.0.0.1:7010/metrics"


class BridgeHandler(http.server.BaseHTTPRequestHandler):
    api_key: str = ""

    def log_message(self, fmt: str, *args: object) -> None:  # silence default access log
        pass

    def do_GET(self) -> None:
        if self.path not in ("/metrics", "/metrics/"):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found\n")
            return

        req = urllib.request.Request(UPSTREAM)
        if self.api_key:
            req.add_header("X-Internal-Key", self.api_key)

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read()
                self.send_response(200)
                self.send_header("Content-Type", resp.headers.get("Content-Type", "text/plain"))
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        except urllib.error.HTTPError as exc:
            log.error("Upstream %s: %s", UPSTREAM, exc)
            self.send_response(exc.code)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"Upstream error: {exc}\n".encode())
        except Exception as exc:
            log.error("Bridge error: %s", exc)
            self.send_response(502)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"Bridge error: {exc}\n".encode())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="OpenBrain Prometheus metrics bridge")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9180)
    args = parser.parse_args()

    api_key = resolve_api_key()
    BridgeHandler.api_key = api_key

    server = http.server.HTTPServer((args.host, args.port), BridgeHandler)
    log.info("Bridge listening on http://%s:%d/metrics → %s", args.host, args.port, UPSTREAM)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Bridge stopped")


if __name__ == "__main__":
    main()
