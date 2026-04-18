# 🔄 Bidirectional Sync: OpenBrain ↔ Obsidian

## Przegląd

**Bidirectional Sync** to najważniejsza funkcja OpenBrain v2.1 - umożliwia dwukierunkową synchronizację między OpenBrain a Obsidian.

### Co to zmienia?

| Przed (Export) | Po (Bidirectional Sync) |
|---------------|------------------------|
| OpenBrain → Obsidian (tylko eksport) | OpenBrain ↔ Obsidian (w obie strony) |
| Zmiany w Obsidian nie są widoczne w OpenBrain | Zmiany w obu systemach są synchronizowane |
| Konflikty ignorowane | Konflikty automatycznie rozwiązywane |
| Brak historii zmian | Pełne śledzenie stanu sync |

---

## 🎯 Kluczowe Funkcje

### 1. Detekcja Zmian
```python
# Automatycznie wykrywa:
- Nowe notatki w Obsidian → Import do OpenBrain
- Nowe memorie w OpenBrain → Eksport do Obsidian
- Zmodyfikowane notatki w obu systemach
- Usunięte elementy
```

### 2. Rozwiązywanie Konfliktów

Trzy strategie dostępne:

| Strategia | Opis | Kiedy używać |
|-----------|------|--------------|
| `last_write_wins` | Wygrywa ostatnia zmiana (timestamp) | Gdy czas jest ważniejszy niż źródło |
| `domain_based` | Corporate=OpenBrain, Personal=Obsidian | **Rekomendowane** - domyślne |
| `manual_review` | Oznacza do ręcznego rozwiązania | Gdy każdy konflikt jest krytyczny |

### 3. Śledzenie Stanu
- Przechowywanie hashy treści dla szybkiego porównania
- Timestampy ostatniego sync
- Historia zmian w `.openbrain/obsidian_sync_state.json`

---

## 🚀 Jak Używać

### MCP Tools

#### `brain_obsidian_bidirectional_sync`

```python
# Synchronizacja z domyślną strategią (domain_based)
result = await brain_obsidian_bidirectional_sync(
    vault="Memory",
    strategy="domain_based",
    dry_run=False,
)

# Result:
# {
#     "started_at": "2026-04-03T21:30:00",
#     "completed_at": "2026-04-03T21:30:05",
#     "vault": "Memory",
#     "strategy": "domain_based",
#     "changes_detected": 15,
#     "changes_applied": 14,
#     "conflicts": 1,
#     "dry_run": False,
#     "errors": [],
#     "changes": [
#         {
#             "memory_id": "mem_abc123",
#             "obsidian_path": "Projects/OpenBrain/Architecture.md",
#             "change_type": "updated",
#             "source": "obsidian",  # Zmiana z Obsidian
#             "conflict": False,
#         },
#         {
#             "memory_id": "mem_def456",
#             "obsidian_path": "Decisions/Auth0.md",
#             "change_type": "updated",
#             "source": "both",  # Konflikt!
#             "conflict": True,
#             "resolution": "openbrain",  # OpenBrain wygrał (domain_based)
#         }
#     ]
# }
```

#### `brain_obsidian_sync_status`

```python
# Sprawdź status synchronizacji
status = await brain_obsidian_sync_status()

# Result:
# {
#     "total_tracked": 42,
#     "never_synced": 3,
#     "synced_recently": 38,
#     "storage_path": ".openbrain/obsidian_sync_state.json"
# }
```

#### `brain_obsidian_update_note`

```python
# Aktualizuj notatkę (append lub replace)
result = await brain_obsidian_update_note(
    vault="Memory",
    path="Projects/OpenBrain/Architecture.md",
    content="\n\n## Update\nNowa sekcja dodana przez OpenBrain",
    append=True,  # Dodaj na końcu
    tags=["updated", "openbrain"],
)
```

---

### REST API

#### POST /api/v1/obsidian/bidirectional-sync

```bash
# Synchronizacja
curl -X POST http://localhost:7010/api/v1/obsidian/bidirectional-sync \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "vault": "Memory",
    "strategy": "domain_based",
    "dry_run": false
  }'
```

#### GET /api/v1/obsidian/sync-status

```bash
# Sprawdź status
curl http://localhost:7010/api/v1/obsidian/sync-status \
  -H "Authorization: Bearer $TOKEN"
```

---

## ⚙️ Konfiguracja

### Strategie Konfliktów

#### Domain-Based (Rekomendowana)

```python
# Corporate domain = OpenBrain jest źródłem prawdy
# Personal domain = Obsidian jest źródłem prawdy
# Build domain = OpenBrain wygrywa (domyślnie)

await brain_obsidian_bidirectional_sync(
    strategy="domain_based"
)
```

**Logika:**
- Corporate memorie (decyzje, polityki) → OpenBrain wygrywa
- Personal notatki (pomysły, notatki) → Obsidian wygrywa
- Build projekty → OpenBrain wygrywa (domyślnie)

#### Last-Write-Wins

```python
# Porównuje timestampy, wygrywa nowsza zmiana
await brain_obsidian_bidirectional_sync(
    strategy="last_write_wins"
)
```

#### Manual Review

```python
# Oznacza konflikty do ręcznego rozwiązania
result = await brain_obsidian_bidirectional_sync(
    strategy="manual_review"
)

# Sprawdź które wymagają uwagi
conflicts = [c for c in result["changes"] if c["conflict"]]
```

---

## 📊 Architektura

### Komponenty

```
┌─────────────────────────────────────────────────────────────┐
│                    OpenBrain Unified                        │
├─────────────────────────────────────────────────────────────┤
│  BidirectionalSyncEngine                                    │
│  ├── detect_changes()      → Porównuje stany               │
│  ├── resolve_conflict()    → Wybiera zwycięzcę             │
│  └── apply_sync()          → Aplikuje zmiany               │
│                                                             │
│  ObsidianChangeTracker                                      │
│  ├── _state: Dict[str, SyncState]                          │
│  ├── load_state()          → Z dysku                       │
│  └── save_state()          → Na dysk                       │
└─────────────────────────────────────────────────────────────┘
                            ↕
                    ObsidianCliAdapter
                            ↕
┌─────────────────────────────────────────────────────────────┐
│                       Obsidian Vault                        │
│                     (Markdown files)                        │
└─────────────────────────────────────────────────────────────┘
```

### Przepływ Synchronizacji

```
1. DETECT
   ├── Pobierz wszystkie memorie z OpenBrain (z obsidian_ref)
   ├── Pobierz wszystkie pliki .md z Obsidian
   ├── Porównaj z ostatnim znanym stanem (tracker)
   └── Wygeneruj listę zmian (SyncChange[])

2. RESOLVE
   ├── Dla każdej zmiany:
   │   ├── Jeśli brak konfliktu → kontynuuj
   │   └── Jeśli konflikt → zastosuj strategię
   └── Oznacz do rozwiązania manualnego (opcjonalnie)

3. APPLY
   ├── Zmiany z OpenBrain → Eksport do Obsidian
   ├── Zmiany z Obsidian → Import do OpenBrain
   ├── Aktualizuj tracker stanem po sync
   └── Zapisz na dysk

4. REPORT
   └── Zwróć SyncResult ze statystykami
```

---

## 💡 Przykłady Użycia

### Automatyczny Sync Co Godzinę

```python
# scheduler.py
import asyncio
from datetime import datetime

async def hourly_sync():
    while True:
        print(f"[{datetime.now()}] Starting scheduled sync...")
        
        result = await brain_obsidian_bidirectional_sync(
            vault="Memory",
            strategy="domain_based",
        )
        
        print(f"  Changes: {result['changes_applied']}")
        print(f"  Conflicts: {result['conflicts']}")
        
        # Czekaj godzinę
        await asyncio.sleep(3600)

# Uruchom
asyncio.run(hourly_sync())
```

### Sync Przed Spotkaniem

```python
# Przed weekly review - zsynchronizuj wszystko
result = await brain_obsidian_bidirectional_sync(
    vault="Memory",
    strategy="domain_based",
)

print(f"Synced {result['changes_applied']} items")

# Teraz wszystkie decyzje są aktualne w Obsidian
```

### Dry Run (Symulacja)

```python
# Sprawdź co by się zmieniło bez aplikowania zmian
result = await brain_obsidian_bidirectional_sync(
    vault="Memory",
    dry_run=True,  # Tylko detekcja!
)

print("Changes that would be applied:")
for change in result["changes"]:
    print(f"  - {change['obsidian_path']}: {change['change_type']}")

# Jeśli OK, wykonaj prawdziwy sync
if result["conflicts"] == 0:
    await brain_obsidian_bidirectional_sync(dry_run=False)
```

---

## 🔒 Bezpieczeństwo

### Backup Przed Sync

```python
# Funkcja delete_note zawsze backupuje do .trash/
await adapter.delete_note(
    vault="Memory",
    path="Old/Note.md",
    backup=True,  # Przenosi do .trash/ zamiast usuwać
)
```

### Walidacja Ścieżek

```python
# Wszystkie ścieżki są walidowane:
_validate_vault_path(vault, path)
# - Brak ../ (path traversal)
# - Ścieżka w obrębie vault
```

### Autoryzacja

```python
# Wszystkie endpointy sync wymagają admina
_require_admin(_user)
```

---

## 🐛 Troubleshooting

### "Conflict detected but not resolved"

**Przyczyna:** Używasz `strategy="manual_review"` i są konflikty.

**Rozwiązanie:**
```python
# Zobacz konflikty
result = await brain_obsidian_bidirectional_sync(strategy="manual_review")
for change in result["changes"]:
    if change["conflict"]:
        print(f"Manual review needed: {change['obsidian_path']}")
```

### "Vault path not accessible"

**Przyczyna:** Vault nie jest zsynchronizowany (iCloud/OneDrive).

**Rozwiązanie:**
```bash
# Sprawdź czy ścieżka istnieje
ls -la "/Users/gniewkob/Library/Mobile Documents/iCloud~md~obsidian/Documents"

# Jeśli nie - włącz synchronizację w Obsidian
```

### "Note not found after write"

**Przyczyna:** iCloud nie zsynchronizował pliku.

**Rozwiązanie:**
```python
# Dodaj opóźnienie lub sprawdź ponownie
import asyncio
await asyncio.sleep(1)  # Poczekaj na iCloud
```

---

## 📈 Statystyki

```python
status = await brain_obsidian_sync_status()

print(f"Total tracked: {status['total_tracked']}")
print(f"Never synced: {status['never_synced']}")
print(f"Synced this week: {status['synced_recently']}")
```

---

## 🔮 Przyszłe Rozszerzenia

- **Auto-sync on change** - WebSocket/TCP do natychmiastowej synchronizacji
- **Selective sync** - Tylko wybrane foldery/domeny
- **Sync rules** - Warunkowe sync (np. tylko gdy tag "sync")
- **Conflict UI** - Interfejs graficzny do rozwiązywania konfliktów

---

## Podsumowanie

**Bidirectional Sync** zamienia OpenBrain i Obsidian w **zintegrowany ekosystem**:

1. ✅ Pracuj tam gdzie wolisz (Obsidian dla edycji, OpenBrain dla AI)
2. ✅ Automatyczna synchronizacja zmian
3. ✅ Inteligentne rozwiązywanie konfliktów
4. ✅ Pełna historia i śledzenie stanu

To jest **game-changer** dla workflow wiedzy!
