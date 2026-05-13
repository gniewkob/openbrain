#!/bin/bash
#
# PostgreSQL Backup Script for OpenBrain Unified
# Używa `docker exec` na kontenerze openbrain-unified-db — nie wymaga lokalnego pg_dump.
#
# Usage: ./scripts/backup_postgres.sh [--full|--list|--restore <file>|--cleanup|--help]
#
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${BACKUP_DIR:-${PROJECT_ROOT}/backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

CONTAINER="${POSTGRES_CONTAINER:-openbrain-unified-db}"

# Wczytaj .env jeśli istnieje
if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${PROJECT_ROOT}/.env"
    set +a
fi

DB_NAME="${POSTGRES_DB:-openbrain_unified}"
DB_USER="${POSTGRES_USER:-postgres}"

RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
COMPRESSION_LEVEL="${BACKUP_COMPRESSION_LEVEL:-6}"

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }

# macOS nie ma sha256sum w domyślnej instalacji — fallback do `shasum -a 256`.
sha256_write() {
    local target="$1"
    if command -v sha256sum &>/dev/null; then
        sha256sum "$target" > "${target}.sha256"
    else
        ( cd "$(dirname "$target")" && shasum -a 256 "$(basename "$target")" ) > "${target}.sha256"
    fi
}

sha256_verify() {
    local target="$1"
    local sumfile="${target}.sha256"
    if command -v sha256sum &>/dev/null; then
        ( cd "$(dirname "$target")" && sha256sum -c "$(basename "$sumfile")" )
    else
        ( cd "$(dirname "$target")" && shasum -a 256 -c "$(basename "$sumfile")" )
    fi
}

check_docker() {
    if ! command -v docker &>/dev/null; then
        log_error "docker nie znaleziony w PATH"
        exit 1
    fi
}

check_container() {
    if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
        log_error "Kontener '$CONTAINER' nie biegnie. Uruchom: docker compose -f docker-compose.unified.yml up -d db"
        exit 1
    fi
}

test_connection() {
    log_info "Sprawdzam połączenie z bazą w kontenerze..."
    if ! docker exec "$CONTAINER" pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; then
        log_error "Nie mogę połączyć się z bazą $DB_NAME jako $DB_USER w $CONTAINER"
        exit 1
    fi
    log_info "OK — baza odpowiada"
}

ensure_backup_dir() {
    mkdir -p "$BACKUP_DIR"
}

get_size() {
    local f="$1"
    [[ -f "$f" ]] && du -h "$f" | cut -f1 || echo "unknown"
}

create_full_backup() {
    local backup_file="${BACKUP_DIR}/openbrain_full_${TIMESTAMP}.dump.gz"
    local log_file="${BACKUP_DIR}/backup_${TIMESTAMP}.log"

    log_info "Pełny backup ${DB_NAME} → ${backup_file}"

    # pg_dump w kontenerze, format custom, ze stdout, kompresowany gzipem po stronie hosta.
    # `set -o pipefail` u góry pliku gwarantuje, że błąd pg_dump propaguje się przez pipe'a,
    # więc poniższy `if` jest wystarczający — nie potrzebujemy osobnego sprawdzania PIPESTATUS.
    if docker exec "$CONTAINER" pg_dump \
            -U "$DB_USER" \
            -d "$DB_NAME" \
            --no-owner \
            --no-acl \
            --format=custom \
            --blobs \
            2>"$log_file" \
        | gzip -"$COMPRESSION_LEVEL" > "$backup_file"; then
        sha256_write "$backup_file"
        log_info "Gotowe — rozmiar $(get_size "$backup_file")"
        cleanup_old_backups
        return 0
    else
        log_error "Backup nie powiódł się. Log: $log_file"
        rm -f "$backup_file"
        return 1
    fi
}

list_backups() {
    log_info "Backupy w $BACKUP_DIR:"
    printf "\n%-25s %-10s %s\n" "TIMESTAMP" "ROZMIAR" "PLIK"
    printf -- '-%.0s' {1..70}; echo
    local found=0
    for f in "$BACKUP_DIR"/openbrain_*.dump.gz; do
        [[ -f "$f" ]] || continue
        found=1
        local fn ts size
        fn=$(basename "$f")
        ts=$(echo "$fn" | grep -oE '[0-9]{8}_[0-9]{6}' || echo "?")
        size=$(get_size "$f")
        printf "%-25s %-10s %s\n" "$ts" "$size" "$fn"
    done
    [[ $found -eq 0 ]] && echo "(brak backupów)"
}

cleanup_old_backups() {
    log_info "Czyszczę backupy starsze niż ${RETENTION_DAYS} dni..."
    find "$BACKUP_DIR" -name "openbrain_*.dump.gz"        -mtime "+${RETENTION_DAYS}" -delete 2>/dev/null || true
    find "$BACKUP_DIR" -name "openbrain_*.dump.gz.sha256" -mtime "+${RETENTION_DAYS}" -delete 2>/dev/null || true
    find "$BACKUP_DIR" -name "backup_*.log"               -mtime "+${RETENTION_DAYS}" -delete 2>/dev/null || true
}

restore_backup() {
    local backup_file="$1"
    if [[ ! -f "$backup_file" ]]; then
        backup_file="${BACKUP_DIR}/${backup_file}"
        [[ ! -f "$backup_file" ]] && { log_error "Nie znaleziono: $1"; exit 1; }
    fi

    log_warn "To DROPNIE i odtworzy bazę ${DB_NAME}!"
    read -rp "Wpisz RESTORE żeby kontynuować: " confirm
    [[ "$confirm" != "RESTORE" ]] && { log_info "Anulowane"; exit 0; }

    if [[ -f "${backup_file}.sha256" ]]; then
        log_info "Weryfikuję sha256..."
        sha256_verify "$backup_file" || { log_error "Checksum FAIL"; exit 1; }
    fi

    log_info "Terminuję aktywne sesje w $DB_NAME..."
    docker exec "$CONTAINER" psql -U "$DB_USER" -d postgres -c \
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity \
         WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();" >/dev/null

    log_info "Dropuję $DB_NAME..."
    docker exec "$CONTAINER" psql -U "$DB_USER" -d postgres -c "DROP DATABASE IF EXISTS \"$DB_NAME\";"
    docker exec "$CONTAINER" psql -U "$DB_USER" -d postgres -c "CREATE DATABASE \"$DB_NAME\";"

    log_info "Odtwarzam dane..."
    gunzip -c "$backup_file" | docker exec -i "$CONTAINER" pg_restore \
        -U "$DB_USER" -d "$DB_NAME" --no-owner --no-acl --verbose
    log_info "Restore zakończony"
}

usage() {
    cat <<EOF
OpenBrain PostgreSQL Backup (przez docker exec)

Użycie: $0 [OPCJA]

  --full, -f          Pełny backup (default)
  --list, -l          Pokaż backupy
  --restore, -r FILE  Odtwórz z pliku
  --cleanup, -c       Wyczyść stare backupy
  --help, -h          Pomoc

Zmienne środowiskowe:
  POSTGRES_CONTAINER  Nazwa kontenera (default: openbrain-unified-db)
  POSTGRES_DB         Nazwa bazy (default: openbrain_unified, override z .env)
  POSTGRES_USER       User (default: postgres, override z .env)
  BACKUP_DIR          Katalog backupów (default: \$PROJECT_ROOT/backups)
  BACKUP_RETENTION_DAYS  Ile dni trzymać (default: 14)
EOF
}

main() {
    local cmd="${1:---full}"
    log_info "OpenBrain PostgreSQL Backup"
    ensure_backup_dir
    check_docker

    case "$cmd" in
        --full|-f)
            check_container
            test_connection
            create_full_backup
            ;;
        --list|-l)
            list_backups
            ;;
        --restore|-r)
            [[ -z "${2:-}" ]] && { log_error "Podaj plik backupu"; exit 1; }
            check_container
            restore_backup "$2"
            ;;
        --cleanup|-c)
            cleanup_old_backups
            ;;
        --help|-h)
            usage
            ;;
        *)
            log_error "Nieznana opcja: $cmd"
            usage
            exit 1
            ;;
    esac
}

main "$@"
