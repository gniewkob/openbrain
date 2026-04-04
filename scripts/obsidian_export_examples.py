#!/usr/bin/env python3
"""
Example exports to Obsidian using OpenBrain.
Run with: python scripts/obsidian_export_examples.py

Prerequisites:
1. Set OBSIDIAN_VAULT_PATHS in .env
2. OpenBrain must be running
3. Obsidian vault must be accessible
"""

import asyncio
import os
import sys

# Add unified/src to path
sys.path.insert(0, "unified/src")

# Load .env
with open(".env", "r") as f:
    for line in f:
        if "=" in line and not line.startswith("#"):
            key, value = line.strip().split("=", 1)
            os.environ[key] = value


async def example_1_weekly_decisions():
    """
    Example 1: Create a weekly collection of decisions.
    This creates an index note with links to all decisions from last week.
    """
    print("=== Example 1: Weekly Decisions Collection ===\n")
    
    from datetime import datetime, timedelta
    
    last_week = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    
    query = f"decision created:>{last_week}"
    collection_name = f"Decisions {datetime.now().strftime('%Y-W%U')}"
    
    print(f"Query: {query}")
    print(f"Collection: {collection_name}")
    print(f"Target: Memory/04 Projects/OpenBrain/{collection_name}/")
    print()
    print("This would create:")
    print("  - Index.md with links to all decisions")
    print("  - Individual .md files for each decision")
    print("  - Grouped by entity_type (Decision, Risk, Architecture)")


async def example_2_security_research():
    """
    Example 2: Export all security-related memories.
    Creates a knowledge base in 02 Memory.
    """
    print("\n=== Example 2: Security Knowledge Base ===\n")
    
    print("Exporting: security, authentication, authorization topics")
    print("Target: Memory/02 Memory/OpenBrain/Security/")
    print()
    print("Structure:")
    print("  📂 Security/")
    print("    ├── Authentication/")
    print("    │   ├── Auth0 Integration.md")
    print("    │   ├── JWT Best Practices.md")
    print("    │   └── OAuth2 Implementation.md")
    print("    ├── Authorization/")
    print("    │   └── RBAC Design.md")
    print("    └── Architecture/")
    print("        └── Security Layer.md")


async def example_3_project_documentation():
    """
    Example 3: Export all memories related to a specific project.
    """
    print("\n=== Example 3: Project Documentation ===\n")
    
    print("Query: 'openbrain' (all memories about OpenBrain project)")
    print("Target: Memory/04 Projects/OpenBrain/")
    print()
    print("This would export:")
    print("  - Architecture decisions")
    print("  - Technical designs")
    print("  - Meeting notes")
    print("  - Risk assessments")
    print()
    print("And create:")
    print("  📂 OpenBrain/")
    print("    ├── Index.md (main project overview)")
    print("    ├── Architecture/")
    print("    ├── Decisions/")
    print("    └── Meetings/")


async def example_4_meeting_archive():
    """
    Example 4: Archive meetings from last month.
    """
    print("\n=== Example 4: Monthly Meeting Archive ===\n")
    
    print("Query: 'meeting 2026-03'")
    print("Target: Memory/07 Archive/Meetings/2026-03/")
    print()
    print("Creates:")
    print("  📂 2026-03/")
    print("    ├── Index.md (list of all March meetings)")
    print("    ├── 2026-03-01 Team Standup.md")
    print("    ├── 2026-03-05 Sprint Planning.md")
    print("    └── ...")


async def print_config():
    """Print current configuration."""
    print("=== Current Configuration ===\n")
    
    from common.obsidian_adapter import ObsidianCliAdapter
    
    adapter = ObsidianCliAdapter()
    
    # Test Memory vault
    path = adapter._get_vault_path("Memory")
    if path:
        print(f"✅ Memory vault: {path}")
        from pathlib import Path
        if Path(path).exists():
            print("   Status: Accessible")
            # Show folder structure
            para_folders = ["00 Inbox", "02 Memory", "04 Projects", "07 Archive"]
            found = [f for f in para_folders if (Path(path) / f).exists()]
            print(f"   PARA folders: {', '.join(found)}")
    else:
        print("❌ Memory vault not configured")
    
    print()


async def main():
    """Run all examples."""
    await print_config()
    
    await example_1_weekly_decisions()
    await example_2_security_research()
    await example_3_project_documentation()
    await example_4_meeting_archive()
    
    print("\n" + "=" * 60)
    print("To actually run these exports:")
    print("  1. Start OpenBrain: ./start_unified.sh start")
    print("  2. Use MCP tools or REST API to trigger exports")
    print("  3. Check your Obsidian vault for new notes!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
