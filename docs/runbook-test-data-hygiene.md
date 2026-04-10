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

## Debug: `Missing session ID` przy `brain_delete`
Ten błąd zwykle pochodzi z warstwy transportu MCP HTTP (sesja streamable), nie z backendowego `DELETE /api/v1/memory/{id}`.
Gateway/transport mapuje ten przypadek do komunikatu:
`Backend 400: Missing MCP session context; reconnect the MCP HTTP client and retry.`

Checklist:
1. Sprawdź backend direct API (z `X-Internal-Key`) — jeśli działa, problem jest w session/transport.
2. Sprawdź flow MCP HTTP: auth -> session start -> tool call.
3. Zrestartuj `mcp-http` i klienta MCP, aby odnowić sesję.
4. Jeśli błąd wraca tylko dla `delete`, zbierz request/response z gatewaya i porównaj z `store/get`.

## Kontrola końcowa
- `build` test records: `0`
- `corporate` test records: oznaczone `metadata.test_data=true`
- `active_memories_*` w metrykach nie zawiera test data
- `find` domyślny ukrywa test data, a `include_test_data=true` pokazuje je diagnostycznie
