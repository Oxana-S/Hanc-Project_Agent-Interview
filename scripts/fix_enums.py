#!/usr/bin/env python3
"""Fix localized severity/priority enum values → normalize to English (high/medium/low)."""

import glob
import re
import sys

ENUM_MAP = {
    # German
    "hoch": "high",
    "mittel": "medium",
    "niedrig": "low",
    # Spanish
    "alta": "high",
    "alto": "high",
    "media": "medium",
    "medio": "medium",
    "baja": "low",
    "bajo": "low",
    # Italian
    "bassa": "low",
    # Arabic
    "عالي": "high",
    "عالية": "high",
    "متوسط": "medium",
    "متوسطة": "medium",
    "منخفض": "low",
    "منخفضة": "low",
    # Chinese
    "高": "high",
    "中": "medium",
    "低": "low",
    # Indonesian
    "tinggi": "high",
    "sedang": "medium",
    "rendah": "low",
    # Portuguese
    "alta": "high",  # same as Spanish
    "média": "medium",
    "baixa": "low",
    "baixo": "low",
}

# Regex pattern: match severity: or priority: followed by a localized value
FIELDS = ["severity", "priority"]


def fix_file(path: str, dry_run: bool = False) -> int:
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    original = content
    fixes = 0

    for field in FIELDS:
        for local_val, eng_val in ENUM_MAP.items():
            # Match "field: local_val" at various positions
            # Handle both quoted and unquoted values
            pattern = rf"({field}:\s*)({re.escape(local_val)})(\s*$)"
            replacement = rf"\g<1>{eng_val}\3"
            new_content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
            if new_content != content:
                count = len(re.findall(pattern, content, flags=re.MULTILINE))
                fixes += count
                content = new_content

            # Also handle quoted values
            pattern_q = rf'({field}:\s*")({re.escape(local_val)})(")'
            replacement_q = rf"\g<1>{eng_val}\3"
            new_content = re.sub(pattern_q, replacement_q, content)
            if new_content != content:
                count = len(re.findall(pattern_q, content))
                fixes += count
                content = new_content

    if content != original and not dry_run:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    return fixes


def main():
    dry_run = "--dry-run" in sys.argv
    base_dir = "config/industries"
    files = sorted(glob.glob(f"{base_dir}/**/*.yaml", recursive=True))

    total_fixes = 0
    fixed_files = 0

    for path in files:
        if "/_base/" in path or "_index" in path or "_countries" in path:
            continue
        fixes = fix_file(path, dry_run=dry_run)
        if fixes > 0:
            total_fixes += fixes
            fixed_files += 1
            action = "would fix" if dry_run else "fixed"
            print(f"  {action} {fixes} enums in {path}")

    print(f"\nTotal: {total_fixes} enum values {'would be ' if dry_run else ''}fixed in {fixed_files} files")


if __name__ == "__main__":
    main()
