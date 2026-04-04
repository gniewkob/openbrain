"""Converters between Memory and Obsidian Note formats."""

from __future__ import annotations

from typing import Any

from ..schemas import MemoryOut, ObsidianExportItem


def sanitize_filename(name: str) -> str:
    """Sanitize string for use as filename."""
    unsafe = '<>:"/\\|?*'
    for char in unsafe:
        name = name.replace(char, '_')
    return name[:100]  # Limit length


def memory_to_note_content(memory: MemoryOut, template: str | None = None) -> str:
    """Convert memory to markdown note content."""
    if template:
        try:
            return template.format(
                title=memory.title or "Untitled",
                content=memory.content,
                domain=memory.domain,
                entity_type=memory.entity_type,
                created_at=memory.created_at,
                updated_at=memory.updated_at,
                owner=memory.owner,
                tags=", ".join(memory.tags),
                id=memory.id,
                version=memory.version,
            )
        except Exception:
            # Fall back to default if template fails
            pass

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


def memory_to_frontmatter(memory: MemoryOut) -> dict[str, Any]:
    """Generate YAML frontmatter from memory metadata."""
    return {
        "title": memory.title,
        "openbrain_id": memory.id,
        "domain": memory.domain,
        "entity_type": memory.entity_type,
        "owner": memory.owner,
        "version": memory.version,
        "status": memory.status,
        "created_at": memory.created_at.isoformat() if hasattr(memory.created_at, 'isoformat') else str(memory.created_at),
        "updated_at": memory.updated_at.isoformat() if hasattr(memory.updated_at, 'isoformat') else str(memory.updated_at),
        "tags": memory.tags,
        "source": "openbrain-export",
    }


def build_collection_index(
    collection_name: str,
    query: str,
    exported: list[ObsidianExportItem],
    memories: list[MemoryOut],
    group_by: str | None,
) -> str:
    """Build markdown index for collection."""
    lines = [
        f"# {collection_name}",
        "",
        f"*Collection generated from OpenBrain — {len(exported)} items*",
        "",
        f"**Query:** `{query}`",
        "",
    ]

    if group_by and memories:
        lines.append(f"## Grouped by: {group_by}")
        lines.append("")
        
        # Group memories
        groups: dict[str, list[tuple[ObsidianExportItem, MemoryOut]]] = {}
        for exp in exported:
            mem = next((m for m in memories if m.id == exp.memory_id), None)
            if mem:
                if group_by == "entity_type":
                    key = mem.entity_type
                elif group_by == "owner":
                    key = mem.owner or "No owner"
                elif group_by == "tags":
                    key = mem.tags[0] if mem.tags else "Untagged"
                else:
                    key = "Other"
                groups.setdefault(key, []).append((exp, mem))
        
        # Output groups
        for key, items in sorted(groups.items()):
            lines.append(f"### {key}")
            lines.append("")
            for exp, mem in items:
                link_path = exp.path.replace('.md', '')
                lines.append(f"- [[{link_path}]] — {exp.title}")
            lines.append("")
    else:
        lines.append("## Items")
        lines.append("")
        for exp in exported:
            link_path = exp.path.replace('.md', '')
            lines.append(f"- [[{link_path}]] — {exp.title}")
        lines.append("")
    
    return "\n".join(lines)
