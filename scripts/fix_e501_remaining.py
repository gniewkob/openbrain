#!/usr/bin/env python3
"""Script to help fix remaining E501 errors (line too long).

This script identifies remaining E501 errors and provides guidance on fixing them.
Run this after the main refactoring is complete.
"""

import subprocess
import sys


def get_e501_errors():
    """Get list of files with E501 errors."""
    result = subprocess.run(
        ["ruff", "check", "src/", "--select=E501"],
        capture_output=True,
        text=True,
        cwd="unified"
    )
    return result.stdout


def count_errors_by_file():
    """Count E501 errors by file."""
    output = get_e501_errors()
    files = {}
    
    for line in output.split("\n"):
        if "src/" in line and ":" in line:
            file_path = line.split("src/")[-1].split(":")[0]
            files[file_path] = files.get(file_path, 0) + 1
    
    return files


def main():
    print("=" * 70)
    print("REMAINING E501 ERRORS (Line too long)")
    print("=" * 70)
    
    files = count_errors_by_file()
    total = sum(files.values())
    
    print(f"\nTotal E501 errors: {total}\n")
    print("Breakdown by file:")
    print("-" * 50)
    
    for file_path, count in sorted(files.items(), key=lambda x: -x[1]):
        print(f"  {count:2d} errors: src/{file_path}")
    
    print("\n" + "=" * 70)
    print("HOW TO FIX")
    print("=" * 70)
    print("""
1. For long strings, break them into multiple lines:
   
   BEFORE:
   detail="This is a very long string that exceeds 88 characters limit"
   
   AFTER:
   detail=(
       "This is a very long string that exceeds "
       "88 characters limit"
   )

2. For f-strings with variables:
   
   BEFORE:
   detail=f"User {user_id} has done something with {object_name}"
   
   AFTER:
   detail=(
       f"User {user_id} has done something "
       f"with {object_name}"
   )

3. For comments, break into multiple comment lines:
   
   BEFORE:
   # This is a very long comment explaining something complex
   
   AFTER:
   # This is a very long comment explaining
   # something complex

4. Run this script again to verify progress:
   
   python scripts/fix_e501_remaining.py
""")
    
    print("=" * 70)
    print("QUICK FIX COMMAND")
    print("=" * 70)
    print("\nTo see all remaining E501 errors:\n")
    print("  cd unified && ruff check src/ --select=E501")
    print()


if __name__ == "__main__":
    main()
