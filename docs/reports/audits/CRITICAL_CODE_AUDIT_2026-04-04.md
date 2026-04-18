# KRYTYCZNY AUDYT KODU I ARCHITEKTURY OPENBRAIN

**Data**: 2026-04-04  
**Audytor**: Automated Code Review  
**Status**: WYMAGANE DZIAŁANIE PRZED PRODUKCJĄ  

---

## 🔴 PROBLEMY KRYTYCZNE (MUSZĄ BYĆ NAPRAWIONE)

### 1. DUPLIKACJA KODU - main.py vs api/v1/ [SEVERITY: HIGH]

**Problem**: Funkcje v1_* istnieją w DWÓCH miejscach:
- `main.py` linie 381-1268 (**~900 linii** - legacy)
- `api/v1/memory.py` i `api/v1/obsidian.py` (nowe - **założenie refaktoryzacji**)

**Konsekwencje**:
- Niespójność zachowań (która wersja jest używana?)
- Podwójny maintenance
- Niejasność dla developerów

**Dowód**:
```bash
$ grep -n "async def v1_write" unified/src/main.py unified/src/api/v1/memory.py
main.py:381:async def v1_write(
api/v1/memory.py:44:async def v1_write(
```

**Rozwiązanie**: Usunąć wszystkie funkcje v1_* z main.py, routing powinien używać tylko api/v1/

---

### 2. RACE CONDITIONS - Global State bez Locków [SEVERITY: HIGH]

**Pliki**:
- `embed.py` (linie 126-132): `_embedding_cache`
- `auth.py` (linia 216): `POLICY_REGISTRY`
- `obsidian_adapter.py` (linia 372): `_VAULT_PATHS_CACHE`
- `api/v1/obsidian.py` (linie 52, 60): `_sync_tracker`, `_sync_engine`

**Problem**: Globalne zmienne modyfikowane bez synchronizacji w środowisku async:

```python
# embed.py - LINIE 126-132
async def get_embedding(text: str, model: str = "nomic-embed-text") -> list[float]:
    global _embedding_cache
    # ... 
    if len(_embedding_cache) >= _MAX_CACHE_SIZE:  # ← Read
        del _embedding_cache[oldest_key]           # ← Write (Race!)
    _embedding_cache[text_hash] = (embedding, model)  # ← Write (Race!)
```

**Konsekwencje**:
- Corrupted cache pod obciążeniem
- Utrata danych
- Nieprzewidywalne zachowanie

**Rozwiązanie**:
```python
import asyncio
_embedding_lock = asyncio.Lock()

async def get_embedding(...):
    async with _embedding_lock:
        # operacje na cache
```

---

### 3. main.py ZA DUŻY - Nieskończona Refaktoryzacja [SEVERITY: HIGH]

**Rozmiar**: 1315 linii  
**Cel**: <200 linii jako entry point

**Zawartość która nie powinna być w main.py**:
- Linie 246-369: Funkcje security (DUPLIKATY z `security/policy.py`):
  - `_is_scoped_user`
  - `_record_access_denied`
  - `_enforce_domain_access`
  - `_effective_domain_scope`
  - `_resolve_owner_for_write`
  - `_resolve_tenant_for_write`
  - `_apply_owner_scope`
  - `_enforce_memory_access`
  - `_hide_memory_access_denied`

- Linie 381-1268: Funkcje v1_* (DUPLIKATY z `api/v1/*`)

- Linie 135-246: Helpers (`_count_policy_skips`, `_safe_ratio`, etc.) - powinny być w `utils/` lub `telemetry/`

**Claim w commicie**: "Split main.py (1330 lines → modular structure)" - **FAŁSZYWY**  
**Rzeczywistość**: main.py wciąż zawiera ~900 linii kodu który powinien być w innych modułach

**Rozwiązanie**:
1. Usunąć duplikaty v1_* funkcji
2. Przenieść security helpers do `security/helpers.py`
3. Przenieść telemetry helpers do `telemetry/utils.py`

---

### 4. BRAK TESTÓW dla api/v1/obsidian.py [SEVERITY: MEDIUM-HIGH]

**Problem**: Brak dedykowanych testów dla 9 endpointów Obsidian API

**Endpointy bez testów**:
- `GET /api/v1/obsidian/vaults`
- `POST /api/v1/obsidian/read-note`
- `POST /api/v1/obsidian/sync`
- `POST /api/v1/obsidian/write-note`
- `POST /api/v1/obsidian/export`
- `POST /api/v1/obsidian/collection`
- `POST /api/v1/obsidian/bidirectional-sync`
- `GET /api/v1/obsidian/sync-status`
- `POST /api/v1/obsidian/update-note`

**Istniejące testy**:
- `test_obsidian_cli.py` - testuje CLI, nie API
- `test_api_endpoints_live.py` - ogólne testy, nie specyficzne dla v1

**Ryzyko**: Regresje, błędy w produkcji przy zmianach

---

## 🟡 PROBLEMY ŚREDNIE (POWINNY BYĆ NAPRAWIONE)

### 5. Konfiguracja Rozproszona (32 miejsca) [SEVERITY: MEDIUM]

**Problem**: Bezpośredni dostęp do `os.environ.get()` w 32 miejscach:

```python
# auth.py
PUBLIC_MODE = os.environ.get("PUBLIC_MODE", "").lower() == "true"
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").strip()
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "").strip()
...

# db.py
DB_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/openbrain_unified")

# app_factory.py
storage_uri=os.environ.get("REDIS_URL", "memory://")
```

**Konsekwencje**:
- Brak centralnej walidacji konfiguracji
- Trudność w testowaniu (mockowanie env)
- Brak type safety dla configu

**Rozwiązanie**: Użyć `pydantic-settings`:
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    public_mode: bool = False
    internal_api_key: str = ""
    database_url: str = "..."
    
    class Config:
        env_prefix = ""
```

---

### 6. Obsidian Sync używa print() [SEVERITY: MEDIUM]

**Plik**: `obsidian_sync.py`

**Linie z print()**:
- 157: `print(f"Warning: Could not load sync state: {e}")`
- 525: `print(f"Detecting changes for vault: {vault}...")`
- 533: `print(f"  Detected: {len(changes)} changes...")`
- 536: `print("  Dry run - no changes applied")`
- 541: `print("Applying changes...")`
- 544: `print(f"  Skipping conflict: {change.obsidian_path}")`
- 558: `print(f"  Applied: {result.changes_applied}...")`

**Konsekwencje**: Logi nie trafiają do systemów agregacji (ELK, Datadog, etc.)

**Rozwiązanie**: Zamienić na `structlog`:
```python
logger = structlog.get_logger()
logger.info("detecting_changes", vault=vault)
```

---

### 7. Za Długie Funkcje [SEVERITY: MEDIUM]

Funkcje przekraczające 50 linii (próg kompleksowości):

| Funkcja | Plik | Linie |
|---------|------|-------|
| `handle_memory_write` | memory_writes.py | 193 |
| `detect_changes` | obsidian_sync.py | 132 |
| `run_maintenance` | memory_writes.py | 113 |
| `apply_sync` | obsidian_sync.py | 97 |
| `register_v1_routes` | routes_v1.py | 96 |
| `register_crud_routes` | routes_crud.py | 93 |
| `handle_memory_write_many` | memory_writes.py | 83 |
| `v1_obsidian_export` | api/v1/obsidian.py | 73 |
| `v1_obsidian_export` | main.py | 69 |
| `v1_obsidian_collection` | api/v1/obsidian.py | 67 |

**Konsekwencje**:
- Trudność w testowaniu (za dużo ścieżek)
- Niska czytelność
- Wysoka złożoność cyklomatyczna

---

### 8. Duplikacja Repository Pattern [SEVERITY: MEDIUM]

**Pliki**:
- `repositories.py` (382 linie)
- `repositories/memory_repository.py` (390 linii)

**Problem**: Obie zawierają `SQLAlchemyMemoryRepository` - która jest używana?

```bash
$ grep -r "SQLAlchemyMemoryRepository" unified/src/
repositories.py:class SQLAlchemyMemoryRepository:
repositories/memory_repository.py:class SQLAlchemyMemoryRepository:
```

**Rozwiązanie**: Usunąć `repositories.py`, zostawić tylko `repositories/memory_repository.py`

---

### 9. Brak Thread-Safety w Vault Cache [SEVERITY: MEDIUM]

**Plik**: `obsidian_adapter.py:372`

```python
global _VAULT_PATHS_CACHE
if not _VAULT_PATHS_CACHE:  # ← Race
    _VAULT_PATHS_CACHE = _load_vault_paths()  # ← Race
```

---

## 🟢 PROBLEMY NISKIE (NICE TO HAVE)

### 10. Za Długie Linie (E501)

3 przypadki >88 znaków:
- `api/v1/health.py:34` (90 znaków)
- `api/v1/memory.py:78` (89 znaków)
- `api/v1/memory.py:112` (91 znaków)

### 11. Twarde Zakodowane Wartości

- `localhost:11434` (Ollama) - `embed.py:13`
- `localhost:5432` (PostgreSQL) - `db.py:19`
- `127.0.0.1:80` (MCP transport) - `mcp_transport.py:25`

### 12. Złożoność Importów

32 relatywne importy wyższego poziomu (`from ..x import`) - potencjalne ryzyko circular imports.

---

## REKOMENDOWANE DZIAŁANIA PRIORYTETOWE

### Sprint 1 (Krytyczne - Blokują Produkcję):

- [ ] **1.1** Usunąć DUPLIKATY funkcji v1_* z main.py (~900 linii)
- [ ] **1.2** Dodać `asyncio.Lock()` do `_embedding_cache` w embed.py
- [ ] **1.3** Dodać `asyncio.Lock()` do `_VAULT_PATHS_CACHE` w obsidian_adapter.py
- [ ] **1.4** Dodać `asyncio.Lock()` do `_sync_tracker` i `_sync_engine` w api/v1/obsidian.py
- [ ] **1.5** Przenieść funkcje security z main.py do security/policy.py

### Sprint 2 (Średnie - Wysoki Priorytet):

- [ ] **2.1** Stworzyć centralny config z pydantic-settings
- [ ] **2.2** Zamienić print() na logger w obsidian_sync.py
- [ ] **2.3** Napisać testy dla api/v1/obsidian.py (9 endpointów)
- [ ] **2.4** Rozdzielić `handle_memory_write` (193 linie) na mniejsze funkcje
- [ ] **2.5** Usunąć duplikat repositories.py

### Sprint 3 (Niskie - Techniczny Dług):

- [ ] **3.1** Naprawić E501 (za długie linie)
- [ ] **3.2** Wydzielić stałe do configu (localhosty, timeouty)
- [ ] **3.3] Uprościć strukturę importów

---

## OCENA KOŃCOWA

| Kryterium | Ocena | Uwagi |
|-----------|-------|-------|
| **Architektura** | ⚠️ C- | Duplikacja, nieskończona refaktoryzacja, main.py za duży |
| **Bezpieczeństwo** | ⚠️ C+ | Race conditions, global state bez locków |
| **Testowalność** | ⚠️ C | Brak testów dla nowych modułów v1 |
| **Wydajność** | ⚠️ C | Race conditions mogą powodować problemy pod obciążeniem |
| **Utrzymywalność** | ⚠️ D+ | Duplikacja kodu, za długie funkcje |
| **Dokumentacja** | ✅ B+ | Dobra dokumentacja zmian |

### WERDYKT

> **Kod NIE JEST GOTOWY do produkcji** bez naprawienia problemów krytycznych (Sprint 1).
>
> Commity sugerują "Complete architecture refactoring" ale rzeczywistość pokazuje
> **nieskończoną refaktoryzację** z poważnymi błędami architektonicznymi.
>
> Szacowany czas naprawy Sprint 1: **2-3 dni robocze**

---

## ZAŁĄCZNIKI

### A. Komendy do weryfikacji

```bash
# Sprawdź duplikaty
grep -n "async def v1_" unified/src/main.py unified/src/api/v1/*.py

# Sprawdź global state
grep -n "global " unified/src/*.py unified/src/**/*.py

# Sprawdź rozmiar plików
find unified/src -name "*.py" -exec wc -l {} + | sort -n | tail -10

# Sprawdź print()
grep -rn "print(" unified/src/ --include="*.py" | grep -v "__pycache__"
```

### B. Metryki

- **Całkowita liczba linii kodu**: ~8,473
- **Liczba plików Python**: 39
- **Funkcje >50 linii**: 15
- **Globalne zmienne**: 8
- **Miejsca z env access**: 32
- **Duplikaty funkcji**: 13 (v1_* w main.py + api/v1/)

---

*Raport wygenerowany automatycznie. Wymaga weryfikacji przez Senior Engineer.*
