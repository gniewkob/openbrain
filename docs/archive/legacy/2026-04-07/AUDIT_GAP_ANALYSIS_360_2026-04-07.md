# 📊 Analiza Luk i Zależności - Audyt 360° OpenBrain Unified

**Data analizy:** 2026-04-07  
**Raport bazuje na:** docs/audit-report-360-2026-04-07.md, docs/CRITICAL_CODE_AUDIT_2026-04-04.md, docs/code-audit-360-2026-04-03.md  
**Zakres:** unified/src/ (39 plików, ~8,944 LOC)

---

## 🎯 PODSUMOWANIE WYKONAWCZE

| Kategoria | Liczba zagadnień | Priorytet P0 | Priorytet P1 | Priorytet P2 |
|-----------|------------------|--------------|--------------|--------------|
| Błędy typów (mypy) | 53 | 53 | 0 | 0 |
| Infrastruktura (backup/DR) | 4 | 1 | 2 | 1 |
| CI/CD | 4 | 2 | 2 | 0 |
| Wydajność | 5 | 0 | 3 | 2 |
| Dokumentacja | 3 | 0 | 1 | 2 |
| Tech Debt | 6 | 0 | 2 | 4 |
| **RAZEM** | **75** | **56** | **10** | **9** |

---

## 🔴 PROBLEMY KRYTYCZNE (P0) - Wymagają natychmiastowej naprawy

### 1. Błędy Mypy - 53 błędy wymagające naprawy

#### Lokalizacja plików i typy błędów:

| Plik | Liczba błędów | Szacowane linie | Główne typy błędów |
|------|---------------|-----------------|-------------------|
| `memory_writes.py` | ~11 | 366-445, 449-551 | brakujące typy zwracane, `Optional[]`, `Any` |
| `api/v1/memory.py` | ~7 | 82-348 | zależności FastAPI, brakujące adnotacje Depends |
| `api/v1/obsidian.py` | ~5 | 82-456 | podobne jak memory.py, dodatkowo typy sync |
| `crud_common.py` | ~3 | 123-270 | `_to_record()`, `_to_out()` - złożone typy |
| `crud.py` | ~5 | cały plik | brakujące typy zwracane z CRUD operations |
| `mcp_transport.py` | ~8 | 534 linii | narzędzia MCP, batch operacje |
| `memory_reads.py` | ~6 | 464 linii | wyszukiwanie, filtry, embedding queries |
| `schemas.py` | ~4 | 613 linii | Pydantic modele - brakujące Optional |
| `auth.py` | ~2 | 597 linii | JWT claims, dict[str, Any] |
| `embed.py` | ~2 | 234 linie | Circuit breaker, cache types |

#### Szczegółowe problemy typowe (na podstawie analizy kodu):

**W `memory_writes.py` (linie 366-445):**
```python
# Problem: Funkcja zwraca MemoryWriteResponse ale typ nie jest jawnie określony
async def handle_memory_write(
    session: AsyncSession,
    request: MemoryWriteRequest,
    actor: str = "agent",
    _commit: bool = True,
) -> MemoryWriteResponse:  # OK, ale wewnętrzne zmienne bez typów
    rec = request.record  # Brak typu: should be MemoryWriteRecord
    mode = request.write_mode  # Brak typu: should be WriteMode
    ...
```

**W `api/v1/memory.py` (linia 128):**
```python
# Problem: brak typu zwracanego w niektórych przypadkach
async def v1_find(...) -> list[dict[str, Any]]:  # Zbyt ogólny typ
```

**W `crud_common.py` (linie 123-157):**
```python
# Problem: konwersja SQLAlchemy model -> Pydantic schema bez pełnych adnotacji
def _to_record(m: Memory) -> MemoryRecord:
    meta = m.metadata_ or {}  # Brak typu: should be dict[str, Any]
    source = meta.get("source", {})  # Brak typu
```

### 2. Brakująca Infrastruktura Krytyczna

| Element | Status | Lokalizacja | Konsekwencje |
|---------|--------|-------------|--------------|
| **Automated backups** | ❌ BRAK | Brak skryptów | Utrata danych przy awarii |
| **Point-in-Time Recovery** | ❌ BRAK | PostgreSQL config | Brak możliwości przywracania |
| **DR Plan** | ❌ BRAK | Dokumentacja | Brak procedur awaryjnych |

---

## 🟠 PROBLEMY WYSOKIEGO PRIORYTETU (P1)

### 3. CI/CD Braki

| Element | Obecny Status | Wymagane | Lokalizacja |
|---------|--------------|----------|-------------|
| **mypy w CI** | ❌ Brak | Wymagane | `.github/workflows/ci.yml` |
| **pytest-cov (coverage)** | ❌ Brak | Wymagane | brak raportowania pokrycia |
| **bandit (security lint)** | ❌ Brak | Zalecane | brak skanowania bezpieczeństwa |
| **pre-commit hooks** | ❌ Brak | Zalecane | brak `.pre-commit-config.yaml` |

Obecny CI (`ci.yml` linie 10-91):
```yaml
jobs:
  lint:    # Tylko Ruff
  test:    # Pytest bez coverage
  security: # Tylko pip-audit
```

Brakuje:
```yaml
  typecheck:  # mypy
  coverage:   # pytest-cov
  bandit:     # security lint
```

### 4. Problemy z Wydajnością (P1)

| Problem | Plik | Linie | Opis | Rozwiązanie |
|---------|------|-------|------|-------------|
| **Telemetry per-process** | `telemetry.py` | 1-249 | Registry w pamięci procesu | Shared backend (Redis) |
| **Connection pool MCP** | `mcp_transport.py` | 68-76 | Nowy client na żądanie | Singleton w `app.state` |
| **Race conditions w cache** | `embed.py` | 103-116, 166-173 | Globalny cache bez locków | `asyncio.Lock` już dodany ✅ |

### 5. Tech Debt - P1

| Problem | Plik | Linia | Opis |
|---------|------|-------|------|
| **Konfiguracja rozproszona** | 9 plików | 32 miejsca | Bezpośredni `os.environ.get()` |
| **Brak testów dla api/v1/obsidian.py** | `tests/` | - | 9 endpointów bez testów |

**Pliki z bezpośrednim dostępem do env:**
- `auth.py` - linie 31-41
- `db.py` - konfiguracja bazy
- `app_factory.py` - linia 141
- `memory_writes.py` - linia 774 (MAINTENANCE_TIMEOUT_S)
- `api/v1/obsidian.py` - linia 365 (OBSIDIAN_SYNC_TIMEOUT_S)
- `obsidian_adapter.py` - konfiguracja vault

---

## 🟡 PROBLEMY NISKIEGO PRIORYTETU (P2)

### 6. Dokumentacja

| Element | Status | Priorytet |
|---------|--------|-----------|
| Docstrings w schematach | Częściowo | P2 |
| Procedura DR (RTO/RPO) | Brak | P1 |
| Dokumentacja API versioning | Brak | P2 |

### 7. Tech Debt - P2

| Problem | Plik | Linie | Szacowany wysiłek |
|---------|------|-------|-------------------|
| Za długie funkcje (>50 linii) | 6 funkcji | różne | 2-3 dni |
| Za długie linie (E501) | 3 miejsca | 34, 78, 112 | 30 min |
| Twarde zakodowane wartości | 3 miejsca | localhost:11434, 5432, 80 | 1-2h |
| Duplikacja helperów testowych | `tests/` | - | 1 dzień |

**Funkcje >50 linii:**
1. `handle_memory_write` (memory_writes.py) - 80 linii (linie 366-445)
2. `detect_changes` (obsidian_sync.py) - 132 linie (linie 435-566)
3. `run_maintenance` (memory_writes.py) - 113 linii (linie 770-941)
4. `apply_sync` (obsidian_sync.py) - 97 linii (linie 599-723)
5. `register_v1_routes` (routes_v1.py) - 96 linii
6. `register_crud_routes` (routes_crud.py) - 93 linii

---

## 🗺️ MAPA ZALEŻNOŚCI - CO TRZEBA ZROBIĆ NAJPIERW

```
ETAP 1: KRYTYCZNE (P0) - Tydzień 1
┌─────────────────────────────────────────────────────────────────┐
│ 1.1 Naprawić 53 błędy mypy                                      │
│     ├── memory_writes.py (11 błędów)                           │
│     ├── api/v1/memory.py (7 błędów)                            │
│     ├── api/v1/obsidian.py (5 błędów)                          │
│     ├── crud_common.py (3 błędy)                               │
│     ├── mcp_transport.py (8 błędów)                            │
│     ├── memory_reads.py (6 błędów)                             │
│     └── Pozostałe (13 błędów)                                  │
│                                                                 │
│ 1.2 Skrypt backupu PostgreSQL                                   │
│     ├── pg_dump automation                                     │
│     ├── Retention policy (7/30 dni)                            │
│     └── S3 upload                                              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
ETAP 2: CI/CD I INFRASTRUKTURA (P0/P1) - Tydzień 2
┌─────────────────────────────────────────────────────────────────┐
│ 2.1 Dodać mypy do CI                                            │
│     ├── Zależy od: 1.1 (błędy mypy naprawione)                 │
│     └── .github/workflows/ci.yml - nowy job                    │
│                                                                 │
│ 2.2 Dodać pytest-cov do CI                                      │
│     └── Coverage threshold: 80%                                │
│                                                                 │
│ 2.3 Implementacja backupu + DR docs                             │
│     ├── Zależy od: 1.2 (skrypt backupu)                        │
│     └── docs/DISASTER_RECOVERY.md                              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
ETAP 3: WYDAJNOŚĆ I BEZPIECZEŃSTWO (P1) - Tydzień 3-4
┌─────────────────────────────────────────────────────────────────┐
│ 3.1 Shared telemetry backend                                    │
│     ├── Redis jako backend dla metrics                         │
│     ├── Zależy od: stabilnego Redis                            │
│     └── telemetry.py refactor                                  │
│                                                                 │
│ 3.2 Connection pool dla MCP                                     │
│     ├── Singleton w app.state                                  │
│     └── mcp_transport.py refactor                              │
│                                                                 │
│ 3.3 Bandit w CI                                                 │
│     ├── Zależy od: stabilnego CI                               │
│     └── .github/workflows/ci.yml                               │
│                                                                 │
│ 3.4 Pre-commit hooks                                            │
│     ├── .pre-commit-config.yaml                                │
│     ├── ruff, mypy, bandit                                     │
│     └── Zależy od: 2.1 (mypy w CI)                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
ETAP 4: REFAKTORYZACJA (P2) - Tydzień 5+
┌─────────────────────────────────────────────────────────────────┐
│ 4.1 Centralna konfiguracja (pydantic-settings)                  │
│     ├── Zależy od: testów stability                            │
│     └── 32 miejsca z env access                                │
│                                                                 │
│ 4.2 Podzielić długie funkcje                                    │
│     ├── handle_memory_write -> _create, _update, _version      │
│     ├── detect_changes -> mniejsze funkcje                     │
│     └── run_maintenance -> dedup, normalize, fix_links         │
│                                                                 │
│ 4.3 Testy dla api/v1/obsidian.py                                │
│     ├── 9 endpointów do pokrycia                               │
│     └── Zależy od: stabilnego API                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔗 SZCZEGÓŁOWE ZALEŻNOŚCI MIĘDZY PROBLEMAMI

### Graf zależności (skrócony):

```
[53 błędy mypy]
      │
      ├── blokują ──> [mypy w CI] (nie można dodać do CI zanim nie naprawione)
      │
      └── blokują częściowo ──> [pre-commit hooks] (mypy w hooks)

[Backup PostgreSQL]
      │
      └── wymagane dla ──> [DR Plan] (nie można mieć DR bez backupu)

[Centralna konfiguracja pydantic-settings]
      │
      ├── ułatwia ──> [32 env access] (zastępuje je)
      ├── ułatwia ──> [Testowanie] (łatwiejsze mockowanie)
      └── zależy od ──> [Testy stability] (breaking change)

[Shared telemetry backend]
      │
      ├── wymaga ──> [Redis] (już dostępny w docker-compose)
      └── zależy od ──> [Stabilność API] (nie podczas refaktoryzacji)

[Connection pool dla MCP]
      │
      ├── wymaga ──> [Singleton pattern]
      └── zależy od ──> [App lifecycle] (app.state)
```

---

## 📋 CHECKLIST IMPLEMENTACJI

### Sprint 1 (Tydzień 1): P0 - Mypy + Backup
```
□ memory_writes.py - 11 błędów
  □ handle_memory_write - dodac pełne typy
  □ _create_new_memory, _version_memory, _update_memory
  □ handle_memory_write_many - typy dla batch
  
□ api/v1/memory.py - 7 błędów
  □ v1_write, v1_write_many, v1_find
  □ v1_get_context, v1_get, v1_update
  
□ api/v1/obsidian.py - 5 błędów
□ crud_common.py - 3 błędy
□ Pozostałe pliki - 27 błędów
□ Skrypt backupu PostgreSQL
```

### Sprint 2 (Tydzień 2): CI/CD + DR
```
□ Dodać mypy do .github/workflows/ci.yml
□ Dodać pytest-cov z threshold 80%
□ Dokumentacja DR (RTO/RPO)
□ Test recovery procedure
```

### Sprint 3 (Tydzień 3-4): Wydajność + Security
```
□ Shared telemetry backend (Redis)
□ Connection pool dla MCP
□ Bandit w CI
□ Pre-commit hooks (.pre-commit-config.yaml)
```

### Sprint 4 (Tydzień 5+): Refaktoryzacja
```
□ pydantic-settings dla konfiguracji
□ Podział długich funkcji
□ Testy dla api/v1/obsidian.py
□ Stałe do configu (localhosty)
```

---

## ⚠️ RYZYKA I UWAGI

### Ryzyka blokujące:

1. **Naprawa mypy może ujawnić ukryte bugi** - wymaga dokładnego testowania
2. **Shared telemetry może wpłynąć na wydajność** - wymaga benchmarków
3. **Centralna konfiguracja to breaking change** - wymaga aktualizacji env

### Rekomendacje:

1. **NIE** dodawać mypy do CI zanim nie naprawione wszystkie 53 błędy
2. **NIE** wdrażać shared telemetry bez testów wydajnościowych
3. **TAK** najpierw zrobić backup, potem DR plan
4. **TAK** używać feature flags dla shared telemetry

---

## 📊 METRYKI SUKCESU

| Metryka | Obecnie | Cel | Deadline |
|---------|---------|-----|----------|
| Błędy mypy | 53 | 0 | Tydzień 1 |
| Coverage | brak danych | >80% | Tydzień 2 |
| Backup | brak | codzienny | Tydzień 1 |
| Funkcje >50 linii | 6 | ≤3 | Tydzień 5 |
| Env access | 32 miejsca | 1 (config) | Tydzień 5 |

---

*Raport wygenerowany przez analizę automatyczną*  
*Data: 2026-04-07*  
*System: OpenBrain Unified v2.x*
