# Runbook: Test Data Hygiene (OpenBrain MCP)

## Cel
Utrzymać operacyjne widoki pamięci (search, context, dashboard) bez danych testowych, bez naruszania governance domeny `corporate`.

## Zasady
- `build` i `personal`: testowe rekordy można usuwać.
- `corporate`: nie kasować twardo (append-only/audit). Oznaczać jako testowe i wykluczać z domyślnych odczytów.
- Domyślne odczyty (`/api/v1/memory/find`, search/list, metryki `active_memories_*`) ukrywają rekordy z `metadata.test_data=true`.
- Do diagnostyki można jawnie włączyć testy przez `filters.include_test_data=true`.

## Szybka diagnostyka
```bash
docker exec -i openbrain-unified-db psql -U postgres -d openbrain_unified -Atc \
"select domain,status,count(*) from memories group by domain,status order by domain,status;"
```

```bash
curl -sS http://127.0.0.1:7010/metrics | grep -E '^active_memories_(total|build_total|corporate_total|personal_total) '
```

```bash
curl -sS http://127.0.0.1:7010/metrics | grep -E '^hidden_test_data_(total|active_total|build_total|corporate_total|personal_total) '
```

```bash
# Wymaga auth/admin:
curl -sS "http://127.0.0.1:7010/api/v1/memory/admin/test-data/report?sample_limit=20"
```

Raport zawiera dodatkowo:
- `visible_status_counts` oraz `visible_domain_status_counts` — widok produkcyjny (bez `metadata.test_data=true`) dla szybkiego porównania visible vs hidden
- `hidden_active_ratio` oraz `hidden_active_ratio_by_domain` — udział ukrytych test-data w aktywnym zbiorze (globalnie i per domena)
- `top_owners` — najwięksi producenci test-data
- `match_key_prefix_counts` — najczęstsze prefiksy `match_key` (np. `test`, `openbrain-bulk-test`)
- `null_match_key_count` — liczba rekordów testowych bez `match_key`
- `recommended_actions` — gotowe rekomendacje operacyjne (code + priority + summary) do sekwencji: dry-run → decyzja → wykonanie

Interpretacja:
- `hidden_active_ratio >= 0.25` traktuj jako sygnał wysokiego ryzyka operacyjnego (dashboard/retrieval mogą wyglądać na „puste” mimo istniejących danych testowych).

## Controlled cleanup (build domain)
```bash
# 1) Dry-run (default behavior)
curl -sS -X POST "http://127.0.0.1:7010/api/v1/memory/admin/test-data/cleanup-build" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true, "limit": 100}'

# 2) Execute (after approval)
curl -sS -X POST "http://127.0.0.1:7010/api/v1/memory/admin/test-data/cleanup-build" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false, "limit": 100}'
```

Zasada bezpieczeństwa:
- endpoint działa tylko dla `domain=build` i tylko dla rekordów z `metadata.test_data=true`
- `dry_run=true` nie wykonuje mutacji

## Wykrywanie kandydatów testowych (SQL)
```sql
SELECT id, domain, status, match_key, left(content, 120)
FROM memories
WHERE lower(coalesce(match_key,'')) ~ '^(test:|openbrain-bulk-test|.*-test-)'
   OR lower(content) IN ('test','smoke test','check','test memory','test z kimi','test update z domain')
   OR lower(content) LIKE 'temporary bulk test%';
```

## Cleanup `build` (safe delete)
Kasuj tylko rekordy testowe z `domain='build'`.

## Quarantine `corporate` (bez kasowania)
```sql
UPDATE memories
SET metadata = jsonb_set(
                jsonb_set(coalesce(metadata, '{}'::jsonb), '{test_data}', 'true'::jsonb, true),
                '{test_data_reason}',
                to_jsonb('legacy test fixture'::text),
                true
              )
WHERE domain='corporate'
  AND (
    lower(coalesce(match_key,'')) ~ '^(test:|openbrain-bulk-test|.*-test-)'
    OR lower(content) IN ('test','smoke test','check','test memory','test z kimi','test update z domain')
    OR lower(content) LIKE 'temporary bulk test%'
  );
```

## Naprawa: nieprawidłowe typy w `custom_fields`

### Objaw
`brain_search` lub `brain_list` zwraca HTTP 422:
```
Value error, custom_fields['<pole>'] type list not allowed (str | int | float | bool | None only)
```
Błąd blokuje **wszystkie** odczyty — search, list i get_context przestają działać.

### Przyczyna
Backend waliduje `custom_fields` przy deserializacji (Pydantic). Dozwolone typy to wyłącznie skalary: `str | int | float | bool | None`. Listy i obiekty przechodzą przez zapis do DB bez błędu, ale rozsypują każdy odczyt który trafi na taki rekord.

### Diagnostyka — znajdź wszystkie naruszenia
```bash
docker exec openbrain-unified-db psql -U postgres -d openbrain_unified -c "
SELECT id, key,
  jsonb_typeof(metadata->'custom_fields'->key) AS type_of,
  metadata->'custom_fields'->key AS value
FROM memories,
  jsonb_object_keys(metadata->'custom_fields') AS key
WHERE status = 'active'
  AND jsonb_typeof(metadata->'custom_fields'->key) IN ('array', 'object')
ORDER BY id, key;
"
```

Wynik pusty (`0 rows`) = baza czysta, problem gdzie indziej.

### Naprawa — konwersja tablic na string (join `, `)
```bash
docker exec openbrain-unified-db psql -U postgres -d openbrain_unified -c "
UPDATE memories
SET metadata = jsonb_set(
  metadata,
  ARRAY['custom_fields', sub.key],
  to_jsonb(array_to_string(
    ARRAY(SELECT jsonb_array_elements_text(metadata->'custom_fields'->sub.key)),
    ', '
  ))
)
FROM (
  SELECT DISTINCT m.id, k AS key
  FROM memories m,
    jsonb_object_keys(m.metadata->'custom_fields') AS k
  WHERE m.status = 'active'
    AND jsonb_typeof(m.metadata->'custom_fields'->k) = 'array'
) AS sub
WHERE memories.id = sub.id;
"
```

Dla pól z typem `object` — usunąć pole lub spłaszczyć ręcznie (nie ma ogólnej konwersji).

### Weryfikacja po naprawie
```bash
# Brak wierszy = baza czysta
docker exec openbrain-unified-db psql -U postgres -d openbrain_unified -c "
SELECT count(*) FROM memories, jsonb_object_keys(metadata->'custom_fields') AS key
WHERE status = 'active'
  AND jsonb_typeof(metadata->'custom_fields'->key) IN ('array', 'object');
"

# Funkcjonalny test
curl -sS -X POST http://127.0.0.1:7010/api/v1/memory/find \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "top_k": 1}' | python3 -c "import sys,json; print('OK' if 'result' in json.load(sys.stdin) else 'FAIL')"
```

### Prewencja
Przy zapisie przez `brain_store` / `brain_update` — nigdy nie przekazuj list ani słowników jako wartości `custom_fields`. Zamiast listy użyj stringa (join) lub rozdziel na kilka pól skalarnych.

## Debug: `Missing session ID` przy `brain_delete`
Ten błąd pochodzi z warstwy transportu MCP HTTP (sesja streamable), nie z backendowego `DELETE /api/v1/memory/{id}`.
Od `mcp_http` z `stateless_http=True` nie powinien już występować w normalnym flow ChatGPT/Claude.
Jeśli się pojawia, najczęściej oznacza stary proces `mcp-http` albo klienta działającego na starej sesji.

Checklist:
1. Sprawdź backend direct API (z `X-Internal-Key`) — jeśli działa, problem jest w session/transport.
2. Zweryfikuj, że `unified/mcp-gateway/src/mcp_http.py` uruchamia `mcp.run(..., stateless_http=True, ...)`.
3. Zrestartuj `mcp-http` i klienta MCP, aby wymusić nowe połączenie.
4. Jeśli błąd wraca tylko dla `delete`, zbierz request/response z gatewaya i porównaj z `store/get`.

## Kontrola końcowa
- `build` test records: `0`
- `corporate` test records: oznaczone `metadata.test_data=true`
- `active_memories_*` w metrykach nie zawiera test data
- `find` domyślny ukrywa test data, a `include_test_data=true` pokazuje je diagnostycznie
