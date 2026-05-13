# PLAN POPRAWY TECHNICAL DEBT - Q2 2026

**Data**: 2026-04-04  
**Aktualizacja**: 2026-04-20  
**Czas realizacji**: 6-8 tygodni  
**Status**: W toku

## Postęp (stan 2026-04-20)

| # | Zadanie | Status |
|---|---|---|
| — | 100% pokrycie testów (1403 testów) | ✅ DONE |
| — | `aiofiles` jako oficjalna zależność projektu | ✅ DONE |
| — | Refaktoryzacja `detect_changes()` | 🔄 PARTIAL (C901 clean, dalsza dekompozycja opcjonalna) |
| — | Refaktoryzacja `run_maintenance()` | ✅ DONE |
| 1.1 | Naprawa E501 long lines | ✅ DONE |
| 1.2 | Ruff format enforcement w CI | ✅ DONE |

---

---

## PRIORYTETY I ETAPY

### FAZA 1: Code Style & Consistency (Tydzień 1-2)

#### 1.1 Naprawa E501 - Za długie linie
**Cel**: Wszystkie linie <88 znaków (standard Ruff)

**Status**: ✅ DONE (2026-04-20)  
`ruff check src/ --select E501` przechodzi bez błędów.

**Kroki**:
```bash
# Walidacja
cd unified
ruff check src/ --select=E501
```

---

#### 1.2 Format enforcement (Ruff)
**Status**: ✅ DONE

`ruff format --check` jest już uruchamiany w CI (`ci.yml`, `ci-enhanced.yml`).

Black pozostaje opcjonalny i nie jest wymagany do jakości gate.

---

### FAZA 2: Funkcje o wysokiej złożoności (Tydzień 3-4)

#### 2.1 `detect_changes()` — status po refaktorze częściowym
**Plik**: `src/obsidian_sync.py`

**Status**: 🔄 PARTIAL  
- Quality gate złożoności (`ruff --select C901`) przechodzi.
- Funkcja została odchudzona przez ekstrakcję części logiki do helperów.
- Dalsza dekompozycja jest możliwa, ale nie jest blockerem release.

---

#### 2.2 `run_maintenance()` — rozbicie wykonane
**Plik**: `src/memory_writes.py`

**Status**: ✅ DONE  
Implementacja jest rozbita na mniejsze kroki:
- `run_maintenance()`
- `_run_maintenance_inner()`
- `_process_duplicates()`
- `_normalize_owners()`
- `_fix_superseded_links()`

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

---

## BACKLOG OTWARTY — 2026-05-13 → ✅ ZAMKNIĘTY 2026-05-13

Wszystkie 11 pozycji zrealizowane w pojedynczej sesji (commity `5ae17fa`..`529f4e2`).
Plan wdrożenia: [docs/architecture/superpowers/plans/2026-05-13-q2-backlog-execution.md](superpowers/plans/2026-05-13-q2-backlog-execution.md).
Wynik: CI 3/3 zielone, 1567 testów przechodzi.

Poniżej zachowany dla audytu — wszystkie checkboxy mentalnie ✓.

---

Pozycje wynikłe z review obsidian-sync + zmian infrastrukturalnych (commity `5ae17fa`..`7cbb1c7`). Posortowane wg pilności.

### P1 — czas-presja
- [ ] **Bump akcji GitHub na Node 24** w `.github/workflows/`. Aktualnie `actions/checkout@v4`, `actions/setup-python@v5`, `astral-sh/setup-uv@v4` biegają na Node.js 20 (deprecated). Force-flip na Node 24 od **2026-06-02**. Po tej dacie CI może zacząć się dziwnie zachowywać.
  - Action items: `checkout@v4` → `@v5`, `setup-python@v5` → `@v6`, `setup-uv@v4` → `@v6`
  - Walidacja: jeden PR, obejrzeć logi 3 workflowów

- [ ] **Migracja named volumes → bind mounts dla istniejącej bazy** (commit `5ae17fa` dodał definicję `./data/postgres`, ale stary wolumen `openbrain_openbrain_postgres_data` wciąż trzyma dane). Procedura w [MIGRATION.md](../../MIGRATION.md) — ok. 5 min downtime'u. Bez tego po pierwszym `docker compose down/up` aplikacja wystartuje z pustą bazą i będzie trzeba ręcznie restore'ować z backupu.

### P2 — architektura / techdebt
- [ ] **Backend: zwracaj `error.code` w odpowiedziach `/write_many`** zamiast wymagać string-matchu po `error.message` w gateway. Aktualnie gateway klasyfikuje błędy heurystycznie:
  ```python
  _OBSIDIAN_OWNER_MARKER = "owner is required for corporate domain"
  _OBSIDIAN_EMBED_MARKER = "/api/embed"
  _OBSIDIAN_DLP_BLOCK_MARKERS = ("secret_detected", "plaintext secret detected")
  ```
  Refactor backend: strukturalny `{error: {code: "owner_required_corporate", message: "..."}}`. Gateway czyta tylko `code`. Zysk: jeden refactor po stronie backendu nie wywala remediation w gateway.

- [ ] **Cleanup ~110 errors w `ruff check unified/`** — pre-existing, większość to F401 (unused imports) i drobne style. Jeden większy pass na całe `unified/`, później enforce w CI.
  - Walidacja: `cd unified && ../.venv/bin/ruff check` → All checks passed

### P3 — kosmetyka / testy
- [ ] **Test dla concurrent chunks w `brain_obsidian_sync`** — nowa logika z `MAX_OBSIDIAN_WRITE_CONCURRENCY > 1` (semaphore + `asyncio.gather` na chunks) nie ma dedykowanego testu. Dziś tylko ścieżka sekwencyjna jest pokryta.

- [ ] **Test dla exp backoff + jitter w `post_write_many`** — aktualnie sprawdzamy tylko że 429 retry działa, nie że delay rośnie wykładniczo ani że jitter jest aplikowany. Można mockować `asyncio.sleep` i `random.uniform`.

- [ ] **Telemetria/counter na truncation w `_clip_text`** — dziś tylko `log.warning`. Warto dorzucić Prometheus/statsd counter, bo ciche truncation produkcyjne łatwo przeoczyć w logach.

- [ ] **Sprzeczność w `~/claude-config/CLAUDE.md`** vs faktyczna intencja "OpenBrain always-on" — zaktualizowane lokalnie (2026-05-13), ale jeśli notatka pojawi się gdzieś w `docs/` repo, też trzeba uspójnić.

- [ ] **Grafana provisioning Prometheus datasource z openbrain repo** — kontener `shared-grafana` montuje tylko `monitoring/grafana/dashboards/openbrain/` z tego repo, **bez** folderu `provisioning/datasources/`. W rezultacie nasz plik `monitoring/grafana/provisioning/datasources/prometheus.yml` (deklarujący UID `openbrain-prometheus`) leży w repo jako dead-code, a runtime używa UID `shared-prometheus` z marketplace repo `~/Repos/priv/monitoring/`. Komit `5e7b804` przepisał wszystkie dashboardy na `shared-prometheus` jako workaround. Decyzja na później: (a) podmontować nasz `provisioning/` do kontenera w shared compose, albo (b) usunąć dead-code i przyjąć `shared-prometheus` jako konwencję per repo.

### P4 — opcjonalne
- [ ] Wskazówki w skryptach `unified/scripts/*.py` co do uruchamiania (README albo docstring z przykładami) — szczególnie `cleanup_frontmatter_content.py` (dry-run vs --apply) i `generate_openbrain_obsidian_dashboard.py` (wymagane env vary).

- [ ] `pyproject.toml` w `unified/mcp-gateway/` nie pinuje `authlib`/`python-multipart` jako bezpośrednich deps (tylko transitive z FastAPI). Po następnym Dependabot bumpie te wersje znów mogą się odsynchronizować. Rozważenie: explicit pin, albo zaufanie do FastAPI constraint.

---
