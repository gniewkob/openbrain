# Szczegółowy Plan Refaktoryzacji OpenBrain

## Executive Summary

**Cel:** Poprawa architektury, bezpieczeństwa i utrzymywalności kodu  
**Czas:** 5-7 dni roboczych  
**Priorytet:** Krytyczne → Ważne → Poprawki jakościowe  
**Ryzyko:** Średnie (wymaga testów regresji)

---

## FAZA 1: Architektura - Podział main.py (Dni 1-3)

### 1.1 Struktura katalogów
```
src/
├── api/
│   ├── __init__.py
│   ├── dependencies.py      # Depends(), auth, session
│   ├── v1/
│   │   ├── __init__.py
│   │   ├── memory.py        # 5 endpointów V1 memory
│   │   ├── obsidian.py      # 9 endpointów V1 obsidian
│   │   └── health.py        # healthz, readyz
│   └── legacy/
│       ├── __init__.py
│       └── crud.py          # Legacy CRUD endpoints
├── services/
│   ├── __init__.py
│   ├── export.py            # Logika eksportu do Obsidian
│   ├── sync.py              # Bidirectional sync engine
│   └── converter.py         # Memory↔Note konwersja
├── security/
│   ├── __init__.py
│   ├── policy.py            # Domain governance, access control
│   └── audit.py             # Audit logging
└── main.py                  # Tylko bootstrap (50 linii max)
```

### 1.2 Zadania szczegółowe

#### Zadanie 1.1: Utworzenie struktury (4h)
**Pliki:** Nowe katalogi i pliki  
**Acceptance Criteria:**
- [ ] Katalogi `api/v1/`, `api/legacy/`, `services/`, `security/` utworzone
- [ ] Wszystkie `__init__.py` z poprawnymi exportami
- [ ] Importy działają: `from src.api.v1 import memory`

#### Zadanie 1.2: Przeniesienie endpointów V1 Memory (6h)
**Pliki:** 
- `src/api/v1/memory.py` (nowy)
- `src/main.py` (zmodyfikowany)

**Do przeniesienia:**
- `v1_write()` (lines ~373)
- `v1_write_many()` (lines ~394)
- `v1_find()` (lines ~411)
- `v1_get_context()` (lines ~423)
- `v1_get()` (lines ~443)

**Kod wzorcowy:**
```python
# src/api/v1/memory.py
from fastapi import APIRouter, Depends
from src.schemas import MemoryWriteRequest, MemoryWriteResponse
from src.services.memory_service import MemoryService

router = APIRouter(prefix="/memory", tags=["memory"])

@router.post("/write", response_model=MemoryWriteResponse)
async def write(
    req: MemoryWriteRequest,
    service: MemoryService = Depends(get_memory_service),
    user: dict = Depends(require_auth),
):
    return await service.write(req, user)
```

**Acceptance Criteria:**
- [ ] Wszystkie 5 endpointów działa (testy przechodzą)
- [ ] `main.py` skrócony o ~100 linii
- [ ] Brak zmian w logice biznesowej

#### Zadanie 1.3: Przeniesienie endpointów V1 Obsidian (8h)
**Pliki:**
- `src/api/v1/obsidian.py` (nowy)
- `src/services/export.py` (nowy)
- `src/services/converter.py` (nowy)

**Do przeniesienia:**
- `v1_obsidian_vaults()` (lines ~457)
- `v1_obsidian_read_note()` (lines ~468)
- `v1_obsidian_write_note()` (lines ~533)
- `v1_obsidian_update_note()` (lines ~1283)
- `v1_obsidian_sync()` (lines ~489)
- `v1_obsidian_export()` (lines ~566)
- `v1_obsidian_collection()` (lines ~638)
- `v1_obsidian_bidirectional_sync()` (lines ~1222)
- `v1_obsidian_sync_status()` (lines ~1271)

**Do wyodrębnienia do `services/export.py`:**
- `_memory_to_note_content()` (lines ~715)
- `_memory_to_frontmatter()` (lines ~758)
- `_build_collection_index()` (lines ~775)
- `_sanitize_filename()` (lines ~707)

**Acceptance Criteria:**
- [ ] Wszystkie 9 endpointów działa
- [ ] Logika konwersji wydzielona do services
- [ ] Testy integracyjne przechodzą

#### Zadanie 1.4: Przeniesienie Legacy CRUD (6h)
**Pliki:**
- `src/api/legacy/crud.py` (nowy)

**Do przeniesienia:**
- `create_memory()` (lines ~922)
- `create_memories_bulk()` (lines ~937)
- `bulk_upsert_memories()` (lines ~954)
- `read_memory()` (lines ~974)
- `read_memories()` (lines ~986)
- `search()` (lines ~1012)
- `update()` (lines ~1024)
- `delete()` (lines ~1050)
- `check_sync_endpoint()` (lines ~1071)
- `maintain()` (lines ~1117)
- `read_policy_registry()` (lines ~1133)
- `update_policy_registry()` (lines ~1140)
- `maintain_reports()` (lines ~1148)
- `maintain_report_detail()` (lines ~1157)
- `export()` (lines ~1168)

**Acceptance Criteria:**
- [ ] Wszystkie legacy endpointy działają
- [ ] Zachowana kompatybilność API

#### Zadanie 1.5: Wydzielenie Security (4h)
**Pliki:**
- `src/security/policy.py` (nowy)
- `src/security/audit.py` (nowy)

**Do przeniesienia do `security/policy.py`:**
- `_is_scoped_user()` (lines ~246)
- `_record_access_denied()` (lines ~250)
- `_require_admin()` (lines ~255)
- `_effective_domain_scope()` (lines ~263)
- `_enforce_domain_access()` (lines ~273)
- `_resolve_owner_for_write()` (lines ~291)
- `_resolve_tenant_for_write()` (lines ~303)
- `_apply_owner_scope()` (lines ~315)
- `_enforce_memory_access()` (lines ~346)
- `_hide_memory_access_denied()` (lines ~361)

**Do przeniesienia do `security/audit.py`:**
- `_audit()` z `crud_common.py` (jeśli tam jest)

**Acceptance Criteria:**
- [ ] Logika bezpieczeństwa wydzielona
- [ ] Reużywalne funkcje policy

#### Zadanie 1.6: Nowy main.py (4h)
**Pliki:**
- `src/main.py` (rewrite)

**Struktura docelowa (max 50 linii):**
```python
from fastapi import FastAPI
from src.api.v1 import memory as v1_memory, obsidian as v1_obsidian
from src.api.legacy import crud as legacy_crud
from src.api.v1.health import router as health_router

def create_application() -> FastAPI:
    app = create_app(...)
    
    # V1 API
    app.include_router(v1_memory.router, prefix="/api/v1")
    app.include_router(v1_obsidian.router, prefix="/api/v1")
    app.include_router(health_router)
    
    # Legacy
    register_crud_routes(app, legacy_handlers)
    register_ops_routes(app, ops_handlers)
    
    return app

app = create_application()
```

**Acceptance Criteria:**
- [ ] `main.py` < 100 linii
- [ ] Wszystkie endpointy działają
- [ ] Testy przechodzą

---

## FAZA 2: Circular Imports (Dzień 3-4)

### 2.1 Problem
Dynamiczne importy w `memory_writes.py`:
```python
def _crud_module():
    return import_module(f"{__package__}.crud")  # ANTYWZORZEC
```

### 2.2 Rozwiązanie: Dependency Injection

#### Zadanie 2.1: Refaktoryzacja memory_writes.py (6h)
**Pliki:**
- `src/memory_writes.py` (zmodyfikowany)
- `src/crud.py` (zmodyfikowany)
- `src/services/memory_service.py` (nowy)

**Plan:**
1. Utworzyć `MemoryService` klasę w `services/memory_service.py`
2. Przenieść logikę z `memory_writes.py` do klasy
3. Używać Dependency Injection w endpointach
4. Usunąć wszystkie `import_module`

**Kod wzorcowy:**
```python
# src/services/memory_service.py
class MemoryService:
    def __init__(
        self,
        session: AsyncSession,
        embed_client: EmbedClient,
        audit_logger: AuditLogger,
    ):
        self.session = session
        self.embed = embed_client
        self.audit = audit_logger
    
    async def write(self, data: MemoryCreate) -> MemoryOut:
        # Logika z handle_memory_write
        pass

# src/api/v1/memory.py
@router.post("/write")
async def write(
    req: MemoryWriteRequest,
    session: AsyncSession = Depends(get_session),
    service: MemoryService = Depends(get_memory_service),
):
    return await service.write(req)
```

**Acceptance Criteria:**
- [ ] Zero `import_module` w kodzie produkcyjnym
- [ ] Wszystkie testy przechodzą
- [ ] Brak regresji w wydajności

---

## FAZA 3: Błędy i Wyjątki (Dzień 4)

### 3.1 Konkretne wyjątki zamiast Exception

#### Zadanie 3.1: Mapowanie wyjątków (6h)
**Pliki:**
- `src/exceptions.py` (rozszerzony)
- `src/db.py`
- `src/memory_writes.py`
- `src/lifespan.py`

**Do zaimplementowania:**
```python
# src/exceptions.py - dodać mapowanie
EXCEPTION_MAPPING = {
    # SQLAlchemy
    sqlalchemy.exc.IntegrityError: DuplicateKeyError,
    sqlalchemy.exc.OperationalError: DatabaseError,
    sqlalchemy.exc.TimeoutError: DatabaseTimeoutError,
    # AsyncPG
    asyncpg.exceptions.UniqueViolationError: DuplicateKeyError,
    asyncpg.exceptions.ConnectionError: DatabaseConnectionError,
    # HTTP
    httpx.TimeoutException: ExternalServiceTimeoutError,
    httpx.HTTPStatusError: ExternalServiceError,
}

# Dekorator do użycia w całej aplikacji
def map_exceptions(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except OpenBrainError:
            raise
        except Exception as e:
            for exc_type, target in EXCEPTION_MAPPING.items():
                if isinstance(e, exc_type):
                    raise target(str(e)) from e
            raise InternalError(str(e)) from e
    return wrapper
```

**Miejsca do poprawy (18 miejsc):**
1. `lifespan.py:41` - telemetry sync
2. `lifespan.py:63` - telemetry load
3. `lifespan.py:83` - telemetry flush
4. `lifespan.py:89` - embedding shutdown
5. `db.py:27` - URL parsing
6. `auth.py:134` - token verification
7. `memory_writes.py:318` - batch record
8. `memory_writes.py:342` - atomic operation
9. `main.py:625` - export error
10. `main.py:731` - template error
11. `main.py:869` - readyz check
12. `obsidian_adapter.py:492` - delete note
13. `obsidian_sync.py:263` - list files
14. `obsidian_sync.py:460` - import error
15. `obsidian_sync.py:486` - update error
16. `obsidian_sync.py:499` - apply sync
17. `mcp_transport.py:84` - tool error
18. `mcp_transport.py:170` - HTTP error

**Acceptance Criteria:**
- [ ] 0 x `except Exception:` w kodzie produkcyjnym
- [ ] Wszystkie wyjątki mapowane na OpenBrainError
- [ ] Testy wyjątków przechodzą

---

## FAZA 4: Infrastruktura (Dzień 4-5)

### 4.1 Circuit Breaker dla Ollama

#### Zadanie 4.1: Implementacja Circuit Breaker (4h)
**Pliki:**
- `src/infrastructure/circuit_breaker.py` (nowy)
- `src/embed.py` (zmodyfikowany)

**Implementacja:**
```python
# src/infrastructure/circuit_breaker.py
import time
from enum import Enum
from functools import wraps

class CircuitState(Enum):
    CLOSED = "closed"      # Normalna praca
    OPEN = "open"         # Wyłączone
    HALF_OPEN = "half_open"  # Testowanie

class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED
    
    def call(self, func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if self.state == CircuitState.OPEN:
                if time.time() - self.last_failure_time > self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                else:
                    raise CircuitBreakerOpenError("Service temporarily unavailable")
            
            try:
                result = await func(*args, **kwargs)
                if self.state == CircuitState.HALF_OPEN:
                    self.state = CircuitState.CLOSED
                    self.failures = 0
                return result
            except Exception as e:
                self.failures += 1
                self.last_failure_time = time.time()
                if self.failures >= self.failure_threshold:
                    self.state = CircuitState.OPEN
                raise
        return wrapper

# Użycie w embed.py
circuit = CircuitBreaker(failure_threshold=3, recovery_timeout=30)

@circuit.call
async def get_embedding(text: str) -> list[float]:
    ...
```

**Acceptance Criteria:**
- [ ] Przy 3 błędach - circuit otwiera się
- [ ] Przez 30s zwraca CircuitBreakerOpenError
- [ ] Po 30s - half-open (testuje jedno zapytanie)
- [ ] Testy integracyjne circuit breaker

### 4.2 Limit rozmiaru payload

#### Zadanie 4.2: Content Size Limit (2h)
**Pliki:**
- `src/app_factory.py`
- `src/middleware.py` (rozszerzony)

**Implementacja:**
```python
# src/middleware.py
from starlette.middleware.base import BaseHTTPMiddleware

class ContentSizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_content_size: int = 10 * 1024 * 1024):
        super().__init__(app)
        self.max_content_size = max_content_size
    
    async def dispatch(self, request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_content_size:
            return JSONResponse(
                status_code=413,
                content={"error": "Payload too large", "max_size": self.max_content_size}
            )
        return await call_next(request)

# W app_factory.py
app.add_middleware(ContentSizeLimitMiddleware, max_content_size=10*1024*1024)
```

**Acceptance Criteria:**
- [ ] Payload > 10MB → HTTP 413
- [ ] Payload < 10MB → przepuszcza
- [ ] Testy middleware

### 4.3 Ujednolicenie logging

#### Zadanie 4.3: Migracja do structlog (2h)
**Pliki:**
- `src/auth.py`
- `src/combined.py`
- `src/obsidian_sync.py`

**Zmiana:**
```python
# Zamiast:
import logging
log = logging.getLogger(__name__)

# Użyć:
import structlog
log = structlog.get_logger()
```

**Acceptance Criteria:**
- [ ] 0 x `import logging` w kodzie
- [ ] Wszystkie logi w formacie JSON
- [ ] Spójne context vars

---

## FAZA 5: Testy (Dzień 5-6)

### 5.1 Testy obciążeniowe

#### Zadanie 5.1: Locust tests (6h)
**Pliki:**
- `tests/load/locustfile.py` (nowy)

**Scenariusze:**
```python
from locust import HttpUser, task, between

class OpenBrainUser(HttpUser):
    wait_time = between(1, 3)
    
    @task(5)
    def get_context(self):
        self.client.post("/api/v1/memory/get-context", json={"query": "test"})
    
    @task(3)
    def write_memory(self):
        self.client.post("/api/v1/memory/write", json={
            "content": "Test content",
            "domain": "build",
            "entity_type": "Test"
        })
    
    @task(1)
    def health_check(self):
        self.client.get("/healthz")
```

**Acceptance Criteria:**
- [ ] 100 req/s bez błędów
- [ ] Latency p95 < 200ms
- [ ] Memory usage stable

### 5.2 Property-based tests

#### Zadanie 5.2: Hypothesis tests (4h)
**Pliki:**
- `tests/property/test_memory_properties.py`

**Przykład:**
```python
from hypothesis import given, strategies as st

@given(st.text(min_size=1, max_size=10000))
def test_embedding_consistency(text):
    """Same text = same embedding"""
    emb1 = get_embedding(text)
    emb2 = get_embedding(text)
    assert emb1 == emb2

@given(st.lists(st.dictionaries(...), min_size=1, max_size=100))
def test_batch_write_all_succeed_or_fail_together(records):
    """Atomic batch writes"""
    ...
```

---

## FAZA 6: Metryki i Monitoring (Dzień 6-7)

### 6.1 Dodatkowe metryki

#### Zadanie 6.1: Histogramy czasu (4h)
**Pliki:**
- `src/telemetry.py` (rozszerzony)
- `src/middleware.py` (rozszerzony)

**Do dodania:**
```python
# Histogram czasu per endpoint
http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration',
    ['method', 'endpoint', 'status_code']
)

# Licznik błędów per typ
error_counter = Counter(
    'openbrain_errors_total',
    'Total errors',
    ['error_type', 'endpoint']
)

# Gauge aktywnych połączeń DB
db_connections_active = Gauge(
    'db_connections_active',
    'Active database connections'
)
```

**Acceptance Criteria:**
- [ ] Prometheus metrics rozszerzone
- [ ] Grafana dashboard updated
- [ ] Alerty na błędy

---

## Szacowanie czasu

| Faza | Zadanie | Szacowany czas | Ryzyko |
|------|---------|---------------|--------|
| **1.1** | Struktura katalogów | 4h | Niskie |
| **1.2** | V1 Memory | 6h | Niskie |
| **1.3** | V1 Obsidian | 8h | Średnie |
| **1.4** | Legacy CRUD | 6h | Średnie |
| **1.5** | Security | 4h | Niskie |
| **1.6** | Nowy main.py | 4h | Średnie |
| **2.1** | Circular imports | 6h | Wysokie |
| **3.1** | Exception mapping | 6h | Średnie |
| **4.1** | Circuit breaker | 4h | Niskie |
| **4.2** | Content size limit | 2h | Niskie |
| **4.3** | Logging unify | 2h | Niskie |
| **5.1** | Locust tests | 6h | Niskie |
| **6.1** | Metrics | 4h | Niskie |
| **RAZEM** | | **66h (~8-9 dni)** | |

---

## Plan wykonawczy (zalecany)

### Tydzień 1
- **Pon-Wt:** Faza 1.1-1.3 (V1 endpoints)
- **Śr:** Faza 1.4-1.6 (Legacy + main.py)
- **Czw:** Faza 2 (Circular imports)
- **Pt:** Faza 3 (Exceptions) + Code review

### Tydzień 2
- **Pon:** Faza 4 (Infrastruktura)
- **Wt-Śr:** Faza 5 (Testy)
- **Czw:** Faza 6 (Metryki) + dokumentacja
- **Pt:** Finalne testy, deploy

---

## Kryteria sukcesu

### Techniczne
- [ ] `main.py` < 100 linii
- [ ] 0 x `except Exception:`
- [ ] 0 x `import_module` dynamiczny
- [ ] 100% testów przechodzi
- [ ] Testy obciążeniowe: 100 req/s

### Biznesowe
- [ ] Zero downtime deploy
- [ ] Brak regresji w API
- [ ] Poprawiona wydajność (cache hit ratio > 80%)

---

## Rollback Plan

**Jeśli coś pójdzie nie tak:**
1. Branch `refactoring/main-split` - nie merguj do main bezpośrednio
2. Feature flags dla nowych endpointów (możliwość wyłączenia)
3. Canary deploy - 10% ruchu na nowy kod
4. Automatyczny rollback na podstawie error rate (> 1%)

---

## Zalecane narzędzia

```bash
# Static analysis
pip install wily  # cyclomatic complexity
wily rank src/main.py

# Security
pip install bandit
bandit -r src/

# Dependencies
cd unified && pipdeptree | grep -E "^\w+"

# Performance profiling
pip install py-spy
py-spy record -o profile.svg -- python -m src.main
```

---

## Podsumowanie

**Najważniejsze:**
1. **Podział main.py** - najwyższy priorytet, największy wpływ
2. **Circuit breaker** - zabezpiecza przed awariami Ollama
3. **Testy obciążeniowe** - weryfikacja wydajności

**Można pominąć (jeśli mało czasu):**
- Property-based tests (zamiast nich więcej unit tests)
- Dodatkowe metryki (podstawowe już są)
- Content size limit (nginx może to robić)

**Nie można pominąć:**
- Podział main.py
- Naprawa circular imports
- Konkretne wyjątki zamiast Exception
