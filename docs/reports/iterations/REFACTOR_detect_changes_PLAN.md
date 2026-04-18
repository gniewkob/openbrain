# Plan Refaktoryzacji detect_changes()

**Obecny stan**:
- 132 linie kodu
- Złożoność cyklomatyczna: 21
- Plik: `src/obsidian_sync.py` (linie 264-396)

**Cel**:
- Rozbić na funkcje <50 linii
- Złożoność <15
- Lepsza testowalność

---

## Obecna Struktura

```python
async def detect_changes(self, session, adapter, vault, since) -> list[SyncChange]:
    # 1. Pobranie danych z OpenBrain (list_memories)
    # 2. Pobranie plików z Obsidian (list_files)
    # 3. Budowa map lookup
    # 4. Iteracja po tracker states (główna logika)
    #    - Sprawdzenie czy memory istnieje
    #    - Sprawdzenie czy plik istnieje
    #    - Porównanie hashy
    #    - Detekcja konfliktów
    # 5. Detekcja nowych plików w Obsidian
    # 6. Zwrócenie listy zmian
```

---

## Plan Refaktoryzacji

### Krok 1: Wydzielenie funkcji pomocniczych

```python
async def _get_openbrain_memories(session, vault: str) -> dict[str, MemoryOut]:
    """Pobierz wszystkie memory z obsidian_ref dla danego vault."""
    from .memory_reads import list_memories
    all_memories = await list_memories(session, {}, limit=1000)
    return {m.obsidian_ref: m for m in all_memories if m.obsidian_ref}

async def _get_obsidian_files(adapter, vault: str) -> set[str]:
    """Pobierz listę plików z Obsidian vault."""
    try:
        files = await adapter.list_files(vault, limit=1000)
        return set(files)
    except Exception as e:
        log.warning("obsidian_list_files_failed", error=str(e), vault=vault)
        return set()

def _detect_memory_change(
    state: SyncState,
    memory: MemoryOut | None,
    obsidian_exists: bool,
) -> SyncChange | None:
    """Wykryj zmianę dla pojedynczego trackowanego elementu."""
    # Logika porównania
    ...

def _detect_new_obsidian_files(
    obsidian_files: set[str],
    tracked_paths: set[str],
) -> list[SyncChange]:
    """Znajdź nowe pliki w Obsidian których nie trackujemy."""
    ...
```

### Krok 2: Uproszczona główna funkcja

```python
async def detect_changes(
    self,
    session: "AsyncSession",
    adapter: "ObsidianCliAdapter",
    vault: str,
    since: Optional[datetime] = None,
) -> list[SyncChange]:
    """Detect changes between OpenBrain and Obsidian."""
    # Pobierz dane
    memory_map = await _get_openbrain_memories(session, vault)
    obsidian_files = await _get_obsidian_files(adapter, vault)
    tracked_states = [s for s in self.tracker.get_all_states() if s.vault == vault]
    
    changes: list[SyncChange] = []
    tracked_paths = set()
    
    # Sprawdź trackowane elementy
    for state in tracked_states:
        tracked_paths.add(state.obsidian_path)
        memory = memory_map.get(state.obsidian_path)
        obsidian_exists = state.obsidian_path in obsidian_files
        
        change = _detect_memory_change(state, memory, obsidian_exists)
        if change:
            changes.append(change)
    
    # Znajdź nowe pliki
    new_files = _detect_new_obsidian_files(obsidian_files, tracked_paths)
    changes.extend(new_files)
    
    return changes
```

---

## Szacunkowy Czas Implementacji

- Krok 1: 4h (wydzielenie funkcji)
- Krok 2: 2h (uproszczenie głównej funkcji)
- Testy: 4h (testy jednostkowe dla nowych funkcji)
- **Razem: 10h**

---

## Zalecenie

Ze względu na złożoność i ryzyko (krytyczna funkcjonalność):

1. **Najpierw** napisać testy integracyjne dla obecnej funkcji
2. **Potem** wykonać refaktoryzację
3. **Zweryfikować** że testy nadal przechodzą

Alternatywnie: odłożyć na osobny sprint gdy będzie dostępny czas 10h.
