# 🚀 Quick Start - Implementacja Planu 5/5

Ten dokument pomoże Ci rozpocząć implementację planu dokończenia systemu do poziomu 5/5.

---

## 📋 PRZED ROZPOCZĘCIEM

Upewnij się, że masz:
- [ ] Dostęp do repo i uprawnienia do push
- [ ] Skonfigurowane środowisko dev (Python 3.12, uv)
- [ ] Działającą bazę dev (PostgreSQL + Redis)
- [ ] Przeczytany pełny plan: `docs/COMPLETION_PLAN_5_5.md`

---

## 🎯 TYDZIEŃ 1: MYPY (Dni 1-3)

### Dzień 1: Setup i analiza

```bash
# 1. Upewnij się, że masz ostatnią wersję kodu
git pull origin main

# 2. Zainstaluj zależności
cd unified
uv sync --group dev

# 3. Uruchom mypy i zapisz wyniki
uv run mypy src/ --ignore-missing-imports > mypy_report.txt

# 4. Przeanalizuj błędy
cat mypy_report.txt | grep "error:" | wc -l  # Powinno być 53
```

### Dzień 1-2: Naprawa błędów (strategia)

**Priorytet plików (najwięcej błędów → najmniej):**

```bash
# Plik 1: memory_writes.py (11 błędów)
# Plik 2: mcp_transport.py (8 błędów)
# Plik 3: api/v1/memory.py (7 błędów)
# Plik 4: memory_reads.py (6 błędów)
# Plik 5: api/v1/obsidian.py (5 błędów)
# Plik 6: crud.py (5 błędów)
# Reszta: pozostałe (11 błędów)
```

**Workflow naprawy:**

```bash
# 1. Wybierz plik (np. memory_writes.py)

# 2. Uruchom mypy tylko dla tego pliku
uv run mypy src/memory_writes.py --ignore-missing-imports

# 3. Napraw błędy (jeden na raz!)
# - Dodaj brakujące typy zwracane
# - Obsłuż Optional[...] z if/return
# - Dodaj type hints dla argumentów

# 4. Uruchom testy dla tego pliku
uv run pytest tests/test_memory_writes.py -v

# 5. Commit
-git add src/memory_writes.py
-git commit -m "fix(types): resolve mypy errors in memory_writes.py"

# 6. Idź do następnego pliku
```

### Dzień 3: Weryfikacja

```bash
# Wszystkie błędy naprawione?
uv run mypy src/ --ignore-missing-imports
# Powinno zwrócić: Success: no issues found in 39 source files

# Wszystkie testy przechodzą?
uv run pytest tests/ -v --tb=short
```

---

## 🎯 TYDZIEŃ 1: BACKUP (Dni 6-7)

### Dzień 6: Skrypt backupu

```bash
# Skrypt jest już gotowy: scripts/backup_postgres.sh
# Sprawdź czy działa:

chmod +x scripts/backup_postgres.sh
./scripts/backup_postgres.sh --help

# Test na dev bazie
POSTGRES_HOST=localhost \
POSTGRES_USER=postgres \
POSTGRES_PASSWORD=your_password \
POSTGRES_DB=openbrain_unified \
./scripts/backup_postgres.sh --full

# Sprawdź czy backup został utworzony
ls -la backups/
```

### Dzień 7: Konfiguracja

```bash
# 1. Dodaj do crontab (codzienny backup o 2:00 AM)
crontab -e
# Dodaj linię:
0 2 * * * cd /path/to/openbrain && POSTGRES_PASSWORD=xxx ./scripts/backup_postgres.sh --full >> /var/log/openbrain-backup.log 2>&1

# 2. Skonfiguruj S3 (opcjonalnie)
export BACKUP_S3_BUCKET=your-backup-bucket
export BACKUP_S3_PREFIX=openbrain/backups

# 3. Test restore
./scripts/backup_postgres.sh --list
./scripts/backup_postgres.sh --restore openbrain_full_YYYYMMDD_HHMMSS.dump.gz
```

---

## 🎯 TYDZIEŃ 2: CI/CD (Dni 11-14)

### Dzień 11-12: Mypy w CI

```bash
# Plik już gotowy: .github/workflows/ci-enhanced.yml
# Wystarczy go aktywować:

git add .github/workflows/ci-enhanced.yml
git commit -m "ci: add enhanced CI pipeline with mypy, coverage, bandit"
git push

# Sprawdź czy działa w GitHub Actions
# https://github.com/your-org/openbrain/actions
```

### Dzień 13-14: Coverage

```bash
# 1. Dodaj pytest-cov do pyproject.toml
cd unified
cat >> pyproject.toml << 'EOF'

[dependency-groups]
dev = [
    "pytest>=9.0.2",
    "pytest-asyncio>=1.3.0",
    "pytest-cov>=4.0.0",
    "fastmcp>=2.0",
    "ruff>=0.15.9",
    "mypy>=1.20.0",
]
EOF

# 2. Zainstaluj
uv sync --group dev

# 3. Test coverage
uv run pytest tests/ --cov=src --cov-report=term-missing

# 4. Jeśli <80%, dodaj brakujące testy
#    Priorytet: api/v1/obsidian.py (9 endpointów bez testów)
```

---

## 🎯 TYDZIEŃ 2: PRE-COMMIT (Dzień 17-18)

```bash
# 1. Instalacja pre-commit
pip install pre-commit

# 2. Aktywacja hooków
pre-commit install

# 3. Test na wszystkich plikach (pierwszy raz)
pre-commit run --all-files

# 4. Commit konfiguracji
git add .pre-commit-config.yaml
git commit -m "chore: add pre-commit hooks for code quality"
```

---

## 🎯 TYDZIEŃ 3-4: WYDAJNOŚĆ (Dni 21-30)

### Redis Telemetry

```python
# Nowy plik: unified/src/telemetry_redis.py
# Implementacja w planie: docs/COMPLETION_PLAN_5_5.md

# Po implementacji, włącz przez env:
export TELEMETRY_BACKEND=redis
export REDIS_URL=redis://localhost:6379/0
```

### Connection Pool

```python
# Modyfikacja: unified/src/mcp_transport.py
# Dodaj lifecycle hooks w main.py:

@app.on_event("startup")
async def startup():
    await mcp_transport.startup()

@app.on_event("shutdown")
async def shutdown():
    await mcp_transport.shutdown()
```

---

## 🎯 TYDZIEŃ 5-6: REFAKTORYZACJA (Dni 31-38)

### Pydantic-settings

```python
# Nowy plik: unified/src/config_refactored.py
# Szczegóły w planie

# Migracja stopniowa:
# 1. Dodaj nową klasę config obok starej
# 2. Przepisz jeden moduł na nową config
# 3. Testuj
# 4. Powtarzaj dla kolejnych modułów
# 5. Usuń starą config
```

### Podział funkcji

```python
# PRZED:
def register_v1_routes(app: FastAPI) -> None:  # 96 linii
    ...

# PO:
def register_v1_routes(app: FastAPI) -> None:  # 15 linii
    _register_memory_routes(app)
    _register_obsidian_routes(app)
    _register_admin_routes(app)

def _register_memory_routes(app: FastAPI) -> None:  # 30 linii
    ...
```

---

## 📊 TRACKING PROGRESSU

Użyj tej tabeli do śledzenia postępów:

| # | Zadanie | Status | Committowane |
|---|---------|--------|--------------|
| 1 | memory_writes.py mypy | [ ] | [ ] |
| 2 | mcp_transport.py mypy | [ ] | [ ] |
| 3 | api/v1/memory.py mypy | [ ] | [ ] |
| 4 | Pozostałe mypy | [ ] | [ ] |
| 5 | Backup skrypt | [x] | [x] |
| 6 | DR dokumentacja | [ ] | [ ] |
| 7 | Mypy w CI | [x] | [ ] |
| 8 | Coverage >=80% | [ ] | [ ] |
| 9 | Bandit w CI | [x] | [ ] |
| 10 | Pre-commit | [x] | [ ] |
| 11 | Redis telemetry | [ ] | [ ] |
| 12 | Connection pool | [ ] | [ ] |
| 13 | Pydantic-settings | [ ] | [ ] |
| 14 | Refaktoryzacja funkcji | [ ] | [ ] |
| 15 | Testy obsidian.py | [ ] | [ ] |

---

## ✅ CHECKLIST KOŃCOWA

Przed ogłoszeniem "5/5":

- [ ] `mypy src/` - 0 błędów
- [ ] `pytest --cov=src --cov-fail-under=80`
- [ ] `ruff check src/` - 0 błędów
- [ ] `bandit -r src/ -ll` - 0 high severity
- [ ] `./scripts/backup_postgres.sh --full` działa
- [ ] DR drill przeprowadzony
- [ ] Wszystkie testy przechodzą
- [ ] CI zielone
- [ ] Pre-commit działa
- [ ] Code review przez 2 osoby
- [ ] Tag v2.1.0

---

## 🆘 POMOC

### Problemy z mypy?

```bash
# Najczęstsze problemy i rozwiązania:

# Problem: Optional[X] bez obsługi None
# Rozwiązanie:
result: Optional[Memory] = await get_memory()
if result is None:
    raise NotFoundError()
return result.content  # Teraz OK

# Problem: Brak return type
# Rozwiązanie:
async def funkcja() -> dict[str, Any]:  # Dodaj return type
    ...

# Problem: Missing type for variable
# Rozwiązanie:
data: dict[str, int] = {}  # Zamiast data = {}
```

### Testy nie przechodzą?

```bash
# Uruchom z verbose
uv run pytest tests/test_file.py -vvs --tb=long

# Sprawdź czy to nie problem z testami (mocki, fixtures)
uv run pytest tests/test_file.py --pdb  # debug
```

---

## 📚 DOKUMENTACJA

| Dokument | Zawartość |
|----------|-----------|
| `docs/COMPLETION_PLAN_5_5.md` | Pełny plan 8-tygodniowy |
| `docs/ROADMAP_VISUAL_5_5.md` | Wizualna mapa drogowa |
| `docs/QUICK_START_5_5.md` | Ten dokument |
| `docs/DISASTER_RECOVERY.md` | DR plan (do stworzenia) |
| `docs/OPERATIONS.md` | Runbook (do stworzenia) |

---

## 💡 TIPY

1. **Commituj często** - co najmniej raz dziennie
2. **Testuj lokalnie** - przed pushem
3. **Małe PRy** - jeden plik/zadanie = jeden PR
4. **Opisuj commity** - `fix(types): resolve mypy errors in X`
5. **Używaj branchy** - `feat/mypy-fixes`, `feat/backup-script`

---

Powodzenia! 🚀
