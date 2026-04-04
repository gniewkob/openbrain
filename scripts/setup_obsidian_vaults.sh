#!/bin/bash
# Setup Obsidian vaults for OpenBrain export
# Usage: source scripts/setup_obsidian_vaults.sh

echo "=== OpenBrain Obsidian Vault Setup ==="
echo ""

# Check if running from project root
if [ ! -f ".env" ]; then
    echo "❌ Error: Run this script from project root directory"
    exit 1
fi

# Source the .env file
export $(grep -v '^#' .env | grep OBSIDIAN | xargs)

# Test configuration
echo "Testing Obsidian vault configuration..."
echo ""

if [ -z "$OBSIDIAN_VAULT_PATHS" ]; then
    echo "⚠️  OBSIDIAN_VAULT_PATHS not set in .env"
    echo "   Add this line to .env:"
    echo '   OBSIDIAN_VAULT_PATHS={"Memory":"/path/to/vault"}'
    exit 1
fi

echo "✅ OBSIDIAN_VAULT_PATHS is set"
echo "   Value: $OBSIDIAN_VAULT_PATHS"
echo ""

# Parse and check vaults
echo "Configured vaults:"
echo "$OBSIDIAN_VAULT_PATHS" | python3 -c "
import json, sys, os
from pathlib import Path

vaults = json.load(sys.stdin)
for name, path in vaults.items():
    print(f'  📁 {name}:')
    print(f'     Path: {path}')
    expanded = os.path.expanduser(path)
    if Path(expanded).exists():
        print(f'     Status: ✅ Accessible')
        # Count markdown files
        md_count = len(list(Path(expanded).glob('**/*.md')))
        print(f'     Markdown files: {md_count}')
    else:
        print(f'     Status: ⚠️  Not accessible (may need iCloud sync)')
    print()
" 2>/dev/null || echo "   (Install Python to verify paths)"

echo ""
echo "=== Recommended folder structure ==="
echo "For PARA method users:"
echo "  📂 00 Inbox/OpenBrain/        - Temporary notes"
echo "  📂 02 Memory/OpenBrain/       - Knowledge base exports"
echo "  📂 04 Projects/OpenBrain/     - Project-related memories"
echo "  📂 05 Areas/OpenBrain/        - Area collections"
echo "  📂 07 Archive/OpenBrain/      - Archived exports"
echo ""
echo "Example usage:"
echo '  brain_obsidian_export(vault="Memory", folder="02 Memory/OpenBrain/Security")'
