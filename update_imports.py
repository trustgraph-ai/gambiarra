#!/usr/bin/env python3
"""
Script to update all imports from old structure to new package structure.
"""

import os
import re
from pathlib import Path

def update_imports_in_file(file_path: Path) -> bool:
    """Update imports in a single file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        original_content = content

        # Update client imports
        content = re.sub(r'^from client\.', 'from gambiarra.client.', content, flags=re.MULTILINE)
        content = re.sub(r'^import client\.', 'import gambiarra.client.', content, flags=re.MULTILINE)

        # Update server imports
        content = re.sub(r'^from server\.', 'from gambiarra.server.', content, flags=re.MULTILINE)
        content = re.sub(r'^import server\.', 'import gambiarra.server.', content, flags=re.MULTILINE)

        # Update test-llm imports (if any)
        content = re.sub(r'^from test_llm\.', 'from gambiarra.test_llm.', content, flags=re.MULTILINE)
        content = re.sub(r'^import test_llm\.', 'import gambiarra.test_llm.', content, flags=re.MULTILINE)

        # If content changed, write it back
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Updated: {file_path}")
            return True

        return False

    except Exception as e:
        print(f"Error updating {file_path}: {e}")
        return False

def main():
    """Update all imports in the gambiarra package."""
    gambiarra_dir = Path("gambiarra")
    tests_dir = Path("tests")

    updated_count = 0

    # Process all Python files in the package
    for directory in [gambiarra_dir, tests_dir]:
        if directory.exists():
            for py_file in directory.rglob("*.py"):
                if update_imports_in_file(py_file):
                    updated_count += 1

    print(f"Updated imports in {updated_count} files")

if __name__ == "__main__":
    main()