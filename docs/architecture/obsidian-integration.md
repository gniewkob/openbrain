# 🔍 AUDYT OBSIDIAN INTEGRATION + ARCHITEKTURA EKSPORTU

**Data:** 2026-04-03  
**Cel:** Analiza obecnej integracji Obsidian + propozycja architektury eksportu z OpenBrain do Obsidian

---

## 📊 OBECNY STAN INTEGRACJI

### Funkcjonalność: ODCZYT Z OBSIDIAN (Implementowana ✓)

| Komponent | Metoda/Funkcja | Kierunek | Status |
|-----------|---------------|----------|--------|
| `obsidian_adapter.py` | `list_vaults()` | Obsidian → OpenBrain | ✅ |
| `obsidian_adapter.py` | `list_files()` | Obsidian → OpenBrain | ✅ |
| `obsidian_adapter.py` | `read_note()` | Obsidian → OpenBrain | ✅ |
| `obsidian_adapter.py` | `note_to_memory_write_record()` | Obsidian → OpenBrain | ✅ |
| `main.py` | `v1_obsidian_sync()` | Obsidian → OpenBrain | ✅ |
| MCP Gateway | `brain_obsidian_sync()` | Obsidian → OpenBrain | ✅ |
| MCP Gateway | `brain_obsidian_read_note()` | Obsidian → OpenBrain | ✅ |
| MCP Gateway | `brain_obsidian_vaults()` | Obsidian → OpenBrain | ✅ |

### 🔴 BRAKUJĄCA FUNKCJONALNOŚĆ: ZAPIS DO OBSIDIAN

| Komponent | Metoda/Funkcja | Kierunek | Status |
|-----------|---------------|----------|--------|
| `obsidian_adapter.py` | `write_note()` | OpenBrain → Obsidian | ❌ **BRAK** |
| `obsidian_adapter.py` | `update_note()` | OpenBrain → Obsidian | ❌ **BRAK** |
| `obsidian_adapter.py` | `delete_note()` | OpenBrain → Obsidian | ❌ **BRAK** |
| `main.py` | `v1_obsidian_export()` | OpenBrain → Obsidian | ❌ **BRAK** |
| MCP Gateway | `brain_obsidian_export()` | OpenBrain → Obsidian | ❌ **BRAK** |
| MCP Gateway | `brain_obsidian_collection()` | OpenBrain → Obsidian | ❌ **BRAK** |

---

## 🔍 SZCZEGÓŁOWY AUDYT OBECNEGO KODU

### 1. ObsidianCliAdapter (obsidian_adapter.py)

**Klasy i metody:**
```python
class ObsidianCliAdapter:
    - __init__(command, timeout_s)
    - _run(*args)                    # Execute obsidian CLI
    - list_vaults() → list[str]      # ✅ GET /vaults
    - list_files(vault, folder, limit) → list[str]  # ✅ GET /files
    - read_note(vault, path) → ObsidianNote  # ✅ GET /read
    - _validate_vault_path(vault, path)      # ✅ Security
    
    # ❌ BRAKUJE:
    # - write_note(vault, path, content, frontmatter) → bool
    # - update_note(vault, path, content, frontmatter) → bool
    # - delete_note(vault, path) → bool
    # - note_exists(vault, path) → bool
```

**Funkcje pomocnicze:**
```python
# Konwersja Obsidian → OpenBrain (ISTNIEJE ✓)
note_to_write_payload(note, ...) → dict
note_to_memory_write_record(note, ...) → MemoryWriteRecord

# Konwersja OpenBrain → Obsidian (BRAK ❌)
memory_to_note_content(memory, ...) → str      # Formatowanie notatki
memory_to_frontmatter(memory, ...) → dict      # Generowanie frontmatter
```

### 2. Endpointy API (main.py + routes_v1.py)

**Obecne endpointy:**
```
GET  /api/v1/obsidian/vaults          ✅ List vaults
POST /api/v1/obsidian/read-note       ✅ Read single note
POST /api/v1/obsidian/sync            ✅ Sync Obsidian → OpenBrain

# ❌ BRAKUJE:
# POST /api/v1/obsidian/write-note      Create/update note
# POST /api/v1/obsidian/export          Export memories to notes
# POST /api/v1/obsidian/collection      Create collection from query
# DELETE /api/v1/obsidian/note          Delete note
```

### 3. MCP Tools (mcp-gateway/src/main.py)

**Obecne tools:**
```python
brain_obsidian_vaults() → list[str]           ✅
brain_obsidian_read_note(path, vault) → dict  ✅
brain_obsidian_sync(vault, paths, folder)     ✅

# ❌ BRAKUJE:
# brain_obsidian_write_note(vault, path, content, frontmatter) → dict
# brain_obsidian_export(memory_ids, vault, folder) → dict
# brain_obsidian_collection(query, vault, folder, name) → dict
# brain_obsidian_delete_note(vault, path) → dict
```

### 4. Modele danych (schemas.py)

**Obecne:**
```python
class ObsidianNoteResponse(BaseModel):   # Odpowiedź z read
    vault: str
    path: str
    title: str
    content: str
    frontmatter: dict
    tags: list[str]
    file_hash: str

class ObsidianSyncRequest(BaseModel):    # Request do sync
    vault: str
    paths: list[str] | None
    folder: str | None
    limit: int
    domain: str
    entity_type: str
    owner: str
    tags: list[str]

class ObsidianSyncResponse(BaseModel):   # Odpowiedź z sync
    vault: str
    resolved_paths: list[str]
    scanned: int
    summary: dict
    results: list
```

**❌ BRAKUJE:**
```python
class ObsidianWriteRequest(BaseModel):
    vault: str
    path: str
    content: str
    frontmatter: dict | None
    overwrite: bool = False

class ObsidianExportRequest(BaseModel):
    memory_ids: list[str] | None
    query: str | None           # Search query
    domain: str | None
    vault: str
    folder: str
    template: str | None        # Optional template for formatting

class ObsidianCollectionRequest(BaseModel):
    query: str
    domain: str | None
    vault: str
    folder: str
    collection_name: str
    max_items: int = 50
    group_by: str | None        # Group by entity_type, owner, etc.
```

---

## 🏗️ PROPOZYCJA ARCHITEKTURY EKSPORTU

### Faza 1: Podstawowy Zapis do Obsidian (MVP)

#### 1.1 Rozszerzenie ObsidianCliAdapter

```python
class ObsidianCliAdapter:
    # ... istniejące metody ...
    
    async def write_note(
        self,
        vault: str,
        path: str,
        content: str,
        frontmatter: dict[str, Any] | None = None,
        overwrite: bool = False,
    ) -> ObsidianNote:
        """
        Write or update a note in Obsidian vault.
        
        Args:
            vault: Vault name
            path: Note path (e.g., "Projects/OpenBrain.md")
            content: Markdown content
            frontmatter: Optional YAML frontmatter dict
            overwrite: If False, raises error if note exists
        
        Returns:
            ObsidianNote: Written note metadata
        """
        self._validate_vault_path(vault, path)
        
        # Check if note exists
        if not overwrite:
            try:
                await self.read_note(vault, path)
                raise ObsidianCliError(f"Note already exists: {path}. Use overwrite=True to update.")
            except ObsidianCliError:
                pass  # Note doesn't exist, proceed
        
        # Construct full content with frontmatter
        full_content = self._build_note_content(content, frontmatter)
        
        # Write via CLI (assuming 'write' command exists)
        # If obsidian CLI doesn't support write, use alternative methods:
        # - Direct file write (if vault is local filesystem)
        # - Obsidian Local REST API plugin
        await self._write_note_to_filesystem(vault, path, full_content)
        
        # Return the written note
        return await self.read_note(vault, path)
    
    async def delete_note(self, vault: str, path: str) -> bool:
        """Delete a note from Obsidian vault."""
        self._validate_vault_path(vault, path)
        # Implementation depends on available methods
        # - Direct file deletion
        # - Obsidian Local REST API
        pass
    
    def _build_note_content(
        self,
        content: str,
        frontmatter: dict[str, Any] | None = None,
    ) -> str:
        """Build full note content with YAML frontmatter."""
        if not frontmatter:
            return content
        
        fm_lines = ["---"]
        for key, value in frontmatter.items():
            if isinstance(value, list):
                fm_lines.append(f"{key}:")
                for item in value:
                    fm_lines.append(f"  - {item}")
            elif isinstance(value, bool):
                fm_lines.append(f"{key}: {str(value).lower()}")
            else:
                fm_lines.append(f"{key}: {value}")
        fm_lines.append("---")
        fm_lines.append("")
        fm_lines.append(content)
        
        return "\n".join(fm_lines)
    
    async def _write_note_to_filesystem(
        self,
        vault: str,
        path: str,
        content: str,
    ) -> None:
        """
        Write note directly to vault filesystem.
        This requires knowing the vault's filesystem path.
        """
        # Get vault path from environment or config
        vault_root = self._get_vault_path(vault)
        if not vault_root:
            raise ObsidianCliError(f"Cannot determine filesystem path for vault: {vault}")
        
        full_path = Path(vault_root) / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        async with aiofiles.open(full_path, 'w', encoding='utf-8') as f:
            await f.write(content)
    
    def _get_vault_path(self, vault: str) -> str | None:
        """Get filesystem path for vault."""
        # Option 1: From environment variable
        env_var = f"OBSIDIAN_VAULT_{vault.upper().replace(' ', '_')}_PATH"
        path = os.environ.get(env_var)
        if path:
            return path
        
        # Option 2: From config file
        # Option 3: From Obsidian config (if accessible)
        
        return None
```

#### 1.2 Nowe Endpointy API

```python
# routes_v1.py
def register_v1_routes(app: FastAPI, handlers) -> None:
    # ... istniejące endpointy ...
    
    # Export single memory to Obsidian
    app.add_api_route(
        "/api/v1/obsidian/write-note",
        handlers.v1_obsidian_write_note,
        methods=["POST"],
        response_model=ObsidianNoteResponse,
    )
    
    # Export multiple memories
    app.add_api_route(
        "/api/v1/obsidian/export",
        handlers.v1_obsidian_export,
        methods=["POST"],
        response_model=ObsidianExportResponse,
    )
    
    # Create collection from query
    app.add_api_route(
        "/api/v1/obsidian/collection",
        handlers.v1_obsidian_collection,
        methods=["POST"],
        response_model=ObsidianCollectionResponse,
    )


# main.py - handlers
async def v1_obsidian_write_note(
    req: ObsidianWriteRequest,
    _user: dict = Depends(require_auth),
) -> ObsidianNoteResponse:
    """Write a single note to Obsidian vault."""
    _require_admin(_user)
    adapter = ObsidianCliAdapter()
    try:
        note = await adapter.write_note(
            vault=req.vault,
            path=req.path,
            content=req.content,
            frontmatter=req.frontmatter,
            overwrite=req.overwrite,
        )
    except ObsidianCliError as e:
        raise HTTPException(status_code=503, detail=str(e))
    
    return ObsidianNoteResponse(
        vault=note.vault,
        path=note.path,
        title=note.title,
        content=note.content,
        frontmatter=note.frontmatter,
        tags=note.tags,
        file_hash=note.file_hash,
    )


async def v1_obsidian_export(
    req: ObsidianExportRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_auth),
) -> ObsidianExportResponse:
    """
    Export memories from OpenBrain to Obsidian notes.
    
    Either memory_ids OR query+domain must be provided.
    """
    _require_admin(_user)
    
    # Get memories to export
    if req.memory_ids:
        memories = []
        for mid in req.memory_ids:
            mem = await get_memory(session, mid)
            if mem:
                memories.append(mem)
    elif req.query:
        search_results = await search_memories(
            session,
            SearchRequest(query=req.query, top_k=req.max_items or 50, filters={"domain": req.domain} if req.domain else {}),
        )
        memories = [mem for mem, _ in search_results]
    else:
        raise HTTPException(status_code=422, detail="Either memory_ids or query must be provided")
    
    # Export to Obsidian
    adapter = ObsidianCliAdapter()
    exported = []
    errors = []
    
    for memory in memories:
        try:
            # Generate note path
            safe_title = _sanitize_filename(memory.title or memory.id)
            path = f"{req.folder}/{safe_title}.md" if req.folder else f"{safe_title}.md"
            
            # Generate content
            content = _memory_to_note_content(memory, req.template)
            frontmatter = _memory_to_frontmatter(memory)
            
            note = await adapter.write_note(
                vault=req.vault,
                path=path,
                content=content,
                frontmatter=frontmatter,
                overwrite=True,
            )
            exported.append({"memory_id": memory.id, "path": note.path})
        except Exception as e:
            errors.append({"memory_id": memory.id, "error": str(e)})
    
    return ObsidianExportResponse(
        vault=req.vault,
        exported_count=len(exported),
        exported=exported,
        errors=errors,
    )


def _memory_to_note_content(memory: MemoryOut, template: str | None = None) -> str:
    """Convert memory to markdown note content."""
    if template:
        # Use custom template
        return template.format(
            title=memory.title or "Untitled",
            content=memory.content,
            domain=memory.domain,
            entity_type=memory.entity_type,
            created_at=memory.created_at,
            updated_at=memory.updated_at,
            owner=memory.owner,
            tags=", ".join(memory.tags),
        )
    
    # Default format
    lines = [
        f"# {memory.title or 'Untitled'}",
        "",
        f"**Domain:** {memory.domain}",
        f"**Type:** {memory.entity_type}",
        f"**Owner:** {memory.owner}",
        f"**Created:** {memory.created_at}",
        "",
        "## Content",
        "",
        memory.content,
        "",
        "## Metadata",
        "",
        f"- ID: `{memory.id}`",
        f"- Version: {memory.version}",
        f"- Status: {memory.status}",
        f"- Tags: {', '.join(memory.tags)}",
    ]
    return "\n".join(lines)


def _memory_to_frontmatter(memory: MemoryOut) -> dict[str, Any]:
    """Generate YAML frontmatter from memory metadata."""
    return {
        "title": memory.title,
        "openbrain_id": memory.id,
        "domain": memory.domain,
        "entity_type": memory.entity_type,
        "owner": memory.owner,
        "version": memory.version,
        "status": memory.status,
        "created_at": memory.created_at.isoformat() if hasattr(memory.created_at, 'isoformat') else memory.created_at,
        "updated_at": memory.updated_at.isoformat() if hasattr(memory.updated_at, 'isoformat') else memory.updated_at,
        "tags": memory.tags,
        "source": "openbrain-export",
    }


def _sanitize_filename(name: str) -> str:
    """Sanitize string for use as filename."""
    # Remove or replace unsafe characters
    unsafe = '<>:"/\\|?*'
    for char in unsafe:
        name = name.replace(char, '_')
    return name[:100]  # Limit length
```

### Faza 2: MCP Tools (Gateway)

```python
# mcp-gateway/src/main.py

@mcp.tool()
async def brain_obsidian_write_note(
    vault: str,
    path: str,
    content: str,
    title: str | None = None,
    tags: list[str] | None = None,
    frontmatter: dict[str, Any] | None = None,
    overwrite: bool = False,
) -> dict:
    """
    Write a note to Obsidian vault.
    
    Args:
        vault: Target vault name
        path: Note path (e.g., "Projects/Note.md")
        content: Markdown content
        title: Optional title (added as H1 if provided)
        tags: Optional tags for frontmatter
        frontmatter: Optional additional frontmatter fields
        overwrite: Overwrite existing note
    """
    _require_obsidian_local_tools_enabled()
    
    # Build full content
    full_content = content
    if title:
        full_content = f"# {title}\n\n{content}"
    
    # Merge frontmatter
    fm = frontmatter or {}
    if tags:
        fm["tags"] = tags
    
    async with _client() as c:
        r = await c.post("/api/v1/obsidian/write-note", json={
            "vault": vault,
            "path": path,
            "content": full_content,
            "frontmatter": fm,
            "overwrite": overwrite,
        })
        _raise(r)
        return r.json()


@mcp.tool()
async def brain_obsidian_export(
    vault: str,
    folder: str = "OpenBrain Export",
    memory_ids: list[str] | None = None,
    query: str | None = None,
    domain: str | None = None,
    max_items: int = 50,
) -> dict:
    """
    Export memories from OpenBrain to Obsidian notes.
    
    Args:
        vault: Target vault
        folder: Target folder in vault
        memory_ids: Specific memory IDs to export
        query: Search query to find memories
        domain: Filter by domain
        max_items: Maximum number of memories to export
    """
    _require_obsidian_local_tools_enabled()
    
    async with _client() as c:
        r = await c.post("/api/v1/obsidian/export", json={
            "vault": vault,
            "folder": folder,
            "memory_ids": memory_ids,
            "query": query,
            "domain": domain,
            "max_items": max_items,
        })
        _raise(r)
        return r.json()


@mcp.tool()
async def brain_obsidian_collection(
    query: str,
    collection_name: str,
    vault: str = "Documents",
    folder: str = "Collections",
    domain: str | None = None,
    max_items: int = 50,
    group_by: str | None = None,  # "entity_type", "owner", "tags"
) -> dict:
    """
    Create a collection (index note) from OpenBrain memories.
    
    Creates a single note with links to exported memory notes,
    organized by the specified grouping.
    
    Args:
        query: Search query
        collection_name: Name for the collection note
        vault: Target vault
        folder: Target folder
        domain: Filter by domain
        max_items: Maximum memories
        group_by: How to group memories (entity_type, owner, tags)
    """
    _require_obsidian_local_tools_enabled()
    
    # First export memories
    export_result = await brain_obsidian_export(
        vault=vault,
        folder=f"{folder}/{collection_name}",
        query=query,
        domain=domain,
        max_items=max_items,
    )
    
    # Create index note
    index_content = _build_collection_index(
        collection_name=collection_name,
        exported=export_result.get("exported", []),
        group_by=group_by,
    )
    
    adapter = ObsidianCliAdapter()
    note = await adapter.write_note(
        vault=vault,
        path=f"{folder}/{collection_name}/Index.md",
        content=index_content,
        frontmatter={
            "title": collection_name,
            "tags": ["openbrain-collection"],
            "query": query,
            "item_count": len(export_result.get("exported", [])),
        },
        overwrite=True,
    )
    
    return {
        "collection_name": collection_name,
        "vault": vault,
        "folder": folder,
        "exported_count": export_result.get("exported_count", 0),
        "index_path": note.path,
        "errors": export_result.get("errors", []),
    }


def _build_collection_index(
    collection_name: str,
    exported: list[dict],
    group_by: str | None,
) -> str:
    """Build markdown index for collection."""
    lines = [
        f"# {collection_name}",
        "",
        f"*Collection generated from OpenBrain — {len(exported)} items*",
        "",
    ]
    
    if group_by:
        lines.append(f"## Grouped by: {group_by}")
        lines.append("")
        # Grouping logic here
    else:
        lines.append("## Items")
        lines.append("")
        for item in exported:
            memory_id = item.get("memory_id", "")
            path = item.get("path", "")
            lines.append(f"- [[{path.replace('.md', '')}]] — `{memory_id}`")
    
    return "\n".join(lines)
```

---

## 🎯 PRZYKŁADY UŻYCIA

### Przykład 1: Eksport pojedynczej memorii

```python
# Via MCP tool
result = await brain_obsidian_write_note(
    vault="Documents",
    path="Projects/OpenBrain/Architecture.md",
    title="OpenBrain Architecture",
    content="""## Overview

OpenBrain uses a unified memory architecture with three domains:
- Corporate (append-only)
- Build (mutable)
- Personal (mutable)

## Components

...""",
    tags=["openbrain", "architecture"],
    frontmatter={
        "domain": "build",
        "entity_type": "Architecture",
        "owner": "<owner>",
    },
)
```

### Przykład 2: Tworzenie kolekcji z zapytania

```python
# Via MCP tool - stwórz kolekcję notatek o bezpieczeństwie
result = await brain_obsidian_collection(
    query="security authentication auth",
    collection_name="Security Research",
    vault="Documents",
    folder="Research",
    domain="corporate",
    max_items=30,
    group_by="entity_type",
)

# Tworzy strukturę:
# Documents/Research/Security Research/
#   ├── Index.md          # Główny indeks kolekcji
#   ├── Decision/
#   │   ├── Auth0 Integration.md
#   │   └── JWT Best Practices.md
#   └── Architecture/
#       └── Security Layer.md
```

### Przykład 3: Auto-generowanie raportu

```python
# Stwórz tygodniowy raport z memorie "decision"
result = await brain_obsidian_collection(
    query="decision created:>2026-03-27",
    collection_name="Weekly Decisions 2026-W13",
    vault="Documents",
    folder="Weekly Reports",
    domain="corporate",
    group_by="owner",
)
```

---

## 🔧 WYMAGANE ZMIANY W KONFIGURACJI

### 1. Environment Variables

```bash
# Nowe zmienne środowiskowe
OBSIDIAN_VAULT_DOCUMENTS_PATH=/Users/<user>/Documents/Obsidian/Documents
OBSIDIAN_VAULT_WORK_PATH=/Users/<user>/Documents/Obsidian/Work
# Format: OBSIDIAN_VAULT_{VAULT_NAME}_PATH

# Lub jedna zmienna z JSON map
OBSIDIAN_VAULT_PATHS='{"Documents": "/path/to/Documents", "Work": "/path/to/Work"}'
```

### 2. Permissions

- OpenBrain service potrzebuje **write access** do katalogów vaultów Obsidian
- Rekomendowane: dedykowany folder w vault (np. `OpenBrain/`) dla notatek generowanych przez system

### 3. Zależności

```toml
# pyproject.toml
dependencies = [
    # ... istniejące ...
    "aiofiles>=24.0",  # Async file operations
]
```

---

## ⚠️ UWAGI BEZPIECZEŃSTWA

1. **Path Traversal**: Walidacja ścieżek już istnieje (`_validate_vault_path`)
2. **Overwrite Protection**: Domyślnie `overwrite=False` - wymaga jawnej zgody
3. **Access Control**: Endpointy wymagają `_require_admin()` - tylko uprzywilejowani użytkownicy
4. **Backup**: Rekomendowane włączenie Obsidian Sync lub git backup przed masowym eksportem

---

## 📋 PLAN IMPLEMENTACJI

### Sprint 1: Podstawowy zapis (1 tydzień)
- [ ] `write_note()` w ObsidianCliAdapter
- [ ] `_write_note_to_filesystem()` z aiofiles
- [ ] Endpoint `POST /api/v1/obsidian/write-note`
- [ ] MCP tool `brain_obsidian_write_note()`
- [ ] ObsidianWriteRequest/Response schemas

### Sprint 2: Eksport masowy (1 tydzień)
- [ ] `v1_obsidian_export()` handler
- [ ] `_memory_to_note_content()` formatting
- [ ] `_memory_to_frontmatter()` generation
- [ ] MCP tool `brain_obsidian_export()`
- [ ] Testy eksportu

### Sprint 3: Kolekcje i grupowanie (1 tydzień)
- [ ] `brain_obsidian_collection()` MCP tool
- [ ] `_build_collection_index()`
- [ ] Grupowanie po entity_type, owner, tags
- [ ] Auto-generowanie indeksów

### Sprint 4: Szablony i zaawansowane (1 tydzień)
- [ ] System szablonów notatek
- [ ] Custom formatters per entity_type
- [ ] Wbudowane szablony (Daily Note, Meeting, Decision)
- [ ] Dokumentacja

---

## 🎁 DODATKOWE FUNKCJONALNOŚCI (Future)

1. **Bi-directional Sync**: Dwukierunkowa synchronizacja zmian
2. **Auto-linking**: Automatyczne tworzenie linków wiki `[[...]]` między powiązanymi memoriami
3. **Graph View**: Generowanie map relacji dla Obsidian Graph View
4. **Daily Notes**: Auto-generowanie Daily Notes z aktywności OpenBrain
5. **Templates**: Wbudowany edytor szablonów w UI OpenBrain

---

*Raport przygotowany na podstawie szczegółowego audytu kodu OpenBrain Unified.*
