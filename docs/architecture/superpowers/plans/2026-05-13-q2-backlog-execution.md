# Q2 Backlog Execution Plan — 2026-05-13

> **STATUS: ✅ ZAMKNIĘTY 2026-05-13.** Wszystkie 11 zadań zrealizowane jednego dnia
> (commity `5ae17fa`..`fc7e1a3`). CI 3/3 zielone, 1567 testów przechodzi.
> Plan zachowany dla audytu — link `monitoring/grafana/provisioning/...` poniżej
> wskazuje na plik usunięty w S5.1 (intencjonalnie).
>
> Plan poniżej zostawiony jako "as authored" — checkboxy ` - [ ]` reprezentują
> intencję z 2026-05-13, nie aktualny stan.

**Goal:** Domknąć 12-pozycyjny backlog otwarty po review obsidian-sync ([roadmap.md "BACKLOG OTWARTY — 2026-05-13"](../../roadmap.md)).

**Strategia:** 6 sprintów, każdy zamknięty osobnym commitem lub spójną serią. Sprinty 0-2 to ~6h roboczych w jeden tydzień. Sprinty 3-5 to refactor/cleanup, można rozsmarować na 2-3 tygodnie.

**Total effort:** ~12-15h pracy + jednorazowo ~30 min DB downtime.

---

## Summary Table

| # | Sprint | Item | Effort | Risk | Reversible | Deadline |
|---|---|---|---|---|---|---|
| 1 | S0 | Bump GH actions na Node 24 | 1h | Low | Yes | **2026-06-02** |
| 2 | S0 | Reconcile CLAUDE.md ngrok note | 10min | None | Yes | — |
| 3 | S0 | Decyzja gateway pyproject pinning | 15min | Low | Yes | — |
| 4 | S1 | DB volume migration (named → bind) | 30min + 5min downtime | Med | No (data) | po pierwszym `docker compose down` |
| 5 | S2 | Test concurrent chunks | 1.5h | Low | Yes | — |
| 6 | S2 | Test exp backoff + jitter | 1h | Low | Yes | — |
| 7 | S2 | Truncation counter (Prometheus) | 1h | Low | Yes | — |
| 8 | S3 | Ruff cleanup unified/ (~110 errors) | 2-3h | Low | Yes | — |
| 9 | S4 | Backend `error.code` refactor | 4-6h | Med | Yes | — |
| 10 | S5 | Grafana provisioning decision | 30min + impl | Low | Yes | — |
| 11 | S5 | README usage w `unified/scripts/*` | 1h | None | Yes | — |

---

## Sprint 0 — Quick wins (~1.5h)

Trzy małe, niezależne pozycje. Każda osobnym commitem.

### Task 1: Bump GitHub actions na Node 24

**Why now:** GitHub force-flipuje runner Node 20 → 24 od **2026-06-02**. Po tej dacie CI zacznie wyrzucać deprecation warnings przekształcone w errors.

**Files:**
- `.github/workflows/ci.yml`
- `.github/workflows/ci-enhanced.yml`
- `.github/workflows/unified-smoke.yml`
- `.github/workflows/*.yml` (sprawdź wszystkie)

**Bumpy:**
- `actions/checkout@v4` → `@v5`
- `actions/setup-python@v5` → `@v6`
- `astral-sh/setup-uv@v4` → `@v6`

- [ ] **Step 1.1:** `grep -rn "@v4\|@v5" .github/workflows/` — lista referencji
- [ ] **Step 1.2:** Sprawdź release notes każdej akcji pod kątem breaking changes (krótko, max 5 min)
- [ ] **Step 1.3:** Pojedynczy commit z bumpem we wszystkich workflows
- [ ] **Step 1.4:** Push i obserwuj 3 workflowy. Walidacja: 0 deprecation warnings w logach

**Rollback:** `git revert <commit>` jeśli któryś workflow padnie. Zero ryzyka dla kodu.

---

### Task 2: Reconcile CLAUDE.md ngrok note

**Why:** Globalny `~/claude-config/CLAUDE.md` był zaktualizowany lokalnie (2026-05-13) na "always-on by design". Trzeba zweryfikować że żaden plik w **repo** nie ma sprzecznej notatki, bo ona trafi w przyszłe sesje agentów.

- [ ] **Step 2.1:** `grep -rn "ngrok" docs/ CLAUDE.md README.md 2>/dev/null | grep -iE "keep stopped|disable|don.?t.*start|exposes.*without"`
- [ ] **Step 2.2:** Każde trafienie zaktualizować na "always-on; auth via INTERNAL_API_KEY/OAuth"
- [ ] **Step 2.3:** Commit jeśli były zmiany; jeśli nie — zaznacz w roadmap że nic nie trzeba

**Walidacja:** kolejny `grep` zwraca tylko aktualne notatki.

---

### Task 3: Decyzja gateway pyproject pinning

**Why:** `unified/mcp-gateway/pyproject.toml` nie pinuje `authlib` ani `python-multipart` — Dependabot może je znów rozjechać.

**Decision matrix:**
- **(a) Explicit pin** w gateway pyproject: stabilność, ale duplikacja constraint z `unified/pyproject.toml`
- **(b) Trust FastAPI constraint**: mniej kodu, ryzyko że transitive bump cofnie wersję

Rekomendacja: **(a)** dla `python-multipart` (high-sev DoS), **(b)** dla `authlib` (medium).

- [ ] **Step 3.1:** Dodaj `"python-multipart>=0.0.27"` do `unified/mcp-gateway/pyproject.toml [project.dependencies]`
- [ ] **Step 3.2:** `cd unified/mcp-gateway && uv lock` — sanity check
- [ ] **Step 3.3:** Commit + push

**Walidacja:** `grep "python-multipart" unified/mcp-gateway/uv.lock` zwraca ≥0.0.27.

---

## Sprint 1 — DB volume migration (~30min + 5min downtime)

Wymaga zaplanowanego okna serwisowego. Procedura już w [MIGRATION.md](../../../MIGRATION.md).

### Task 4: Migracja named volume → bind mount

**Why:** Po pierwszym `docker compose down/up` po pull 5ae17fa stack wystartuje z pustą bazą — bind mount `./data/postgres` jest pusty, named volume `openbrain_openbrain_postgres_data` osierocony.

**Pre-requisites:**
- Stack uruchomiony (PG running)
- Wolne ~2 GB na lokalnym dysku na backup
- Brak aktywnych pisarzy do bazy (CI/cron zatrzymane)

- [ ] **Step 4.1:** Anonsuj okno serwisowe (jeśli ktoś inny używa). Zatrzymaj cron-y: `launchctl unload ~/Library/LaunchAgents/com.openbrain.postgres-backup.plist`
- [ ] **Step 4.2:** Backup z named volume: `docker exec openbrain-unified-db pg_dump -U postgres -d openbrain_unified --no-owner --no-acl --format=custom --blobs > backups/pre_migration_$(date +%Y%m%d_%H%M%S).dump`
- [ ] **Step 4.3:** `docker compose -f docker-compose.unified.yml down`
- [ ] **Step 4.4:** `mkdir -p data/postgres data/redis`
- [ ] **Step 4.5:** `docker compose -f docker-compose.unified.yml up -d db` — startuje na PUSTYM bind mount
- [ ] **Step 4.6:** Czekaj na healthcheck (10s), wykonaj restore: `docker exec -i openbrain-unified-db pg_restore -U postgres -d openbrain_unified --no-owner --no-acl --verbose < backups/pre_migration_*.dump`
- [ ] **Step 4.7:** Sanity: `docker exec openbrain-unified-db psql -U postgres -d openbrain_unified -c "SELECT count(*) FROM memories;"` — powinno być ~1352
- [ ] **Step 4.8:** Pełny stack: `docker compose -f docker-compose.unified.yml up -d`
- [ ] **Step 4.9:** Sanity HTTP: `curl http://127.0.0.1:7010/readyz`
- [ ] **Step 4.10:** Wznów cron: `launchctl load ~/Library/LaunchAgents/com.openbrain.postgres-backup.plist`
- [ ] **Step 4.11:** (Po 24h sanity) usuń stary wolumen: `docker volume rm openbrain_openbrain_postgres_data openbrain_openbrain_redis_data`

**Rollback (jeśli step 4.6 lub 4.7 padnie):**
- `docker compose down` → przywróć named volume w compose (cofnij 5ae17fa lokalnie) → `up`. Stary volume nadal istnieje. Dane bezpieczne.

**Walidacja:** count(memories) == przed migracją. Brak błędów w `docker logs openbrain-unified-server --tail 50`.

---

## Sprint 2 — Testy + observability (~3.5h)

Pakiet testów + jeden metric. Każda pozycja w osobnym commicie.

### Task 5: Test concurrent chunks w `brain_obsidian_sync`

**Why:** Po refactorze w 5ae17fa `process_chunk` jest wywoływane przez semaphore + `asyncio.gather` gdy `MAX_OBSIDIAN_WRITE_CONCURRENCY > 1`. Aktualnie pokryta tylko ścieżka sekwencyjna.

**File:** `unified/mcp-gateway/tests/test_obsidian_tools.py`

- [ ] **Step 5.1:** Test scenariusz: 3 chunks (każdy 1 record), `MAX_OBSIDIAN_WRITE_CONCURRENCY=2`. Mock `_post_write_many` zwraca 200 z opóźnieniem 0.1s żeby wymusić nakładkę.
- [ ] **Step 5.2:** Asercje:
  - Łączna liczba `client.post` calls = 3
  - Wszystkie 3 records zaagregowane w `aggregated_results`
  - Czas wykonania < 0.25s (gdyby było sekwencyjne, byłoby ≥0.3s)
- [ ] **Step 5.3:** `monkeypatch.setattr(gateway, "MAX_OBSIDIAN_WRITE_CONCURRENCY", 2)` + `MAX_BULK_ITEMS=1`

**Walidacja:** `pytest unified/mcp-gateway/tests/test_obsidian_tools.py::test_brain_obsidian_sync_parallel_chunks -v` zielone.

---

### Task 6: Test exp backoff + jitter w `post_write_many`

**Why:** Aktualnie sprawdzamy tylko że 429 → retry działa, nie że delay rośnie wykładniczo z jitterem.

**File:** `unified/mcp-gateway/tests/test_obsidian_tools.py`

- [ ] **Step 6.1:** Mock `asyncio.sleep` (capture wszystkie wywołania) + `random.uniform` (zwracaj 0 → no jitter dla deterministyki).
- [ ] **Step 6.2:** Wymuś 4× 429, potem 200. Walidacja sleep durations:
  - `[0.25, 0.5, 1.0, 2.0]` (exp z base 0.25, mnożnik 2^attempt)
- [ ] **Step 6.3:** Drugi test z `random.uniform` zwracającym ±0.25 — sprawdź że jitter jest aplikowany (sleep ∈ [base*0.75, base*1.25])

**Walidacja:** 2 nowe testy zielone.

---

### Task 7: Truncation counter dla `_clip_text`

**Why:** Dziś `log.warning` przy truncation. Counter pozwoli na alert "więcej niż X truncations/h".

**Files:**
- `unified/src/common/obsidian_adapter.py`
- `unified/src/telemetry_counters.py` (lub gdziekolwiek są inne countery)
- (Opcjonalnie) `monitoring/grafana/dashboards/openbrain/openbrain-overview.json` — panel

**Implementacja:**
- [ ] **Step 7.1:** Znajdź jak istniejące countery są zdefiniowane: `grep -rn "prometheus_client\|Counter\b" unified/src/`
- [ ] **Step 7.2:** Dodaj `obsidian_clip_truncation_total = Counter("obsidian_clip_truncation_total", "Records where a field was clipped to fit length limits", ["field"])` — labelled by field name
- [ ] **Step 7.3:** W `_clip_text`, gdy `len(value) > limit`, wywołaj `.labels(field=field or "unknown").inc()`
- [ ] **Step 7.4:** Test: wywołaj `_clip_text("x" * 9999, 100, field="content")` i sprawdź że counter wzrósł (z `prometheus_client.REGISTRY.get_sample_value(...)`)
- [ ] **Step 7.5:** Bonus — panel w Grafanie: timeseries `rate(obsidian_clip_truncation_total[5m])` by field

**Walidacja:** `curl http://127.0.0.1:7010/metrics | grep obsidian_clip_truncation` zwraca metrykę.

---

## Sprint 3 — Ruff cleanup (~2-3h)

### Task 8: Cleanup ~110 ruff errors w `unified/`

**Why:** Pre-existing, większość to F401 i drobne style. CI ich nie enforce'uje pełnie, ale spowalnia review (`ruff check` na PR z tym samym repo zawsze pokazuje >100 rzeczy).

**Strategy:** Zbierz wszystkie, podziel na auto-fixable vs manual, commituj w 2 partiach.

- [ ] **Step 8.1:** Inwentaryzacja: `cd unified && ../.venv/bin/ruff check 2>&1 | tee /tmp/ruff-errors.txt`
- [ ] **Step 8.2:** Auto-fix safe rules: `ruff check --fix unified/`. Pewnie zamknie 50-80%.
- [ ] **Step 8.3:** `git diff` — przejrzyj zmiany, upewnij się że nic semantycznego nie zostało zepsute (unused imports → OK; unused variables → trzeba sprawdzić czy nie są to slot dla side-effect)
- [ ] **Step 8.4:** Commit "chore: ruff auto-fix" + `pytest unified/tests/` żeby potwierdzić że nic nie spadło
- [ ] **Step 8.5:** Pozostałe (manual): naprawiaj per-błąd, grupuj komity logicznie (np. wszystkie B904 razem)
- [ ] **Step 8.6:** Włącz w CI: w `.github/workflows/ci.yml` zmień `ruff check` z soft → fail-on-error dla `unified/`

**Walidacja:** `ruff check unified/` → All checks passed. Tests dalej zielone.

**Rollback:** Każdy partial commit można `git revert` osobno.

---

## Sprint 4 — Backend `error.code` (~4-6h)

### Task 9: Strukturalne kody błędów w `/write_many`

**Why:** Gateway klasyfikuje błędy po fragmentach `error.message` ([main.py:212](../../../unified/mcp-gateway/src/main.py:212)). Refactor backendu na strukturalne kody pozwoli usunąć string-match.

**Touched files:**
- `unified/src/api/v1/memory.py` — endpoint `/write_many`
- `unified/src/use_cases/memory.py` — handler
- `unified/src/schemas.py` — `MemoryWriteResultItem` (lub jak się tam nazywa) z dodanym `error_code` polem
- `unified/mcp-gateway/src/main.py` — `_obsidian_classify_error` używa `error_code` jeśli dostępny, fallback na string-match (transition period)
- Testy obu stron

**Etapy (osobne commity):**
- [ ] **Step 9.1:** **Backend — dodaj `error_code` do response schema** (osobny commit). Dla każdej znanej ścieżki error mappingu (`owner_required_corporate`, `embed_400`, `secret_detected`, `validation_error`) wystaw kod. Stare `error` (message) zostaje dla kompatybilności.
- [ ] **Step 9.2:** **Backend testy** sprawdzają że odpowiedź ma teraz `error_code` w przewidzianym formacie.
- [ ] **Step 9.3:** **Gateway — czytaj `error_code` jeśli jest, w przeciwnym razie fallback** na string-match (transition). Adapter:
  ```python
  def _classify_from_item(item: dict) -> str:
      code = item.get("error_code")
      if code:
          return code
      return _obsidian_classify_error(str(item.get("error", "")).lower())
  ```
- [ ] **Step 9.4:** **Gateway testy** — mock backendu zwraca `error_code` zamiast message; potwierdź że remediation działa.
- [ ] **Step 9.5:** Po deployu — monitoruj 1 tydzień. Jeśli zero fall-throughów do string-matcha → usuń string-match path w osobnym commicie.

**Walidacja:** Wszystkie testy gateway + backend zielone. W produkcji: brak nowych failed-write w summary.

**Rollback:** Gateway zachowuje fallback — backendowy revert nie psuje gatewaya.

---

## Sprint 5 — Polish (~1.5h)

### Task 10: Grafana provisioning decision

**Why:** [openbrain repo monitoring/grafana/provisioning/datasources/prometheus.yml](../../../monitoring/grafana/provisioning/datasources/prometheus.yml) jest dead code — kontener `shared-grafana` go nie montuje. Komit 5e7b804 obszedł problem dashboard-side.

**Options:**
- **(a) Zmontuj nasz `provisioning/` do kontenera** — wymaga modyfikacji shared compose w `~/Repos/priv/`. Ryzyko kolizji UID z mailai/salonbw provisioning.
- **(b) Usuń dead provisioning file** — przyjmij `shared-prometheus` jako konwencję per-repo. Mniej kodu, jeden punkt prawdy (shared marketplace).

**Rekomendacja: (b)** — workaround już działa, mniej operacyjnego complexity.

- [ ] **Step 10.1:** Usuń `monitoring/grafana/provisioning/datasources/prometheus.yml` i pusty folder.
- [ ] **Step 10.2:** Dodaj notkę do `docs/operations/monitoring.md` że dashboardy muszą używać `shared-prometheus` UID i czemu.
- [ ] **Step 10.3:** Commit "chore(monitoring): drop dead provisioning, standardize on shared-prometheus UID"

**Walidacja:** Dashboardy nadal działają (sanity Grafany).

---

### Task 11: README usage w `unified/scripts/*`

**Why:** 5 skryptów w `unified/scripts/` (`_config.py`, `cleanup_frontmatter_content.py`, `generate_openbrain_obsidian_dashboard.py`, `obsidian_inbox_cleanup.sh`, `weekly_maintenance_dry_run.sh`) — niejasne jak je odpalać i z jakim env.

- [ ] **Step 11.1:** Dorzuć `unified/scripts/README.md` (lub rozbuduj sekcję w `docs/operations/`)
- [ ] **Step 11.2:** Dla każdego skryptu opisz: cel, wymagane env vars, dry-run vs apply, schedule (cron/launchd jeśli relevant)
- [ ] **Step 11.3:** Dodaj sekcję "Maintenance scripts" do głównego `README.md` linkującą do tego

**Walidacja:** Manualny przegląd przez kolegę / wrócenie do skryptu po tygodniu.

---

## Harmonogram (sugerowany)

| Tydzień | Sprint | Wynik |
|---|---|---|
| W1 (do 2026-05-20) | S0 + S1 | Quick wins zamknięte, DB migracja zrobiona |
| W2 (2026-05-21 ~ 27) | S2 | Pakiet testów + truncation counter |
| W3 (2026-05-28 ~ 06-03) | S3 | Ruff cleanup |
| W4-5 (2026-06-04 ~ 17) | S4 | Backend error.code (większy refactor) |
| W6 (2026-06-18 ~ 24) | S5 | Polish |

**Twarde deadline'y:**
- Task 1 (GH actions): **2026-06-02** — musi być w W1-W3

---

## Walidacja całości

Po zamknięciu wszystkich 11 zadań:

- [ ] CI 3/3 zielone na master
- [ ] `ruff check unified/` → All checks passed
- [ ] `pytest unified/tests/ unified/mcp-gateway/tests/` → 0 failed
- [ ] Roadmap.md: backlog 2026-05-13 oznaczony jako ✅ DONE
- [ ] Dashboard Grafany: panel `obsidian_clip_truncation_total` widoczny
- [ ] Dependabot alerts: 0
- [ ] `docker volume ls` → brak `openbrain_openbrain_*_data`
- [ ] Brak deprecation warnings w CI logs

---

*Plan przygotowany 2026-05-13. Po zatwierdzeniu zacznij od Sprint 0.*
