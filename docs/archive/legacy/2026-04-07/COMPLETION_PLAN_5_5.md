# 🎯 PLAN DOKOŃCZENIA SYSTEMU - OpenBrain Unified 5/5

**Wersja:** 1.0  
**Data:** 2026-04-07  
**Cel:** Podniesienie jakości systemu z poziomu 4.4/5 do 5/5

---

## 📊 ANALIZA WYJŚCIOWA

| Obszar | Obecna Ocena | Docelowa | Główne Luki |
|--------|--------------|----------|-------------|
| **Jakość Kodu** | 4/5 | 5/5 | 53 błędy mypy, brak coverage |
| **Infrastruktura** | 4/5 | 5/5 | Brak backupu/DR, scalability |
| **DevOps/CI** | 4/5 | 5/5 | Brak mypy, coverage, bandit |
| **Wydajność** | 3.5/5 | 5/5 | Telemetry per-process, connection pools |
| **Dokumentacja** | 4/5 | 5/5 | Braki w operacyjnej dokumentacji |

---

## 🗺️ MAPA DROGOWA (8 TYGODNI)

```
TYDZIEŃ 1-2: FUNDAMENTY (Mypy + Backup)
├── Dzień 1-3: Naprawa błędów mypy (memory_writes.py)
├── Dzień 4-5: Naprawa błędów mypy (pozostałe pliki)
├── Dzień 6-7: Skrypt backupu PostgreSQL
└── Dzień 8-10: Testy backupu + dokumentacja DR

TYDZIEŃ 3-4: CI/CD I WERYFIKACJA
├── Dzień 11-12: Mypy w CI pipeline
├── Dzień 13-14: Pytest-cov z threshold 80%
├── Dzień 15-16: Bandit security linting
├── Dzień 17-18: Pre-commit hooks
└── Dzień 19-20: Stabilizacja + bugfixing

TYDZIEŃ 5-6: WYDAJNOŚĆ I SKALOWALNOŚĆ
├── Dzień 21-24: Shared telemetry backend (Redis)
├── Dzień 25-26: Connection pool dla MCP
├── Dzień 27-28: PgBouncer dla PostgreSQL
└── Dzień 29-30: Benchmarki i optymalizacja

TYDZIEŃ 7-8: REFAKTORYZACJA I DOKUMENTACJA
├── Dzień 31-34: Pydantic-settings refactor
├── Dzień 35-38: Podział długich funkcji
├── Dzień 39-42: Testy dla obsidian.py + docs
└── Dzień 43-56: Finalizacja, review, release
```

---

## FAZA 1: FUNDAMENTY (Tydzień 1-2)

### 1.1 Naprawa 53 Błędów Mypy

#### Priorytet: 🔴 P0 | Szacowany czas: 3-4 dni

**Lista plików do naprawy:**

| Plik | Błędy | Lokalizacje | Typowe problemy |
|------|-------|-------------|-----------------|
| `memory_writes.py` | 11 | 366-445, 449-551 | Brak typów zwracanych, Optional, Any |
| `mcp_transport.py` | 8 | Cały plik | Narzędzia MCP, batch operacje |
| `api/v1/memory.py` | 7 | 82-348 | FastAPI Depends, typy zwracane |
| `memory_reads.py` | 6 | ~464 linii | Wyszukiwanie, embedding queries |
| `api/v1/obsidian.py` | 5 | 82-456 | Typy sync, endpointy Obsidian |
| `crud.py` | 5 | Cały plik | CRUD operations |
| `schemas.py` | 4 | ~613 linii | Pydantic modele - Optional |
| `auth.py` | 2 | ~597 linii | JWT claims |
| `embed.py` | 2 | ~234 linie | Circuit breaker |
| Pozostałe | 3 | - | Różne |

**Typowe naprawy:**

```python
# PRZED (błąd: brak typu zwracanego)
def handle_memory_write(...):
    ...

# PO (poprawione)
async def handle_memory_write(
    session: AsyncSession,
    write: MemoryWrite,
    agent_id: str,
    request_id: str | None = None,
) -> MemoryWriteResult:
    ...

# PRZED (błąd: Optional bez obsługi None)
result = await session.execute(stmt)
memory = result.scalar_one_or_none()
return memory.content  # mypy: Item "None" of "Optional[...]" has no attribute "content"

# PO (poprawione)
result = await session.execute(stmt)
memory = result.scalar_one_or_none()
if memory is None:
    raise NotFoundError(f"Memory {id} not found")
return memory.content
```

**Checklist:**
- [ ] Uruchomić `mypy src/ --ignore-missing-imports > mypy_errors.txt`
- [ ] Naprawić memory_writes.py (11 błędów)
- [ ] Naprawić mcp_transport.py (8 błędów)
- [ ] Naprawić api/v1/memory.py (7 błędów)
- [ ] Naprawić memory_reads.py (6 błędów)
- [ ] Naprawić api/v1/obsidian.py (5 błędów)
- [ ] Naprawić crud.py (5 błędów)
- [ ] Naprawić schemas.py (4 błędów)
- [ ] Naprawić auth.py (2 błędy)
- [ ] Naprawić embed.py (2 błędy)
- [ ] Uruchomić testy po każdej zmianie
- [ ] Zweryfikować: `mypy src/` - 0 błędów

---

### 1.2 Skrypt Backupu PostgreSQL

#### Priorytet: 🔴 P0 | Szacowany czas: 2 dni

**Lokalizacja:** `scripts/backup_postgres.sh`

```bash
#!/bin/bash
set -euo pipefail

# Konfiguracja z .env
DB_NAME="${POSTGRES_DB:-openbrain_unified}"
DB_USER="${POSTGRES_USER:-postgres}"
DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_PORT:-5432}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
S3_BUCKET="${BACKUP_S3_BUCKET:-}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/openbrain_${TIMESTAMP}.sql.gz"

# Tworzenie katalogu
mkdir -p "${BACKUP_DIR}"

# Backup
pg_dump -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" \
    --verbose --no-owner --no-acl --format=custom | gzip > "${BACKUP_FILE}"

# Upload do S3 (opcjonalnie)
if [[ -n "${S3_BUCKET}" ]]; then
    aws s3 cp "${BACKUP_FILE}" "s3://${S3_BUCKET}/backups/"
fi

# Czyszczenie starych backupów
find "${BACKUP_DIR}" -name "openbrain_*.sql.gz" -mtime +${RETENTION_DAYS} -delete

echo "Backup zakończony: ${BACKUP_FILE}"
```

**Checklist:**
- [ ] Stworzyć `scripts/backup_postgres.sh`
- [ ] Dodać testy jednostkowe dla skryptu
- [ ] Przetestować na dev bazie
- [ ] Skonfigurować cron (codziennie 2:00 AM)
- [ ] Skonfigurować monitoring powodzenia backupu
- [ ] Dodać do dokumentacji operacyjnej

---

### 1.3 Dokumentacja Disaster Recovery

#### Priorytet: 🟡 P1 | Szacowany czas: 2 dni

**Lokalizacja:** `docs/DISASTER_RECOVERY.md`

Zawartość:
- RTO (Recovery Time Objective): 4 godziny
- RPO (Recovery Point Objective): 24 godziny (codzienny backup)
- Procedura restore z backupu
- Procedura failover na standby (jeśli skonfigurowany)
- Kontakty alarmowe
- Checklisty dla różnych scenariuszy (DB down, full DC failure)

**Checklist:**
- [ ] Stworzyć `docs/DISASTER_RECOVERY.md`
- [ ] Zdefiniować RTO/RPO
- [ ] Opisać procedurę restore
- [ ] Przeprowadzić DR drill (test restore)
- [ ] Dodać do onboarding docs

---

## FAZA 2: CI/CD I WERYFIKACJA (Tydzień 3-4)

### 2.1 Mypy w CI Pipeline

#### Priorytet: 🔴 P0 | Zależność: Faza 1.1

**Zmiana:** `.github/workflows/ci.yml`

```yaml
  typecheck:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    
    - name: Install uv
      uses: astral-sh/setup-uv@v4
      with:
        version: "latest"
    
    - name: Install dependencies
      run: |
        cd unified
        uv sync --group dev
    
    - name: Type check with mypy
      run: |
        cd unified
        uv run mypy src/ --ignore-missing-imports --strict
```

**Checklist:**
- [ ] Dodać job `typecheck` do CI
- [ ] Ustawić `--strict` po naprawie wszystkich błędów
- [ ] Skonfigurować `mypy.ini` lub sekcję w pyproject.toml

---

### 2.2 Pytest-cov z Threshold

#### Priorytet: 🔴 P0

**Zmiana:** `unified/pyproject.toml`

```toml
[dependency-groups]
dev = [
    "pytest>=9.0.2",
    "pytest-asyncio>=1.3.0",
    "pytest-cov>=4.0.0",  # NOWE
    "fastmcp>=2.0",
    "ruff>=0.15.9",
    "mypy>=1.20.0",
]
```

**Zmiana:** `.github/workflows/ci.yml`

```yaml
    - name: Run tests with coverage
      env:
        DATABASE_URL: postgresql+asyncpg://[DB_USER]:${DB_PASSWORD}@localhost:5432/openbrain_test
        DISABLE_SECRET_SCANNING: "1"
      run: |
        cd unified
        uv run pytest tests/ -v --tb=short -x \
          --ignore=tests/integration \
          --ignore=tests/test_api_endpoints_live.py \
          --ignore=tests/test_endpoints_summary.py \
          --cov=src --cov-report=xml --cov-report=term-missing \
          --cov-fail-under=80
```

**Checklist:**
- [ ] Dodać pytest-cov do pyproject.toml
- [ ] Zaktualizować CI z coverage
- [ ] Ustawić threshold na 80%
- [ ] Skonfigurować Codecov lub podobne

---

### 2.3 Bandit Security Linting

#### Priorytet: 🟡 P1

**Zmiana:** `.github/workflows/ci.yml`

```yaml
  security-lint:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    
    - name: Install uv
      uses: astral-sh/setup-uv@v4
    
    - name: Install bandit
      run: uv pip install bandit
    
    - name: Security lint with bandit
      run: |
        cd unified
        uv run bandit -r src/ -f json -o bandit-report.json || true
        uv run bandit -r src/ -ll
```

**Checklist:**
- [ ] Dodać job `security-lint`
- [ ] Skonfigurować `.bandit.yml`
- [ ] Ustawić poziom low (-ll)
- [ ] Dodać wykluczenia dla testów (assert używany w testach)

---

### 2.4 Pre-commit Hooks

#### Priorytet: 🟡 P1

**Nowy plik:** `.pre-commit-config.yaml`

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.15.9
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.20.0
    hooks:
      - id: mypy
        additional_dependencies: [types-all]
        args: [--ignore-missing-imports]
  
  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.9
    hooks:
      - id: bandit
        args: [-r, unified/src, -ll]
  
  - repo: local
    hooks:
      - id: check-secrets
        name: Check for committed secrets
        entry: python scripts/check_no_committed_secrets.py
        language: system
        pass_filenames: false
```

**Checklist:**
- [ ] Stworzyć `.pre-commit-config.yaml`
- [ ] Dodać do dokumentacji: `pip install pre-commit && pre-commit install`
- [ ] Przetestować na wszystkich plikach

---

## FAZA 3: WYDAJNOŚĆ I SKALOWALNOŚĆ (Tydzień 5-6)

### 3.1 Shared Telemetry Backend (Redis)

#### Priorytet: 🟡 P1 | Problem: Telemetry per-process nie działa z multi-worker

**Obecny kod:** `unified/src/telemetry.py:177`

```python
# PROBLEM: Registry jest per-process
class TelemetryRegistry:
    _instance = None
    _registry: dict[str, Any] = {}
    
# Rozwiązanie: Redis-backed registry
```

**Implementacja:**

```python
# unified/src/telemetry_redis.py
import json
from redis.asyncio import Redis

class RedisTelemetryRegistry:
    """Distributed telemetry registry using Redis."""
    
    def __init__(self, redis: Redis, prefix: str = "telemetry"):
        self._redis = redis
        self._prefix = prefix
    
    async def increment(self, name: str, value: float = 1.0) -> None:
        key = f"{self._prefix}:counter:{name}"
        await self._redis.incrbyfloat(key, value)
    
    async def record_histogram(self, name: str, value: float) -> None:
        key = f"{self._prefix}:histogram:{name}"
        # Użycie Redis sorted set dla histogramów
        await self._redis.zadd(key, {str(value): value})
    
    async def get_counters(self) -> dict[str, float]:
        pattern = f"{self._prefix}:counter:*"
        keys = await self._redis.keys(pattern)
        result = {}
        for key in keys:
            name = key.decode().split(":")[-1]
            value = await self._redis.get(key)
            result[name] = float(value) if value else 0.0
        return result
```

**Checklist:**
- [ ] Stworzyć `telemetry_redis.py`
- [ ] Dodać flagę konfiguracyjną `TELEMETRY_BACKEND=redis|memory`
- [ ] Przepisać testy dla nowej implementacji
- [ ] Benchmark: multi-worker consistency

---

### 3.2 Connection Pool dla MCP

#### Priorytet: 🟡 P1 | Problem: Per-request AsyncClient tworzy N+1 connections

**Obecny kod:** `unified/src/mcp_transport.py:68-76`

```python
# PROBLEM: Nowy client na każde żądanie
async def _call_tool(...) -> ...:
    async with httpx.AsyncClient() as client:
        response = await client.post(...)
```

**Rozwiązanie:**

```python
# unified/src/mcp_transport.py
from contextlib import asynccontextmanager

class MCPTransport:
    def __init__(self):
        self._client: httpx.AsyncClient | None = None
    
    async def startup(self):
        limits = httpx.Limits(max_keepalive_connections=20, max_connections=50)
        timeout = httpx.Timeout(30.0, connect=5.0)
        self._client = httpx.AsyncClient(limits=limits, timeout=timeout)
    
    async def shutdown(self):
        if self._client:
            await self._client.aclose()
    
    async def call_tool(self, ...) -> ...:
        if not self._client:
            raise RuntimeError("Transport not initialized")
        response = await self._client.post(...)
        ...
```

**Checklist:**
- [ ] Zaimplementować connection pool
- [ ] Dodać lifecycle hooks (startup/shutdown)
- [ ] Monitorować connections w Prometheus
- [ ] Benchmark: przed/po

---

### 3.3 PgBouncer dla PostgreSQL

#### Priorytet: 🟢 P2 | Optymalizacja connection poolingu

**Zmiana:** `docker-compose.unified.yml`

```yaml
  pgbouncer:
    image: pgbouncer/pgbouncer:1.22
    environment:
      DATABASES_HOST: db
      DATABASES_PORT: 5432
      DATABASES_DATABASE: ${POSTGRES_DB:-openbrain_unified}
      POOL_MODE: transaction
      MAX_CLIENT_CONN: 1000
      DEFAULT_POOL_SIZE: 25
      MIN_POOL_SIZE: 5
      RESERVE_POOL_SIZE: 5
      MAX_DB_CONNECTIONS: 50
      SERVER_IDLE_TIMEOUT: 600
      SERVER_LIFETIME: 3600
    ports:
      - "6432:6432"
    depends_on:
      db:
        condition: service_healthy
    networks:
      - net_unified
```

**Zmiana konfiguracji:** `DATABASE_URL=postgresql+asyncpg://...:6432/...`

**Checklist:**
- [ ] Dodać pgbouncer do docker-compose
- [ ] Skonfigurować pool modes
- [ ] Monitorować wait times i connection usage
- [ ] Dostosować pool sizes na podstawie obciążenia

---

## FAZA 4: REFAKTORYZACJA I DOKUMENTACJA (Tydzień 7-8)

### 4.1 Pydantic-settings Refactor

#### Priorytet: 🟢 P2 | 32 miejsca env → 1 konfiguracja

**Obecny stan:** Konfiguracja rozproszona w 9 plikach, 32 miejscach

**Implementacja:**

```python
# unified/src/config_refactored.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, validator

class DatabaseConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DB_")
    
    host: str = Field(default="localhost")
    port: int = Field(default=5432)
    name: str = Field(default="openbrain_unified")
    user: str = Field(default="postgres")
    password: str = Field(...)
    pool_size: int = Field(default=5)
    max_overflow: int = Field(default=10)
    
    @property
    def url(self) -> str:
        return build_asyncpg_dsn(self.user, self.password, self.host, self.port, self.name)

class AuthConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUTH_")
    
    public_mode: bool = Field(default=False)
    internal_api_key: str = Field(..., min_length=32)
    oidc_issuer_url: str | None = None
    oidc_audience: str = Field(default="openbrain-mcp")

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )
    
    db: DatabaseConfig = Field(default_factory=DatabaseConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    # ... pozostałe konfiguracje

settings = Settings()
```

**Checklist:**
- [ ] Zaimplementować `config_refactored.py`
- [ ] Przepisać wszystkie istniejące konfiguracje
- [ ] Zachować backward compatibility (migration path)
- [ ] Aktualizować testy
- [ ] Zdeprecjonować starą konfigurację

---

### 4.2 Podział Długich Funkcji

#### Priorytet: 🟢 P2 | 6 funkcji >50 linii do refaktoryzacji

**Lista funkcji do refaktoryzacji:**

| Funkcja | Plik | Linie | Strategia |
|---------|------|-------|-----------|
| `register_v1_routes` | routes_v1.py | 96 | Extract route groups |
| `register_crud_routes` | routes_crud.py | 93 | Extract CRUD operations |
| `handle_memory_write` | memory_writes.py | 80 | Extract validation + execution |
| `detect_changes` | obsidian_sync.py | 132 | Extract strategies |
| `run_maintenance` | memory_writes.py | 113 | Extract maintenance tasks |
| `apply_sync` | obsidian_sync.py | 97 | Extract sync operations |

**Przykład refaktoryzacji:**

```python
# PRZED: register_v1_routes - 96 linii
def register_v1_routes(app: FastAPI) -> None:
    # ... 96 linii kodu

# PO: Rozbite na grupy
def register_v1_routes(app: FastAPI) -> None:
    _register_memory_routes(app)
    _register_obsidian_routes(app)
    _register_admin_routes(app)

def _register_memory_routes(app: FastAPI) -> None:
    @app.post("/api/v1/memory/write")
    async def write_memory(...) -> ...: ...
    
    @app.post("/api/v1/memory/find")
    async def find_memories(...) -> ...: ...
    # ...
```

**Checklist:**
- [ ] Refaktoryzacja `register_v1_routes`
- [ ] Refaktoryzacja `register_crud_routes`
- [ ] Refaktoryzacja `handle_memory_write`
- [ ] Refaktoryzacja `detect_changes`
- [ ] Refaktoryzacja `run_maintenance`
- [ ] Refaktoryzacja `apply_sync`
- [ ] Uruchomić wszystkie testy

---

### 4.3 Testy dla api/v1/obsidian.py

#### Priorytet: 🟢 P2 | 9 endpointów bez testów

**Nowy plik:** `unified/tests/test_api_v1_obsidian.py`

```python
import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_obsidian_sync_endpoint(client: AsyncClient):
    """Test sync endpoint with valid vault path."""
    response = await client.post(
        "/api/v1/obsidian/sync",
        json={"vault": "TestVault", "paths": ["note.md"]}
    )
    assert response.status_code == 200
    data = response.json()
    assert "synced" in data

@pytest.mark.asyncio
async def test_obsidian_export_endpoint(client: AsyncClient):
    """Test export endpoint creates valid markdown."""
    # ... test implementation

# Testy dla pozostałych 7 endpointów:
# - /obsidian/vaults
# - /obsidian/read
# - /obsidian/write
# - /obsidian/delete
# - /obsidian/bidirectional-sync
# - /obsidian/export
# - /obsidian/collection
```

**Checklist:**
- [ ] Stworzyć `test_api_v1_obsidian.py`
- [ ] Pokryć wszystkie 9 endpointów
- [ ] Testy pozytywne i negatywne
- [ ] Mock dla filesystem operations
- [ ] CI integration

---

### 4.4 Dokumentacja Operacyjna

#### Priorytet: 🟢 P2

**Nowe dokumenty:**

1. **`docs/OPERATIONS.md`** - Podręcznik operacyjny
   - Runbook dla typowych operacji
   - Troubleshooting guide
   - Monitoring dashboards
   - Alert response procedures

2. **`docs/PERFORMANCE_TUNING.md`** - Tuning wydajności
   - Pool sizes (DB, Redis, HTTP)
   - Cache configuration
   - Embedding optimization
   - Query optimization

3. **`docs/API_GUIDE.md`** - Przewodnik po API
   - Przykłady użycia
   - Rate limiting
   - Error handling
   - SDK examples (Python, JS)

**Checklist:**
- [ ] Stworzyć `OPERATIONS.md`
- [ ] Stworzyć `PERFORMANCE_TUNING.md`
- [ ] Stworzyć `API_GUIDE.md`
- [ ] Dodać diagramy architektury
- [ ] Dodać przykłady kodu

---

## 📈 METRYKI SUKCESU

### Metryki jakościowe (Docelowe: 5/5)

| Metryka | Obecnie | Docelowo | Jak mierzyć |
|---------|---------|----------|-------------|
| **Mypy errors** | 53 | 0 | `mypy src/ --strict` |
| **Test coverage** | ? | >=80% | `pytest --cov` |
| **Ruff errors** | 0 | 0 | `ruff check src/` |
| **Bandit issues** | ? | 0 (high) | `bandit -r src/ -ll` |
| **Functions >50 lines** | 6 | <=3 | Manual count |
| **Cyclomatic complexity** | ? | <=10 avg | `radon cc src/` |

### Metryki infrastruktury

| Metryka | Obecnie | Docelowo | Jak mierzyć |
|---------|---------|----------|-------------|
| **Backup RPO** | N/A | 24h | Backup timestamps |
| **Backup RTO** | N/A | 4h | DR drill timing |
| **DB connection pool** | 5/10 | 25/50 | PgBouncer stats |
| **HTTP connection reuse** | 0% | >80% | MCP metrics |
| **Telemetry consistency** | Per-process | Global | Multi-worker test |

### Metryki procesu

| Metryka | Obecnie | Docelowo | Jak mierzyć |
|---------|---------|----------|-------------|
| **CI time** | ? | <10 min | GitHub Actions |
| **Pre-commit pass rate** | N/A | >95% | git hooks |
| **Test flakiness** | ? | <1% | CI stats |
| **Deployment frequency** | ? | Daily | CI/CD |
| **Mean time to recovery** | ? | <2h | Incident logs |

---

## 🎯 MILESTONY I RELEASE

### Milestone 1: "Type Safety" (Koniec tygodnia 2)
- [ ] 0 błędów mypy
- [ ] Backup skrypt działający
- [ ] DR dokumentacja

### Milestone 2: "Quality Gates" (Koniec tygodnia 4)
- [ ] Mypy w CI
- [ ] Coverage >=80%
- [ ] Bandit w CI
- [ ] Pre-commit hooks

### Milestone 3: "Scalability" (Koniec tygodnia 6)
- [ ] Shared telemetry (Redis)
- [ ] Connection pools
- [ ] PgBouncer
- [ ] Benchmark results

### Milestone 4: "Production Ready" (Koniec tygodnia 8)
- [ ] Pydantic-settings
- [ ] Refaktoryzacja funkcji
- [ ] Testy obsidian.py
- [ ] Dokumentacja operacyjna
- [ ] Final review + release tag

---

## 🛡️ RYZYKA I MITIGACJE

| Ryzyko | Prawdopodobieństwo | Wpływ | Mitigacja |
|--------|-------------------|-------|-----------|
| Naprawa mypy ujawni ukryte bugi | Wysokie | Średni | Dokładne testy po każdej zmianie |
| Shared telemetry wpłynie na wydajność | Średnie | Średni | Benchmarki przed/po, feature flag |
| Pydantic-settings to breaking change | Wysokie | Wysoki | Backward compatibility, migration guide |
| Backup restore nie działa | Niskie | Krytyczny | Regular DR drills |
| CI time wzrośnie >10 min | Średnie | Niski | Parallel jobs, caching |

---

## 📋 CHECKLIST FINALIZACJI

Przed oznaczeniem systemu jako 5/5:

- [ ] Wszystkie P0 zakończone
- [ ] Wszystkie P1 zakończone
- [ ] Coverage >=80%
- [ ] 0 błędów mypy
- [ ] 0 błędów bandit (high)
- [ ] DR drill przeprowadzony
- [ ] Benchmarki wykonane
- [ ] Dokumentacja kompletna
- [ ] Code review przez 2 osoby
- [ ] Release tag v2.1.0

---

*Plan dokończenia systemu OpenBrain Unified do poziomu 5/5*  
*Wersja 1.0 | 2026-04-07*
