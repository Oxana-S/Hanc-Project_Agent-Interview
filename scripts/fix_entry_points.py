#!/usr/bin/env python3
"""Fix non-numeric entry_point values by extracting the number."""

import re
import yaml
from pathlib import Path

BASE = Path(__file__).parent.parent / "config" / "industries"


def extract_number(value) -> int:
    """Extract numeric value from a string like '150 CHF', '$65', 'CHF 250', '5-7 BGN'."""
    s = str(value).strip()

    # Already numeric
    try:
        n = float(s)
        return max(int(n), 1)  # Ensure > 0
    except (ValueError, TypeError):
        pass

    # Remove currency symbols and common prefixes
    s = re.sub(r'[$€£¥₹]', '', s)
    s = re.sub(r'^(Ab|от|От|Da|Desde|De la)\s+', '', s, flags=re.IGNORECASE)

    # Find all numbers (handle comma as thousand separator)
    numbers = re.findall(r'[\d,]+(?:\.\d+)?', s.replace(' ', ''))
    if numbers:
        # Take the first number, remove commas
        n_str = numbers[0].replace(',', '')
        try:
            return max(int(float(n_str)), 1)
        except ValueError:
            pass

    # For ranges like "5-7", take the lower bound
    range_match = re.match(r'(\d+)\s*[-–]\s*(\d+)', s)
    if range_match:
        return int(range_match.group(1))

    return None


def fix_all():
    total = 0
    for path in sorted(BASE.rglob("*.yaml")):
        if "/_base/" in str(path) or "_index" in path.name or "_countries" in path.name:
            continue

        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read()
            data = yaml.safe_load(raw)
        except Exception:
            continue

        if not isinstance(data, dict):
            continue

        pricing = data.get("pricing_context", {})
        if not isinstance(pricing, dict):
            continue

        entry = pricing.get("entry_point")
        if entry is None:
            continue

        # Check if already numeric
        try:
            val = float(entry)
            if val <= 0:
                # Fix zero entry_point — use budget_range low if available
                budget = pricing.get("typical_budget_range", [])
                if isinstance(budget, list) and len(budget) >= 2:
                    pricing["entry_point"] = int(float(budget[0]))
                else:
                    pricing["entry_point"] = 100  # reasonable minimum
                with open(path, "w", encoding="utf-8") as f:
                    yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False, width=200)
                rel = path.relative_to(BASE)
                print(f"  Fixed entry_point=0 → {pricing['entry_point']} in {rel}")
                total += 1
            continue
        except (ValueError, TypeError):
            pass

        # Non-numeric — extract number
        extracted = extract_number(entry)
        if extracted:
            pricing["entry_point"] = extracted
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False, width=200)
            rel = path.relative_to(BASE)
            print(f"  Fixed '{entry}' → {extracted} in {rel}")
            total += 1
        else:
            rel = path.relative_to(BASE)
            print(f"  COULD NOT FIX: '{entry}' in {rel}")

    print(f"\nTotal fixed: {total}")


if __name__ == "__main__":
    fix_all()
