# MIGRATION — named volume → bind mount (PostgreSQL + Redis)

Po `git pull` na tej zmianie [docker-compose.unified.yml](docker-compose.unified.yml) używa bind
mountów (`./data/postgres`, `./data/redis`) zamiast Docker named volumes
(`openbrain_postgres_data`, `openbrain_redis_data`). Powód: chroni dane przed
`docker volume prune` / CleanMyMac, robi je widocznymi dla skryptów na hoście.

**Konsekwencja:** po pull-u stack wystartuje z **pustą bazą**. Stare wolumeny
nadal istnieją w Dockerze — nie zostają usunięte automatycznie. Migracja jest
jednorazowa i bezpieczna o ile zachowasz kolejność.

## Procedura (~5 min)

### 1. Zatrzymaj stack na starym kompozycie
```bash
git stash                       # albo: git checkout <stary commit>
docker compose -f docker-compose.unified.yml up -d db  # tylko bazę
```

### 2. Zrób dump z named volume
```bash
mkdir -p backups
docker exec openbrain-unified-db pg_dump \
    -U postgres -d openbrain_unified \
    --no-owner --no-acl --format=custom --blobs \
    > backups/pre_migration_$(date +%Y%m%d_%H%M%S).dump
```

### 3. Zatrzymaj i usuń kontener (volume zostaje, dane przeżyją)
```bash
docker compose -f docker-compose.unified.yml down
```

### 4. Wróć do aktualnego brancha (bind mount config)
```bash
git stash pop                   # albo: git checkout master
mkdir -p data/postgres data/redis
```

### 5. Wystartuj na bind mount — pusta baza
```bash
docker compose -f docker-compose.unified.yml up -d db
```

### 6. Restore z dumpu
```bash
docker exec -i openbrain-unified-db pg_restore \
    -U postgres -d openbrain_unified --no-owner --no-acl --verbose \
    < backups/pre_migration_*.dump
```

### 7. Sprawdź
```bash
docker exec openbrain-unified-db psql -U postgres -d openbrain_unified \
    -c "SELECT count(*) FROM memories;"
```

### 8. (Opcjonalnie) usuń stare wolumeny
**Dopiero gdy zweryfikujesz że dane są na miejscu.**
```bash
docker volume rm openbrain_openbrain_postgres_data openbrain_openbrain_redis_data
```

## Redis

Redis trzyma OAuth tokeny z TTL — nie wymaga dumpu. Po restarcie użytkownicy
będą musieli się ponownie zalogować w Claude Desktop.

## Rollback

Jeśli coś pójdzie nie tak, stare wolumeny **wciąż istnieją**. Wróć do poprzedniego
commita compose-a (`git revert` lub przywróć `openbrain_postgres_data:/var/lib/postgresql/data`)
i `docker compose up -d`.
