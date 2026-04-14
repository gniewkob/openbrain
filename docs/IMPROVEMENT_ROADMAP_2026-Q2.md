# PLAN POPRAWY TECHNICAL DEBT - Q2 2026

**Data**: 2026-04-04  
**Aktualizacja**: 2026-04-14  
**Czas realizacji**: 6-8 tygodni  
**Status**: W toku

## Postęp (stan 2026-04-14)

| # | Zadanie | Status |
|---|---|---|
| — | 100% pokrycie testów (1403 testów) | ✅ DONE |
| — | `aiofiles` jako oficjalna zależność projektu | ✅ DONE |
| — | Refaktoryzacja `detect_changes()` | ⏳ TODO |
| — | Refaktoryzacja `run_maintenance()` | ⏳ TODO |
| 1.1 | Naprawa E501 long lines | ⏳ TODO |
| 1.2 | Black/Ruff format enforcement | ⏳ TODO |

---

---

## PRIORYTETY I ETAPY

### FAZA 1: Code Style & Consistency (Tydzień 1-2)

#### 1.1 Naprawa E501 - Za długie linie
**Cel**: Wszystkie linie <88 znaków (standard Ruff)

**Szacunkowa liczba**: ~200 linii do naprawy

**Kroki**:
```bash
# Automatyczna naprawa (szacunkowo 50% przypadków)
cd unified
ruff check src/ --select=E501 --fix

# Ręczna naprawa pozostałych (ciężkie przypadki)
# - Długie stringi → podzielić na wielolinijkowe
# - Zagnieżdżone wywołania → zmienne tymczasowe
# - Długie listy/dict → jeden element na linię
```

**Szacunkowy czas**: 8h

---

#### 1.2 Auto-formatowanie z Black
**Krok opcjonalny** (alternatywa do Ruff):

```bash
pip install black
black src/ --line-length 88
```

**Uwaga**: Wymaga dyskusji zespołowej - czy wdrożyć Black do CI?

---

### FAZA 2: Funkcje o wysokiej złożoności (Tydzień 3-4)

#### 2.1 `detect_changes()` - 132 linie, złożoność 21
**Plik**: `src/obsidian_sync.py`

**Plan refaktoryzacji**:
```python
# OBECNIE:
async def detect_changes(...) -> SyncResult:
    # 132 linie kodu z 21 rozgałęzieniami

# PO REFAKTORYZACJI:
async def detect_changes(...) -> SyncResult:
    changes = await _detect_vault_changes(vault)
    conflicts = await _identify_conflicts(changes)
    return await _build_sync_result(changes, conflicts)

async def _detect_vault_changes(vault: str) -> list[Change]:
    # ~40 linii

async def _identify_conflicts(changes: list[Change]) -> list[Conflict]:
    # ~40 linii

async def _build_sync_result(...) -> SyncResult:
    # ~30 linii
```

**Szacunkowy czas**: 12h (wymaga testów integracyjnych)

---

#### 2.2 `run_maintenance()` - 113 linie, złożoność 20
**Plik**: `src/memory_writes.py`

**Plan refaktoryzacji**:
```python
# Rozbić na mniejsze funkcje:
- _collect_maintenance_candidates()
- _process_duplicates()
- _process_policy_skips()
- _build_maintenance_report()
```

**Szacunkowy czas**: 10h

---

#### 2.3 `app()` w combined.py - złożoność 16
**Plik**: `src/combined.py`

**Plan**: Rozbić routing na osobne funkcje:
```python
async def app(scope, receive, send):
    if _is_health_check(scope):
        return await _handle_health(scope, receive, send)
    if _is_api_request(scope):
        return await _handle_api(scope, receive, send)
    # ...
```

**Szacunkowy czas**: 6h

---

### FAZA 3: Dokumentacja (Tydzień 5)

#### 3.1 Docstrings dla publicznych funkcji
**Cel**: 90 funkcji bez dokumentacji → 0

**Szablon**:
```python
def function_name(param: Type) -> ReturnType:
    """Krótki opis funkcji.
    
    Args:
        param: Opis parametru
        
    Returns:
        Opis zwracanej wartości
        
    Raises:
        ExceptionType: Kiedy wyjątek
        
    Example:
        >>> function_name(value)
        result
    """
```

**Priorytetowe moduły**:
1. `src/auth.py` - 15 funkcji
2. `src/api/v1/*.py` - 20 funkcji
3. `src/memory_reads.py` - 12 funkcji
4. `src/memory_writes.py` - 10 funkcji

**Szacunkowy czas**: 16h (przy użyciu Copilot/GPT do generowania szablonów)

---

### FAZA 4: Test Coverage (Tydzień 6-7)

#### 4.1 Priorytetowe moduły bez testów

| Moduł | Priorytet | Szacunkowy czas |
|-------|-----------|-----------------|
| `obsidian_sync.py` | Wysoki | 12h |
| `memory_reads.py` | Wysoki | 8h |
| `repositories/` | Średni | 6h |
| `middleware.py` | Średni | 4h |
| `telemetry*.py` | Niski | 4h |

**Cel**: Test coverage >70%

---

#### 4.2 Testy integracyjne dla Obsidian
**Plik**: `tests/integration/test_obsidian_sync.py`

**Scenariusze**:
- Eksport notatki do Obsidian
- Import notatki z Obsidian
- Konflikty w bidirectional sync
- Dry-run mode

**Szacunkowy czas**: 10h

---

### FAZA 5: Dodatkowe usprawnienia (Tydzień 8)

#### 5.1 Type Hints (opcjonalne)
- Dodać brakujące `-> None` w funkcjach
- Dodać `Any` tam gdzie potrzebne

#### 5.2 Logowanie strukturalne
- Ujednolicić nazewnictwo logów
- Dodać context (request_id, user_id)

#### 5.3 Optymalizacje wydajności
- Profilowanie z `cProfile`
- Optymalizacja zapytań SQL (N+1 queries)

---

## HARMONOGRAM

```
Tydzień 1-2:  [E501] Code Style
Tydzień 3-4:  [REFACTOR] Complex Functions
Tydzień 5:    [DOCS] Docstrings
Tydzień 6-7:  [TESTS] Coverage
Tydzień 8:    [POLISH] Finalne usprawnienia
```

**Suma godzin**: ~80h (2 tygodnie pracy 1 osoby)

---

## NARZĘDZIA I AUTOMATYZACJA

### Pre-commit hooks
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.3.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.8.0
    hooks:
      - id: mypy
```

### Makefile targets
```makefile
style:
	ruff check src/ --select=E501 --fix
	ruff format src/

test-coverage:
	pytest tests/ --cov=src --cov-report=html --cov-fail-under=70

docs-check:
	interrogate src/ --fail-under=80
```

---

## METRYKI SUKCESU

| Metryka | Obecnie | Cel | Jak mierzyć |
|---------|---------|-----|-------------|
| E501 errors | ~200 | 0 | `ruff check --select=E501` |
| Cyclomatic complexity (max) | 21 | <15 | `radon cc src/` |
| Functions >80 lines | 6 | <3 | AST analysis |
| Docstrings coverage | ~30% | >80% | `interrogate` |
| Test coverage | ~40% | >70% | `pytest --cov` |
| Ruff errors | 0 | 0 | `ruff check src/` |

---

## RYZYKA I WYZWANIA

### Ryzyko 1: Refaktoryzacja obsidian_sync
- **Wpływ**: Wysoki (krytyczna funkcjonalność)
- **Mitigacja**: Przed refaktoryzacją dodać integracyjne testy E2E

### Ryzyko 2: Test coverage
- **Wpływ**: Średni (czasochłonne)
- **Mitigacja**: Priorytetowość krytycznych ścieżek

### Ryzyko 3: Breaking changes
- **Wpływ**: Niski
- **Mitigacja**: Tylko refactor wewnętrzny, API bez zmian

---

## REKOMENDACJA IMPLEMENTACJI

**Opcja A**: Pełna realizacja (80h)
- Zatrudnić dodatkowego deva na 2 tygodnie
- Lub: 1 sprint (2 tygodnie) zespołu

**Opcja B**: Iteracyjna (20h/tydzień)
- 1 dzień w tygodniu na technical debt
- Realizacja przez 8 tygodni

**Opcja C**: Minimalna (20h)
- Tylko Faza 1 (E501) + Faza 4 (testy dla obsidian)
- Reszta "jak czas pozwoli"

---

## NASTĘPNE KROKI

1. [ ] Dyskusja zespołowa: Którą opcję wybrać?
2. [ ] Utworzenie ticketów w systemie (Jira/GitHub Issues)
3. [ ] Przydział osób do zadań
4. [ ] Sprint planning

---

*Plan przygotowany. Oczekuje na decyzję o realizacji.*
