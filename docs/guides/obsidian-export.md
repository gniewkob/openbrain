# 📤 OpenBrain → Obsidian Export Guide

## Wprowadzenie

Od teraz OpenBrain może eksportować dane **do** Obsidian, a nie tylko z niego importować. Możesz:

- ✅ Zapisywać pojedyncze notatki do Obsidian
- ✅ Eksportować zapytania (np. wszystkie decyzje o bezpieczeństwie)
- ✅ Tworzyć kolekcje (zbiorcze notatki z linkami)
- ✅ Grupować wyniki po typie, właścicielu lub tagach

---

## 🚀 Quick Start

### 1. Konfiguracja środowiska

Musisz wskazać OpenBrain ścieżki do swoich vaultów Obsidian:

```bash
# Opcja 1: Pojedyncza zmienna dla każdego vaultu
export OBSIDIAN_VAULT_DOCUMENTS_PATH="/Users/<user>/Documents/Obsidian/Documents"
export OBSIDIAN_VAULT_WORK_PATH="/Users/<user>/Documents/Obsidian/Work"

# Opcja 2: JSON z wieloma vaultami
export OBSIDIAN_VAULT_PATHS='{"Documents": "/path/to/Documents", "Work": "/path/to/Work"}'
```

### 2. Uruchomienie

```bash
# Upewnij się, że zmienne są ustawione
export OBSIDIAN_VAULT_DOCUMENTS_PATH="/path/to/vault"

# Uruchom OpenBrain
./start_unified.sh start
```

---

## 🛠️ MCP Tools (Claude/Code)

### brain_obsidian_write_note

Zapisuje pojedynczą notatkę do Obsidian:

```python
result = await brain_obsidian_write_note(
    vault="Documents",
    path="Projects/OpenBrain/Architecture.md",
    title="OpenBrain Architecture",
    content="""## Overview

OpenBrain uses a unified memory architecture...

## Components

- FastAPI backend
- PostgreSQL + pgvector
- MCP protocol support
""",
    tags=["openbrain", "architecture", "mcp"],
    frontmatter={
        "domain": "build",
        "entity_type": "Architecture",
        "owner": "<owner>",
        "priority": "high",
    },
    overwrite=True,  # Nadpisz jeśli istnieje
)

# Result:
# {
#     "vault": "Documents",
#     "path": "Projects/OpenBrain/Architecture.md",
#     "title": "OpenBrain Architecture",
#     "created": true,  # true = nowa, false = zaktualizowana
#     "file_hash": "abc123..."
# }
```

### brain_obsidian_export

Eksportuje wyniki zapytania do wielu notatek:

```python
# Eksportuj wszystkie decyzje o bezpieczeństwie
result = await brain_obsidian_export(
    vault="Documents",
    folder="Security/Decisions",  # Folder docelowy
    query="security authentication authorization",
    domain="corporate",
    max_items=30,
)

# Result:
# {
#     "vault": "Documents",
#     "folder": "Security/Decisions",
#     "exported_count": 15,
#     "exported": [
#         {"memory_id": "...", "path": "Security/Decisions/Auth0 Integration.md", "title": "...", "created": true},
#         ...
#     ],
#     "errors": []
# }
```

### brain_obsidian_collection

Tworzy zbiorczą notatkę z linkami (idealna do przeglądów):

```python
# Stwórz kolekcję decyzji tygodnia
result = await brain_obsidian_collection(
    query="decision created:>2026-03-27",
    collection_name="Weekly Decisions 2026-W13",
    vault="Documents",
    folder="Weekly Reviews",
    domain="corporate",
    max_items=50,
    group_by="entity_type",  # Grupuj po typie: Decision, Architecture, Risk
)

# Tworzy strukturę:
# Documents/Weekly Reviews/Weekly Decisions 2026-W13/
#   ├── Index.md              # Główny indeks z linkami
#   ├── Decision/
#   │   ├── Auth0 Integration.md
#   │   └── JWT Migration.md
#   ├── Architecture/
#   │   └── Security Layer.md
#   └── Risk/
#       └── Data Breach Response.md
```

---

## 🌐 REST API

### POST /api/v1/obsidian/write-note

```bash
curl -X POST http://localhost:7010/api/v1/obsidian/write-note \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "vault": "Documents",
    "path": "Notes/Idea.md",
    "content": "My new idea...",
    "frontmatter": {
      "title": "New Idea",
      "tags": ["idea", "mcp"]
    },
    "overwrite": false
  }'
```

### POST /api/v1/obsidian/export

```bash
# Eksportuj wszystkie memorie o AI
curl -X POST http://localhost:7010/api/v1/obsidian/export \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "vault": "Documents",
    "folder": "AI Research",
    "query": "artificial intelligence llm",
    "max_items": 20
  }'
```

### POST /api/v1/obsidian/collection

```bash
# Stwórz kolekcję
curl -X POST http://localhost:7010/api/v1/obsidian/collection \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "security",
    "collection_name": "Security Research",
    "vault": "Documents",
    "folder": "Research",
    "group_by": "entity_type"
  }'
```

---

## 📁 Format Eksportowanej Notatki

Każda eksportowana notatka ma format:

```markdown
---
title: Memory Title
openbrain_id: mem_abc123
domain: corporate
entity_type: Decision
owner: <owner>
version: 3
status: active
created_at: 2026-03-27T10:00:00
updated_at: 2026-03-28T14:30:00
tags:
  - security
  - auth
source: openbrain-export
---

# Memory Title

**Domain:** corporate
**Type:** Decision
**Owner:** <owner>
**Created:** 2026-03-27T10:00:00

## Content

Pełna treść memorii...

## Metadata

- ID: `mem_abc123`
- Version: 3
- Status: active
- Tags: security, auth
```

---

## 🎨 Custom Templates (w przyszłości)

Planowana funkcjonalność - własne szablony:

```python
result = await brain_obsidian_export(
    query="meeting",
    template="""
# {title}

**Date:** {created_at}
**Attendees:** {custom_fields.attendees}

## Agenda
{content}

## Action Items
{custom_fields.action_items}
"""
)
```

---

## 🔒 Bezpieczeństwo

- **Path Traversal**: Wszystkie ścieżki są walidowane (brak `../`)
- **Overwrite Protection**: Domyślnie `overwrite=False`
- **Access Control**: Endpointy wymagają uprawnień admina
- **Vault Isolation**: Zapisy tylko do skonfigurowanych vaultów

---

## 🐛 Troubleshooting

### "Cannot determine filesystem path for vault"

**Rozwiązanie:** Ustaw zmienną środowiskową:

```bash
export OBSIDIAN_VAULT_DOCUMENTS_PATH="/absolute/path/to/vault"
```

### "Note already exists"

**Rozwiązanie:** Użyj `overwrite=True` lub zmień ścieżkę.

### Brak uprawnień do zapisu

**Rozwiązanie:** Sprawdź uprawnienia do katalogu vault:

```bash
ls -la /path/to/vault
chmod u+w /path/to/vault
```

---

## 📚 Przykłady Użycia

### Tygodniowy raport decyzji

```python
# Automatyczne generowanie co tydzień
from datetime import datetime, timedelta

last_week = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

result = await brain_obsidian_collection(
    query=f"decision created:>{last_week}",
    collection_name=f"Decisions Week {datetime.now().strftime('%Y-W%U')}",
    vault="Documents",
    folder="Weekly Reviews/Decisions",
    group_by="owner",
)
```

### Eksport bazy wiedzy projektu

```python
# Eksportuj wszystko związane z projektem
result = await brain_obsidian_export(
    vault="Work",
    folder="Projects/OpenBrain",
    query="openbrain",
    max_items=100,
)
```

### Archiwum spotkań

```python
# Wszystkie spotkania z danego miesiąca
result = await brain_obsidian_collection(
    query="meeting 2026-03",
    collection_name="March 2026 Meetings",
    vault="Documents",
    folder="Meetings/2026",
    group_by="tags",
)
```

---

## 📝 Format Kolekcji (Index)

Wygenerowana notatka indeksu:

```markdown
# Security Research

*Collection generated from OpenBrain — 15 items*

**Query:** `security authentication`

## Grouped by: entity_type

### Decision
- [[Security Research/Decision/Auth0 Integration]] — Auth0 Integration
- [[Security Research/Decision/JWT Best Practices]] — JWT Best Practices

### Architecture
- [[Security Research/Architecture/Security Layer]] — Security Layer Design

### Risk
- [[Security Research/Risk/Data Breach Response]] — Data Breach Response Plan
```

---

*Więcej informacji w dokumentacji architektury: `docs/obsidian-audit-and-export-architecture.md`*
