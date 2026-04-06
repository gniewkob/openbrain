# Kompleksowy Audyt OpenBrain - Raport

**Data audytu:** 2026-04-04  
**Audytor:** AI Assistant  
**Wersja kodu:** OpenBrain Unified v2.1

---

## Executive Summary

Na podstawie analizy kodu po ostatnich naprawach (synchronizacja kluczy API, naprawa `brain_update`, migracje bazy) zidentyfikowano **5 krytycznych problemów bezpieczeństwa**, **8 problemów jakościowych** oraz **4 obszary wymagające optymalizacji**.

### Kluczowe zagrożenia:
1. **Sekrety w repozytorium** (NGROK_AUTHTOKEN, hasła PostgreSQL)
2. **Brak walidacji schematów MCP vs Backend** - ryzyko przyszłych błędów 422
3. **Niebezpieczne wartości domyślne** w konfiguracji
4. **Brak rate limiting dla internal key**
5. **Nieprawidłowa obsługa błędów** w MCP gateway

---

## 1. KRYTYCZNE PROBLEMY BEZPIECZEŃSTWA 🔴

### 1.1. Sekrety w docker-compose.unified.yml (HIGH)
**Plik:** `docker-compose.unified.yml`
**Problemy:**
```yaml
# Linia 111 - NGROK_AUTHTOKEN w plaintext
NGROK_AUTHTOKEN=3Ac5z667AJsD4kiy76AoHJTEQax_5dEF5kAbdyzZk1JicaoNR

# Linia 7 - Hasło PostgreSQL w plaintext
POSTGRES_PASSWORD=2d0d0c4d2df44c61a4aa83eb94d0c1b7

# Linia 43, 58, 96 - INTERNAL_API_KEY powtarzany w wielu miejscach
```

**Ryzyko:**
- Sekrety są commitowane do repozytorium
- Każdy z dostępem do repo widzi wrażliwe dane
- Hasło do bazy danych jest widoczne w historii git

**Rekomendacja:**
```yaml
# Użyj .env file lub Docker secrets
environment:
  - NGROK_AUTHTOKEN=${NGROK_AUTHTOKEN}
  - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
  - INTERNAL_API_KEY=${INTERNAL_API_KEY}
```

### 1.2. Brak rotacji kluczy API (MEDIUM)
**Plik:** `unified/src/config.py` (linia 72-75)

Klucz INTERNAL_API_KEY nie ma:
- Daty ważności
- Mechanizmu rotacji
- Alerty przed wygaśnięciem

**Ryzyko:** Po 30 dniach (TTL tokenu) ChatGPT straci dostęp bez ostrzeżenia.

### 1.3. Niespójna walidacja klucza w różnych komponentach (MEDIUM)
- Backend wymaga min. 32 znaki (config.py:72)
- MCP gateway nie waliduje długości (main.py:39)
- Brak jednolitego schematu walidacji

### 1.4. Brak ochrony przed enumeration attacks (MEDIUM)
**Plik:** `unified/src/auth.py` (linia 523-534)

Różne kody błędów dla różnych sytuacji:
- 503 gdy brak OIDC
- 401 gdy brak headera
- 422 gdy błąd walidacji

To pozwala atakującemu na fingerprinting konfiguracji.

**Rekomendacja:** Używaj jednego kodu 401 dla wszystkich błędów auth.

### 1.5. Caching embeddingów bez limitu rozmiaru tekstu (LOW)
**Plik:** `unified/src/embed.py` (linia 27-31)

Tekst dowolnej długości jest hashowany i cache'owany. Brak:
- Limitu długości tekstu
- Sanity check przed wysłaniem do Ollama
- Rate limiting na poziomie embeddingów

---

## 2. PROBLEMY JAKOŚCIOWE / KONFIGURACYJNE 🟡

### 2.1. Schema Drift MCP vs Backend (HIGH)
**Problem historyczny:** `brain_update` wymagał `domain`, ale MCP tego nie miało.

**Pozostałe ryzyka:**
| MCP Tool | Backend wymaga | MCP Schema | Ryzyko |
|----------|----------------|------------|--------|
| brain_store_bulk | `records[].domain` | ❓ Niejasne | Możliwy błąd 422 |
| brain_upsert_bulk | `items[].domain` | ❓ Niejasne | Możliwy błąd 422 |
| brain_obsidian_sync | `domain` w body | ✅ OK | - |

**Rekomendacja:** Stworzyć jeden źródłowy schemat OpenAPI i generować typy dla MCP.

### 2.2. Brak wersjonowania API MCP (MEDIUM)
MCP tools nie mają wersji. Zmiana schematu jest breaking change bez migracji.

**Rekomendacja:** Dodać `api_version` do każdego toola:
```python
@mcp.tool()
async def brain_store(...) -> BrainMemory:
    """Version: 2.1.0"""
```

### 2.3. Niebezpieczne wartości domyślne (MEDIUM)
**Plik:** `unified/src/config.py`
```python
LOCAL_DEV_INTERNAL_API_KEY = "openbrain-local-dev"  # Linia 32
# Ten klucz jest fallbackiem jeśli INTERNAL_API_KEY nie jest ustawiony!
```

Jeśli ktoś zapomni ustawić INTERNAL_API_KEY, system używa przewidywalnego klucza.

### 2.4. Brak dokumentacji dla Obsidian tools (MEDIUM)
Obsidian tools są wyłączone domyślnie (`ENABLE_LOCAL_OBSIDIAN_TOOLS`), ale:
- Brak jasnego komunikatu użytkownikowi
- Brak dokumentacji jak włączyć
- Błąd pojawia się dopiero przy użyciu toola

### 2.5. Nieefektywne zapytania przy brain_update (LOW)
**Plik:** `unified/mcp-gateway/src/main.py` (linia 377-411)

Obecna implementacja:
1. GET /api/v1/memory/{id} - pobierz istniejący rekord
2. POST /api/v1/memory/write - zapisz zaktualizowany

To jest 2 zapytania HTTP zamiast 1. Backend powinien obsługiwać partial updates.

### 2.6. Brak spójności w obsłudze błędów (LOW)
**Plik:** `unified/mcp-gateway/src/main.py` (linia 119-139)

W produkcji szczegóły błędów są ukrywane:
```python
if is_production:
    if r.status_code >= 500:
        raise ValueError(f"Backend error: Internal server error")
```

To utrudnia debugowanie problemów w produkcji.

### 2.7. Brak testów integracyjnych MCP (LOW)
**Plik:** `unified/tests/test_mcp_transport.py`

Testy używają mocków (`_FakeResponse`, `_FakeClient`), nie testują:
- Rzeczywistej komunikacji z backendem
- Schematów request/response
- Obsługi błędów sieciowych

### 2.8. Migracje bez transakcji (LOW)
**Pliki:** `unified/migrations/versions/0*.py`

Migracje alembic nie używają:
```python
op.execute("BEGIN TRANSACTION;")
# ... changes ...
op.execute("COMMIT;")
```

W przypadku błędu w środku migracji, baza może zostać w niekonsekwentnym stanie.

---

## 3. PROBLEMY FUNKCJONALNE 🟠

### 3.1. PUBLIC_MODE=true bez OIDC_ISSUER_URL (HIGH)
**Plik:** `docker-compose.unified.yml` (linia 61)

Serwer działa w trybie publicznym bez OIDC. To oznacza:
- Wymagany jest INTERNAL_API_KEY
- Bez klucza: błąd 503
- Nie ma fallbacku do Auth0

To jest celowe działanie, ale dokumentacja tego nie wyjaśnia.

### 3.2. Brak walidacji tenant_id (MEDIUM)
**Plik:** `unified/src/schemas.py` (linia 134)

`tenant_id` jest opcjonalny, ale gdy podany, nie jest walidowany czy:
- Istnieje w systemie
- Użytkownik ma do niego dostęp
- Nie jest pustym stringiem

### 3.3. Nieobsługiwany przypadek w embedding cache (LOW)
**Plik:** `unified/src/embed.py` (linia 88-93)

Jeśli model embeddingowy się zmieni, cache zwraca stare embeddingi:
```python
if cached_model == config.embedding.model:
    return list(embedding)
# Co jeśli model się zmienił? Cache jest ignorowany, ale...
```

Brak czyszczenia cache przy zmianie modelu.

### 3.4. Brak limitu czasu dla maintenance (LOW)
**Plik:** `unified/src/memory_reads.py` (linia 416+)

`brain_maintain` może działać bardzo długo na dużej bazie bez:
- Timeoutu
- Progress reporting
- Możliwości przerwania

---

## 4. PROBLEMY WYDAJNOŚCIOWE 🟢

### 4.1. Brak connection pooling dla Ollama (MEDIUM)
**Plik:** `unified/src/embed.py` (linia 20, 34-43)

Klient HTTP jest tworzony globalnie, ale:
- Nie ma limitu równoczesnych połączeń do Ollama
- Brak backpressure gdy Ollama jest przeciążona
- Brak circuit breaker dla niedostępnej Ollamy

### 4.2. N+1 query problem w batch operations (MEDIUM)
**Plik:** `unified/src/memory_writes.py`

`brain_store_bulk` prawdopodobnie robi N zapytań zamiast 1 INSERT ... RETURNING.

### 4.3. Brak indeksów dla częstych zapytań (LOW)
**Plik:** `unified/src/models.py`

Brak indeksów na:
- `created_at` (używane w sortowaniu)
- `updated_at` (używane w sortowaniu)
- `content_hash` (używane w deduplikacji)

### 4.4. Brak kompresji dla dużych pól (LOW)
Pola `content` mogą mieć do 20,000 znaków (MAX_CONTENT_LEN). Brak kompresji w bazie.

---

## 5. REKOMENDACJE PRIORYTETOWE

### Natychmiast (P0)
1. **Przenieś wszystkie sekrety do .env** - użyj `docker-compose secrets` lub env files
2. **Rotacja kluczy API** - wygeneruj nowe klucze, ustaw przypomnienie o rotacji
3. **Dodaj walidację schematów** - stwórz testy sprawdzające zgodność MCP z backendem

### Krótkoterminowe (P1)
4. **Jednolita obsługa błędów auth** - zawsze zwracaj 401, nigdy 503
5. **Dodaj dokumentację Obsidian** - wyjaśnij jak włączyć i skonfigurować
6. **Rate limiting dla internal key** - ochrona przed abuse
7. **Timeout dla maintenance** - przerwij długotrwałe operacje

### Średnioterminowe (P2)
8. **Schematy wersjonowane** - wersjonowanie API MCP
9. **Lepsze testy integracyjne** - testy end-to-end z prawdziwym backendem
10. **Optymalizacja zapytań** - indeksy, batch inserts, kompresja

---

## 6. LISTA KONTROLNA NAPRAW

```markdown
- [ ] Przenieś NGROK_AUTHTOKEN do .env
- [ ] Przenieś POSTGRES_PASSWORD do .env
- [ ] Przenieś INTERNAL_API_KEY do .env
- [ ] Usuń stare wartości z historii git (git filter-branch)
- [ ] Dodaj walidację długości klucza w MCP gateway
- [ ] Ujednolić kody błędów auth (tylko 401)
- [ ] Dodaj testy schematów MCP vs Backend
- [ ] Dodaj dokumentację Obsidian tools
- [ ] Dodaj rate limiting dla internal key
- [ ] Dodaj timeout dla maintenance
- [ ] Dodaj indeksy na created_at, updated_at, content_hash
- [ ] Dodaj circuit breaker dla Ollama
```

---

## 7. WPŁYW NA UŻYTKOWNIKÓW

### Obecni użytkownicy (Claude Code, ChatGPT)
- ✅ Brain search działa
- ✅ Brain update działa (po naprawie)
- ✅ Brain store działa
- ⚠️ Obsidian wymaga dodatkowej konfiguracji

### Przyszli użytkownicy
- ⚠️ Muszą skonfigurować .env przed uruchomieniem
- ⚠️ Muszą rotować klucze co 30 dni (ChatGPT)

---

## 8. WNIOSKI

OpenBrain jest **funkcjonalny** ale wymaga **natychmiastowej uwagi** w zakresie bezpieczeństwa sekretów. Główne problemy są konfiguracyjne, nie architektoniczne.

**Ocena ogólna:** 6.5/10
- Funkcjonalność: 8/10
- Bezpieczeństwo: 4/10 (sekrety w repo)
- Jakość kodu: 7/10
- Dokumentacja: 6/10
- Testowanie: 5/10

**Rekomendacja:** Przed produkcyjnym użyciem wymagane jest wdrożenie wszystkich rekomendacji P0.
