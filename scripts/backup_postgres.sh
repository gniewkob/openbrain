#!/bin/bash
#
# PostgreSQL Backup Script for OpenBrain Unified
# Usage: ./scripts/backup_postgres.sh [--full|--incremental|--list|--restore <file>]
#
set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${BACKUP_DIR:-${PROJECT_ROOT}/backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DATE=$(date +%Y%m%d)

# Database configuration (from environment or defaults)
DB_NAME="${POSTGRES_DB:-openbrain_unified}"
DB_USER="${POSTGRES_USER:-postgres}"
DB_PASSWORD="${POSTGRES_PASSWORD:-}"
DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_PORT:-5432}"

# Backup configuration
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
S3_BUCKET="${BACKUP_S3_BUCKET:-}"
S3_PREFIX="${BACKUP_S3_PREFIX:-backups/postgres}"
COMPRESSION_LEVEL="${BACKUP_COMPRESSION_LEVEL:-6}"

# Export password for pg_dump
export PGPASSWORD="${DB_PASSWORD}"

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

ensure_backup_dir() {
    mkdir -p "${BACKUP_DIR}"
    log_info "Backup directory: ${BACKUP_DIR}"
}

check_dependencies() {
    if ! command -v pg_dump &> /dev/null; then
        log_error "pg_dump not found. Please install PostgreSQL client."
        exit 1
    fi
    
    if ! command -v pg_restore &> /dev/null; then
        log_error "pg_restore not found. Please install PostgreSQL client."
        exit 1
    fi
    
    if [[ -n "${S3_BUCKET}" ]] && ! command -v aws &> /dev/null; then
        log_warn "AWS CLI not found. S3 upload will be skipped."
    fi
}

test_connection() {
    log_info "Testing database connection..."
    if ! pg_isready -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" > /dev/null 2>&1; then
        log_error "Cannot connect to PostgreSQL at ${DB_HOST}:${DB_PORT}"
        exit 1
    fi
    log_info "Database connection successful"
}

get_backup_size() {
    local file="$1"
    if [[ -f "$file" ]]; then
        du -h "$file" | cut -f1
    else
        echo "unknown"
    fi
}

create_full_backup() {
    local backup_file="${BACKUP_DIR}/openbrain_full_${TIMESTAMP}.dump"
    local compressed_file="${backup_file}.gz"
    
    log_info "Starting full backup of ${DB_NAME}..."
    log_info "Output: ${compressed_file}"
    
    # Create backup
    pg_dump \
        -h "${DB_HOST}" \
        -p "${DB_PORT}" \
        -U "${DB_USER}" \
        -d "${DB_NAME}" \
        --verbose \
        --no-owner \
        --no-acl \
        --format=custom \
        --blobs \
        2>"${BACKUP_DIR}/backup_${TIMESTAMP}.log" | \
        gzip -${COMPRESSION_LEVEL} > "${compressed_file}"
    
    if [[ ${PIPESTATUS[0]} -eq 0 ]]; then
        local size=$(get_backup_size "${compressed_file}")
        log_info "Backup completed successfully"
        log_info "Size: ${size}"
        log_info "File: ${compressed_file}"
        
        # Create checksum
        sha256sum "${compressed_file}" > "${compressed_file}.sha256"
        
        # Upload to S3 if configured
        if [[ -n "${S3_BUCKET}" ]] && command -v aws &> /dev/null; then
            upload_to_s3 "${compressed_file}"
        fi
        
        # Cleanup old backups
        cleanup_old_backups
        
        return 0
    else
        log_error "Backup failed! Check log: ${BACKUP_DIR}/backup_${TIMESTAMP}.log"
        rm -f "${compressed_file}"
        return 1
    fi
}

upload_to_s3() {
    local file="$1"
    local filename=$(basename "$file")
    local s3_path="s3://${S3_BUCKET}/${S3_PREFIX}/${filename}"
    
    log_info "Uploading to S3: ${s3_path}"
    
    if aws s3 cp "${file}" "${s3_path}" --storage-class STANDARD_IA; then
        log_info "S3 upload successful"
        
        # Upload checksum
        aws s3 cp "${file}.sha256" "${s3_path}.sha256" --storage-class STANDARD_IA
    else
        log_error "S3 upload failed"
        return 1
    fi
}

cleanup_old_backups() {
    log_info "Cleaning up backups older than ${RETENTION_DAYS} days..."
    
    # Local cleanup
    find "${BACKUP_DIR}" -name "openbrain_*.dump.gz" -mtime +${RETENTION_DAYS} -delete
    find "${BACKUP_DIR}" -name "openbrain_*.dump.gz.sha256" -mtime +${RETENTION_DAYS} -delete
    find "${BACKUP_DIR}" -name "backup_*.log" -mtime +${RETENTION_DAYS} -delete
    
    # S3 cleanup
    if [[ -n "${S3_BUCKET}" ]] && command -v aws &> /dev/null; then
        local cutoff_date=$(date -d "${RETENTION_DAYS} days ago" +%Y-%m-%d 2>/dev/null || date -v-${RETENTION_DAYS}d +%Y-%m-%d)
        
        aws s3 ls "s3://${S3_BUCKET}/${S3_PREFIX}/" | \
            while read -r line; do
                file_date=$(echo "$line" | awk '{print $1}')
                filename=$(echo "$line" | awk '{print $4}')
                if [[ "$file_date" < "$cutoff_date" ]]; then
                    log_info "Deleting old S3 backup: ${filename}"
                    aws s3 rm "s3://${S3_BUCKET}/${S3_PREFIX}/${filename}"
                fi
            done
    fi
    
    log_info "Cleanup completed"
}

list_backups() {
    log_info "Available backups:"
    echo ""
    printf "%-25s %-15s %-20s\n" "TIMESTAMP" "SIZE" "LOCATION"
    printf "%s\n" "---------------------------------------------------------"
    
    # Local backups
    for backup in "${BACKUP_DIR}"/openbrain_*.dump.gz; do
        if [[ -f "$backup" ]]; then
            local filename=$(basename "$backup")
            local size=$(get_backup_size "$backup")
            local timestamp=$(echo "$filename" | grep -oE '[0-9]{8}_[0-9]{6}' || echo "unknown")
            printf "%-25s %-15s %-20s\n" "${timestamp}" "${size}" "local"
        fi
    done
    
    # S3 backups
    if [[ -n "${S3_BUCKET}" ]] && command -v aws &> /dev/null; then
        aws s3 ls "s3://${S3_BUCKET}/${S3_PREFIX}/" 2>/dev/null | \
            grep ".dump.gz$" | \
            while read -r line; do
                local date=$(echo "$line" | awk '{print $1}')
                local time=$(echo "$line" | awk '{print $2}')
                local size=$(echo "$line" | awk '{print $3}')
                local filename=$(echo "$line" | awk '{print $4}')
                local timestamp=$(echo "$filename" | grep -oE '[0-9]{8}_[0-9]{6}' || echo "unknown")
                printf "%-25s %-15s %-20s\n" "${timestamp}" "${size}" "s3"
            done
    fi
}

restore_backup() {
    local backup_file="$1"
    
    if [[ ! -f "$backup_file" ]]; then
        # Try to find in backup directory
        backup_file="${BACKUP_DIR}/${backup_file}"
        if [[ ! -f "$backup_file" ]]; then
            log_error "Backup file not found: $1"
            exit 1
        fi
    fi
    
    log_warn "This will DROP and recreate the database ${DB_NAME}!"
    log_warn "Make sure you have a recent backup before proceeding."
    echo ""
    read -p "Are you sure? Type 'RESTORE' to continue: " confirm
    
    if [[ "$confirm" != "RESTORE" ]]; then
        log_info "Restore cancelled"
        exit 0
    fi
    
    log_info "Starting restore from ${backup_file}..."
    
    # Verify checksum if exists
    if [[ -f "${backup_file}.sha256" ]]; then
        log_info "Verifying checksum..."
        if ! sha256sum -c "${backup_file}.sha256" > /dev/null 2>&1; then
            log_error "Checksum verification failed!"
            exit 1
        fi
        log_info "Checksum verified"
    fi
    
    # Drop and recreate database
    log_info "Dropping database ${DB_NAME}..."
    dropdb -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" --if-exists "${DB_NAME}"
    
    log_info "Creating database ${DB_NAME}..."
    createdb -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" "${DB_NAME}"
    
    # Restore
    log_info "Restoring data..."
    if [[ "$backup_file" == *.gz ]]; then
        gunzip -c "${backup_file}" | pg_restore \
            -h "${DB_HOST}" \
            -p "${DB_PORT}" \
            -U "${DB_USER}" \
            -d "${DB_NAME}" \
            --verbose \
            --no-owner \
            --no-acl \
            2>&1
    else
        pg_restore \
            -h "${DB_HOST}" \
            -p "${DB_PORT}" \
            -U "${DB_USER}" \
            -d "${DB_NAME}" \
            --verbose \
            --no-owner \
            --no-acl \
            "${backup_file}" \
            2>&1
    fi
    
    log_info "Restore completed successfully"
}

# Main
main() {
    local command="${1:---full}"
    
    log_info "OpenBrain PostgreSQL Backup Tool"
    log_info "================================"
    
    ensure_backup_dir
    check_dependencies
    
    case "$command" in
        --full|-f)
            test_connection
            create_full_backup
            ;;
        --list|-l)
            list_backups
            ;;
        --restore|-r)
            if [[ -z "${2:-}" ]]; then
                log_error "Usage: $0 --restore <backup_file>"
                exit 1
            fi
            restore_backup "$2"
            ;;
        --cleanup|-c)
            cleanup_old_backups
            ;;
        --help|-h)
            cat << EOF
OpenBrain PostgreSQL Backup Tool

Usage: $0 [OPTION]

Options:
    --full, -f          Create a full backup (default)
    --list, -l          List available backups
    --restore, -r FILE  Restore from backup file
    --cleanup, -c       Clean up old backups
    --help, -h          Show this help message

Environment Variables:
    POSTGRES_DB         Database name (default: openbrain_unified)
    POSTGRES_USER       Database user (default: postgres)
    POSTGRES_PASSWORD   Database password
    POSTGRES_HOST       Database host (default: localhost)
    POSTGRES_PORT       Database port (default: 5432)
    BACKUP_DIR          Backup directory (default: ./backups)
    BACKUP_RETENTION_DAYS   Retention period in days (default: 30)
    BACKUP_S3_BUCKET    S3 bucket for remote backups
    BACKUP_S3_PREFIX    S3 key prefix (default: backups/postgres)

Examples:
    $0                              # Create full backup
    $0 --list                       # List backups
    $0 --restore backup.dump.gz     # Restore from file
    BACKUP_S3_BUCKET=mybucket $0    # Backup to S3
EOF
            ;;
        *)
            log_error "Unknown command: $command"
            log_error "Use --help for usage information"
            exit 1
            ;;
    esac
}

main "$@"
