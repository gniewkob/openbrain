# OpenBrain MCP - API Keys i Konfiguracja

> **Data aktualizacji:** 2026-04-04 (aktualizacja: 2026-04-04)
> **Status:** Aktywne
> **ID w OpenBrain:** `875710e1-912c-4e0a-871e-09de565bdf92`

---

## Klucze API

> **Jeden klucz dla wszystkich transportów** — od 2026-04-04 `docker-compose.unified.yml`
> czyta klucz z `.env` przez `${INTERNAL_API_KEY}`. Klucz definiuje się tylko w jednym miejscu.

### Aktywny klucz

- **Lokalizacja:** `/Users/gniewkob/Repos/openbrain/.env` → `INTERNAL_API_KEY=<klucz>`
- **Nigdy nie umieszczać klucza bezpośrednio w docker-compose.unified.yml**

### 1. Lokalny Gateway (stdio) - Claude Desktop/Code

- **Lokalizacja:** `.mcp.json`, `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Transport:** stdio (lokalny skrypt `/unified/mcp-gateway/run-mcp.sh`)
- **Użycie:** Claude Desktop, Claude Code CLI
- **Klucz:** odczytywany z `.env`

### 2. HTTP/Docker - ChatGPT (ngrok)

- **Lokalizacja:** `docker-compose.unified.yml` → `${INTERNAL_API_KEY}` (z `.env`)
- **URL publiczny:** https://poutily-hemispheroidal-pia.ngrok-free.dev
- **Strona zgody:** https://poutily-hemispheroidal-pia.ngrok-free.dev/consent
- **Ważność tokenu:** 30 dni (persystowane w Redis — przeżywają restart kontenera)

---

## Konfiguracja ChatGPT

### Opcja A: GPTs z MCP Actions

1. Wejdź w **GPTs → Create → Configure**
2. Przewiń do **Actions**
3. Kliknij **Add actions**
4. W polu **Schema** wpisz:
   ```json
   {
     "openapi": "3.1.0",
     "info": {
       "title": "OpenBrain MCP",
       "version": "1.0"
     },
     "servers": [
       {
         "url": "https://poutily-hemispheroidal-pia.ngrok-free.dev"
       }
     ]
   }
   ```
5. Zapisz i przetestuj
6. Gdy ChatGPT poprosi o autoryzację, wpisz klucz:
   ```
   0FABJMzqD2cvBOC_dYbjKCnb51nDVlqo--f44nVwWrI
   ```

### Opcja B: Settings → MCP

1. **Settings → Personalization**
2. Sekcja **MCP Servers**
3. Dodaj nowy serwer:
   - **Name:** `openbrain`
   - **URL:** `https://poutily-hemispheroidal-pia.ngrok-free.dev`
   - **Type:** `streamable-http`
4. Potwierdź autoryzację wpisując klucz API

---

## Konfiguracja Claude Desktop (lokalnie)

Plik: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "openbrain": {
      "command": "/Users/gniewkob/Repos/openbrain/unified/mcp-gateway/run-mcp.sh",
      "env": {
        "BRAIN_URL": "http://127.0.0.1:7010",
        "INTERNAL_API_KEY": "<wartość INTERNAL_API_KEY z .env>",
        "ENABLE_LOCAL_OBSIDIAN_TOOLS": "1"
      }
    }
  }
}
```

---

## Debugowanie (Historia 2026-04-04)

### Problem 1: Kontener Ollama pusty

**Symptom:** Błąd `KeyError: 'embedding'` przy wyszukiwaniu  
**Przyczyna:** Kontener `openbrain-unified-ollama` nie miał pobranego modelu `nomic-embed-text`

**Rozwiązanie:**
Zmiana `docker-compose.unified.yml`:
```yaml
# Zmieniono:
OLLAMA_URL: http://ollama:11434
# Na:
OLLAMA_URL: http://host.docker.internal:11434
```

Wyłączono kontener Ollama - używana jest teraz lokalna instancja Ollama z macOS (dostępna pod `host.docker.internal:11434`).

### Problem 2: Brak kolumny `metadata`

**Symptom:** `column memories.metadata does not exist`  
**Rozwiązanie:** Dodano migrację `009_add_metadata_column.py`

### Problem 3: Niespójność typów UUID vs String

**Symptom:** `column "id" is of type uuid but expression is of type character varying`  
**Przyczyna:** Migracja tworzyła kolumny jako UUID, ale model SQLAlchemy oczekuje String  
**Rozwiązanie:** 
- Naprawiono migrację `001_unified_initial.py` (UUID → String)
- Dodano migrację `010_fix_uuid_to_string.py` dla istniejących baz

---

## Sprawdzanie statusu usług

```bash
# Status kontenerów
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep openbrain

# Test lokalnego API
curl -s http://127.0.0.1:7010/health

# Test embeddingów
curl -s -X POST http://127.0.0.1:11434/api/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model":"nomic-embed-text:latest","prompt":"test"}'

# Test publicznego MCP
curl -s https://poutily-hemispheroidal-pia.ngrok-free.dev/.well-known/openid-configuration
```

---

## Dostępne endpointy

| Usługa | Lokalny | Publiczny |
|--------|---------|-----------|
| Unified Server | http://127.0.0.1:7010 | - |
| MCP HTTP | http://127.0.0.1:7011 | https://poutily-hemispheroidal-pia.ngrok-free.dev |
| Database | localhost:5432 | - |
| Ollama | localhost:11434 | - (host.docker.internal:11434 z Docker) |

---

## Rotacja kluczy

Jeśli potrzebujesz wygenerować nowy klucz API:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Następnie zaktualizuj **tylko**:
1. `/Users/gniewkob/Repos/openbrain/.env` → `INTERNAL_API_KEY=<nowy_klucz>`
2. `~/Library/Application Support/Claude/claude_desktop_config.json` → pole `INTERNAL_API_KEY`
3. Zrestartuj kontenery: `docker compose -f docker-compose.unified.yml up -d`

`docker-compose.unified.yml` NIE wymaga zmian — czyta klucz z `.env` przez `${INTERNAL_API_KEY}`.

> **Uwaga:** Po rotacji klucza OAuth tokeny w Redis pozostają ważne ale nie będą mogły być
> zwalidowane (klucz jest używany tylko przy wystawianiu nowych tokenów, nie przy ich weryfikacji).
> Tokeny wygasną naturalnie po 30 dniach lub można wyczyścić Redis: `redis-cli -n 1 FLUSHDB`

---

## Historia zmian

### 2026-04-04 — Fixes deploymentu

**Bug 1: `brain_update` tworzył duplikaty zamiast aktualizować**
- Przyczyna: gateway wysyłał `POST /write` z `id` w payload (pole ignorowane przez schemat)
- Fix: dodano `PATCH /api/v1/memory/{id}` → wywołuje `update_memory()` przez ID
- Pliki: `src/api/v1/memory.py`, `mcp-gateway/src/main.py`

**Bug 2: Corporate versioning → `UniqueViolationError`**
- Przyczyna: nowy rekord był insertowany zanim stary zmienił status na `superseded`
- Fix: kolejność operacji w `_version_memory()`: najpierw `flush()` starego, potem insert nowego
- Plik: `src/memory_writes.py`

**Bug 3: OAuth tokeny przepadały po każdym restarcie mcp-http**
- Przyczyna: `SimpleKeyOAuthProvider` trzymał tokeny w pamięci procesu
- Fix: token store przeniesiony do Redis (db 1) z TTL 30 dni
- Pliki: `mcp-gateway/src/mcp_http.py`, `mcp-gateway/pyproject.toml`, `docker-compose.unified.yml`

**Bug 4: Dwa różne klucze w `.env` i `docker-compose.unified.yml`**
- Przyczyna: klucz hardcoded w compose, `.env` ignorowany
- Fix: `docker-compose.unified.yml` używa `${INTERNAL_API_KEY}` — jeden klucz w `.env`
