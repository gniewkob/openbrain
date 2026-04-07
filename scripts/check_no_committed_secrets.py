from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

# Files where test/example credentials are expected — never flag these
IGNORED_PATHS = {
    # CI workflow uses localhost test credentials intentionally
    ".github/workflows/ci.yml",
    # Secret scan tests contain deliberate secret-like fixtures
    "unified/tests/test_secret_scan.py",
    # Audit docs contain example/redacted credential URLs
    "docs/AUDIT_REPORT_2026-04-04.md",
    "docs/CRITICAL_CODE_AUDIT_2026-04-04.md",
    # Implementation plans contain fake/example credentials as test fixtures
    "docs/superpowers/plans/2026-04-05-track-a-p0-hardening.md",
    "docs/superpowers/plans/2026-04-05-track-b-p1-fixes.md",
    "docs/superpowers/plans/2026-04-06-audit-remediation-p1-p2.md",
    "docs/superpowers/plans/2026-04-06-m2-write-truncation-warning.md",
    "docs/superpowers/specs/2026-04-05-track-a-p0-hardening-design.md",
    "docs/superpowers/specs/2026-04-05-track-b-p1-fixes-design.md",
    "docs/mcp-api-keys-and-configuration.md",
}

IGNORED_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".pdf",
    ".pyc",
}
URL_SCAN_SUFFIXES = {
    ".env",
    ".example",
    ".ini",
    ".json",
    ".md",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
LINE_PATTERNS = {
    "ngrok token": re.compile(r"^\s*(?:-\s*)?NGROK_AUTHTOKEN\s*[:=]\s*(?P<value>.+)$"),
    "internal api key": re.compile(
        r"^\s*(?:-\s*)?INTERNAL_API_KEY\s*[:=]\s*(?P<value>.+)$"
    ),
    "auth0 client secret": re.compile(
        r"^\s*(?:-\s*)?AUTH0_CLIENT_SECRET\s*[:=]\s*(?P<value>.+)$"
    ),
    "grafana admin password": re.compile(
        r"^\s*(?:-\s*)?GRAFANA_ADMIN_PASSWORD\s*[:=]\s*(?P<value>.+)$"
    ),
    "postgres password": re.compile(
        r"^\s*(?:-\s*)?POSTGRES_PASSWORD\s*[:=]\s*(?P<value>.+)$"
    ),
    "generic token": re.compile(
        r"^\s*(?:-\s*)?[A-Z0-9_]*TOKEN[A-Z0-9_]*\s*[:=]\s*(?P<value>.+)$"
    ),
    "generic secret": re.compile(
        r"^\s*(?:-\s*)?[A-Z0-9_]*SECRET[A-Z0-9_]*\s*[:=]\s*(?P<value>.+)$"
    ),
    "bearer authorization": re.compile(
        r"^\s*Authorization\s*:\s*Bearer\s+(?P<value>.+)$",
        re.IGNORECASE,
    ),
}
PRIVATE_KEY_PATTERN = re.compile(
    r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"
)
URL_CREDENTIAL_PATTERN = re.compile(
    r"\b[a-z][a-z0-9+.-]*://(?P<value>[^/\s:@]+:[^/\s@]+)@",
    re.IGNORECASE,
)


def tracked_files() -> list[Path]:
    proc = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    result = []
    for raw in proc.stdout.splitlines():
        path = ROOT / raw
        if not path.is_file():
            continue
        if path.suffix.lower() in IGNORED_SUFFIXES:
            continue
        result.append(path)
    return result


def _is_placeholder(value: str) -> bool:
    normalized = value.strip().strip('"').strip("'")
    if not normalized:
        return True
    if normalized.startswith("${") and normalized.endswith("}"):
        return True
    if normalized.startswith("$"):
        return True
    # URL credentials like "user:${VAR}" contain env var references
    if "${" in normalized:
        return True
    if normalized.lower() in {
        "[hidden]",
        "[redacted]",
        "changeme",
        "your-secret-here",
        # Common test/default passwords that are not real secrets
        "postgres",
        "password",
        "secret",
        "admin",
        "test",
        "1",
        "0",
    }:
        return True
    if normalized.startswith("your-"):
        return True
    if normalized in {"...", "<redacted>", "<hidden>"}:
        return True
    if "os.environ.get(" in normalized or "env.get(" in normalized:
        return True
    # Python code: attribute access (config.auth.internal_api_key), type annotations (str = "")
    if normalized.startswith(("str", "int", "bool", "list", "dict", "tuple", "None")):
        return True
    if re.match(r"^[a-z_][a-z0-9_.]*\.[a-z_][a-z0-9_.]*", normalized):
        return True
    # Numeric/arithmetic expressions (e.g. TTL constants: "30 * 24 * 3600 # comment")
    if re.fullmatch(r"[\d\s\*\+\-\/\(\)]+(?:#[^\n]*)?", normalized):
        return True
    return False


def main() -> int:
    findings: list[str] = []
    for path in tracked_files():
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = path.relative_to(ROOT)
        # Skip files that intentionally contain test/example credentials
        if str(rel) in IGNORED_PATHS:
            continue
        if PRIVATE_KEY_PATTERN.search(content):
            findings.append(f"{rel}: private key block")
        if path.suffix.lower() in URL_SCAN_SUFFIXES or path.name.startswith(".env"):
            for match in URL_CREDENTIAL_PATTERN.finditer(content):
                if _is_placeholder(match.group("value")):
                    continue
                findings.append(f"{rel}: embedded URL credentials")
        for line_no, line in enumerate(content.splitlines(), start=1):
            for label, pattern in LINE_PATTERNS.items():
                match = pattern.search(line)
                if not match:
                    continue
                if _is_placeholder(match.group("value")):
                    continue
                findings.append(f"{rel}:{line_no}: {label}")

    if findings:
        print("Committed secret-like values detected:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1

    print("No committed secret-like values detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
