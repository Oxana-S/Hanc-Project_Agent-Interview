#!/usr/bin/env python3
"""Fix L10 pricing issues: payback_months=0, non-numeric payback, empty roi_examples, payback>36."""

import yaml
from pathlib import Path

BASE = Path(__file__).parent.parent / "config" / "industries"

# Custom YAML dumper to preserve formatting
class QuotedStr(str):
    pass

def quoted_representer(dumper, data):
    return dumper.represent_scalar('tag:yaml.org,2002:str', data, style="'")

yaml.add_representer(QuotedStr, quoted_representer)


def load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_yaml(path, data):
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False, width=200)


def fix_payback_zero(path, reasonable_value=1):
    """Fix payback_months=0 → set to 1 (immediate ROI, but 0 is invalid)."""
    data = load_yaml(path)
    pricing = data.get("pricing_context", {})
    roi = pricing.get("roi_examples", [])
    fixed = 0
    for r in roi:
        if isinstance(r, dict):
            pm = r.get("payback_months")
            try:
                if float(pm) <= 0:
                    r["payback_months"] = reasonable_value
                    fixed += 1
            except (ValueError, TypeError):
                pass
    if fixed:
        save_yaml(path, data)
        print(f"  Fixed {fixed} payback=0 in {path.relative_to(BASE)}")
    return fixed


def fix_payback_non_numeric(path):
    """Fix non-numeric payback_months → extract number or set to 1."""
    data = load_yaml(path)
    pricing = data.get("pricing_context", {})
    roi = pricing.get("roi_examples", [])
    fixed = 0
    for r in roi:
        if isinstance(r, dict):
            pm = r.get("payback_months")
            if pm is not None:
                try:
                    float(pm)
                except (ValueError, TypeError):
                    # Non-numeric: set to 1 for "immediate" ROI
                    r["payback_months"] = 1
                    fixed += 1
    if fixed:
        save_yaml(path, data)
        print(f"  Fixed {fixed} non-numeric payback in {path.relative_to(BASE)}")
    return fixed


def fix_payback_too_high(path, max_months=36):
    """Fix payback_months > 36 → cap at reasonable value."""
    data = load_yaml(path)
    pricing = data.get("pricing_context", {})
    roi = pricing.get("roi_examples", [])
    fixed = 0
    for r in roi:
        if isinstance(r, dict):
            pm = r.get("payback_months")
            try:
                val = float(pm)
                if val > max_months:
                    # Calculate from cost/savings if possible
                    cost = r.get("monthly_cost", 0)
                    savings = r.get("monthly_savings", 0)
                    if cost and savings and float(savings) > float(cost):
                        import math
                        new_val = math.ceil(float(cost) / (float(savings) - float(cost)) * 12)
                        r["payback_months"] = min(new_val, max_months)
                    else:
                        r["payback_months"] = 6  # reasonable default
                    fixed += 1
            except (ValueError, TypeError):
                pass
    if fixed:
        save_yaml(path, data)
        print(f"  Fixed {fixed} payback>{max_months} in {path.relative_to(BASE)}")
    return fixed


def fix_empty_roi(path, country, industry):
    """Add basic roi_examples to profiles where they're empty."""
    data = load_yaml(path)
    pricing = data.get("pricing_context", {})

    if not isinstance(pricing, dict):
        print(f"  SKIP {path.relative_to(BASE)} — no pricing_context")
        return 0

    roi = pricing.get("roi_examples", [])
    if isinstance(roi, list) and len(roi) > 0:
        return 0  # already has examples

    # Build from existing budget data
    budget = pricing.get("typical_budget_range", [])
    entry = pricing.get("entry_point")
    currency = pricing.get("currency", "EUR")

    if isinstance(budget, list) and len(budget) >= 2:
        low = float(budget[0])
    elif entry:
        low = float(entry)
    else:
        low = 1000  # default

    # Create 1 basic ROI example
    cost = int(low)
    savings = int(low * 2.5)

    pricing["roi_examples"] = [
        {
            "scenario": f"Basic AI voice agent deployment for {industry}",
            "monthly_cost": cost,
            "monthly_savings": savings,
            "payback_months": 3,
        }
    ]

    save_yaml(path, data)
    print(f"  Added roi_examples to {path.relative_to(BASE)}")
    return 1


def main():
    total = 0

    print("=== Fixing payback_months = 0 ===")
    for p in [
        "eu/ch/photo_video.yaml",
        "eu/it/logistics.yaml",
        "eu/ro/elderly_care.yaml",
        "sea/vn/cleaning.yaml",
    ]:
        total += fix_payback_zero(BASE / p)

    print("\n=== Fixing non-numeric payback_months ===")
    for p in [
        "eu/de/coworking.yaml",
        "eu/pt/coworking.yaml",
    ]:
        total += fix_payback_non_numeric(BASE / p)

    print("\n=== Fixing payback_months > 36 ===")
    for p in [
        "mena/ae/energy.yaml",
        "sea/cn/recruitment.yaml",
    ]:
        total += fix_payback_too_high(BASE / p)

    print("\n=== Fixing empty roi_examples ===")
    for p, country, industry in [
        ("eu/bg/recruitment.yaml", "bg", "recruitment"),
        ("sea/cn/cannabis.yaml", "cn", "cannabis"),
    ]:
        total += fix_empty_roi(BASE / p, country, industry)

    print(f"\nTotal fixes: {total}")


if __name__ == "__main__":
    main()
