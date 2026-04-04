#!/usr/bin/env python3
import argparse, http.server, logging, os, sys, urllib.error, urllib.request
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s [bridge] %(levelname)s %(message)s', stream=sys.stdout)
log = logging.getLogger('bridge')

def _load_env_file(path: Path) -> dict[str, str]:
    result = {}
    if not path.exists(): return result
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line: continue
            k, _, v = line.partition('=')
            result[k.strip()] = v.strip().strip('"').strip("'")
    except Exception as e: log.warning(f'Err {path}: {e}')
    return result

def resolve_api_key() -> str:
    val = os.environ.get('INTERNAL_API_KEY', '').strip()
    if val: return val
    repo_root = Path(__file__).resolve().parent.parent
    for candidate in (repo_root / '.env', repo_root / '.env.local'):
        env = _load_env_file(candidate)
        val = env.get('INTERNAL_API_KEY', '').strip()
        if val: return val
    return ''

class BridgeHandler(http.server.BaseHTTPRequestHandler):
    api_key = ''; upstream = ''
    def log_message(self, fmt, *args): pass
    def do_GET(self):
        if not self.path.startswith('/metrics'):
            self.send_response(404); self.end_headers(); return
        req = urllib.request.Request(self.upstream)
        if self.api_key: req.add_header('X-Internal-Key', self.api_key)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers(); self.wfile.write(body)
        except Exception as e:
            log.error(f'Upstream error: {e}'); self.send_response(502); self.end_headers()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=9180)
    parser.add_argument('--upstream', default=os.environ.get('METRICS_UPSTREAM_URL', 'http://unified-server:80/metrics'))
    args = parser.parse_args()
    BridgeHandler.api_key = resolve_api_key(); BridgeHandler.upstream = args.upstream
    server = http.server.HTTPServer((args.host, args.port), BridgeHandler)
    log.info(f'Bridge active: {args.host}:{args.port} -> {args.upstream}')
    server.serve_forever()

if __name__ == '__main__': main()
