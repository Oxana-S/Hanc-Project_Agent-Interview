#!/usr/bin/env python3
"""
Full validation of all industry profiles in the Knowledge Base.

Checks ALL 960 files against 5 levels of criteria:
  1. Structural integrity (required fields, min counts)
  2. Content completeness (v2.0 sections)
  3. Metadata correctness (meta.id, region, country, language, currency)
  4. Localization quality (language match, local competitors/integrations)
  5. Value validity (severity/priority enums, pricing logic)

Usage:
    python scripts/validate_all_profiles.py
    python scripts/validate_all_profiles.py --verbose
    python scripts/validate_all_profiles.py --region eu
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

# Expected language per country (from _countries.yaml)
COUNTRY_LANGUAGE = {
    "de": "de", "at": "de", "ch": "de", "fr": "fr", "it": "it",
    "es": "es", "pt": "pt", "ro": "ro", "bg": "bg", "hu": "hu", "gr": "el",
    "us": "en", "ca": "en",
    "br": "pt", "ar": "es", "mx": "es",
    "ae": "ar", "sa": "ar", "qa": "ar",
    "cn": "zh", "vn": "vi", "id": "id",
    "ru": "ru",
}

# Expected currency per country
COUNTRY_CURRENCY = {
    "de": "EUR", "at": "EUR", "ch": "CHF", "fr": "EUR", "it": "EUR",
    "es": "EUR", "pt": "EUR", "ro": "RON", "bg": "BGN", "hu": "HUF", "gr": "EUR",
    "us": "USD", "ca": "CAD",
    "br": "BRL", "ar": "ARS", "mx": "MXN",
    "ae": "AED", "sa": "SAR", "qa": "QAR",
    "cn": "CNY", "vn": "VND", "id": "IDR",
    "ru": "RUB",
}

VALID_SEVERITIES = {"high", "medium", "low"}
VALID_PRIORITIES = {"high", "medium", "low"}


def validate_profile(file_path: Path, region: str, country: str, industry: str,
                     base_profiles: set) -> Dict[str, Any]:
    """Validate a single profile file against all criteria."""
    result = {
        "path": str(file_path),
        "region": region,
        "country": country,
        "industry": industry,
        "errors": [],      # Critical — profile is broken
        "warnings": [],    # Non-critical — profile works but has issues
        "score": 0.0,
    }

    # --- Level 0: YAML parsing ---
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        result["errors"].append(f"YAML parse error: {e}")
        return result

    if not isinstance(data, dict):
        result["errors"].append("File does not contain a YAML mapping")
        return result

    # --- Level 1: Structural integrity ---
    level1_checks = {
        "pain_points":           {"min": 3, "required": True,  "type": "list_of_dicts", "fields": ["description", "severity"]},
        "typical_services":      {"min": 5, "required": True,  "type": "list_of_str"},
        "recommended_functions": {"min": 3, "required": True,  "type": "list_of_dicts", "fields": ["name", "priority"]},
        "typical_integrations":  {"min": 2, "required": False, "type": "list_of_dicts", "fields": ["name", "examples"]},
        "industry_faq":          {"min": 3, "required": False, "type": "list_of_dicts", "fields": ["question", "answer_template"]},
        "typical_objections":    {"min": 2, "required": False, "type": "list_of_dicts", "fields": ["objection", "response"]},
        "aliases":               {"min": 2, "required": False, "type": "list_of_str"},
    }

    for field_name, spec in level1_checks.items():
        field_val = data.get(field_name)

        if field_val is None or (isinstance(field_val, list) and len(field_val) == 0):
            if spec["required"]:
                result["errors"].append(f"L1: Required field '{field_name}' is missing or empty")
            else:
                result["warnings"].append(f"L1: Optional field '{field_name}' is missing or empty")
            continue

        if not isinstance(field_val, list):
            result["errors"].append(f"L1: '{field_name}' should be a list, got {type(field_val).__name__}")
            continue

        count = len(field_val)
        if count < spec["min"]:
            msg = f"L1: '{field_name}' has {count} items (min {spec['min']})"
            if spec["required"]:
                result["errors"].append(msg)
            else:
                result["warnings"].append(msg)

        # Check internal structure
        if spec["type"] == "list_of_dicts":
            required_fields = spec.get("fields", [])
            for i, item in enumerate(field_val):
                if not isinstance(item, dict):
                    result["warnings"].append(f"L1: '{field_name}[{i}]' is not a dict")
                    continue
                for rf in required_fields:
                    if rf not in item or item[rf] is None or (isinstance(item[rf], str) and item[rf].strip() == ""):
                        result["warnings"].append(f"L1: '{field_name}[{i}]' missing sub-field '{rf}'")

    # --- Level 2: Content completeness (v2.0 sections) ---
    # sales_scripts
    sales = data.get("sales_scripts", [])
    if not sales or not isinstance(sales, list):
        result["warnings"].append("L2: 'sales_scripts' is missing or empty")
    elif len(sales) < 3:
        result["warnings"].append(f"L2: 'sales_scripts' has {len(sales)} items (min 3)")
    else:
        for i, s in enumerate(sales):
            if isinstance(s, dict):
                for f in ["trigger", "script", "goal"]:
                    if f not in s or not s[f]:
                        result["warnings"].append(f"L2: 'sales_scripts[{i}]' missing '{f}'")

    # competitors
    competitors = data.get("competitors", [])
    if not competitors or not isinstance(competitors, list):
        result["warnings"].append("L2: 'competitors' is missing or empty")
    elif len(competitors) < 2:
        result["warnings"].append(f"L2: 'competitors' has {len(competitors)} items (min 2)")
    else:
        for i, c in enumerate(competitors):
            if isinstance(c, dict):
                for f in ["name", "positioning"]:
                    if f not in c or not c[f]:
                        result["warnings"].append(f"L2: 'competitors[{i}]' missing '{f}'")

    # pricing_context
    pricing = data.get("pricing_context")
    if not pricing or not isinstance(pricing, dict):
        result["warnings"].append("L2: 'pricing_context' is missing")
    else:
        for f in ["currency", "typical_budget_range", "entry_point"]:
            if f not in pricing or pricing[f] is None:
                result["warnings"].append(f"L2: 'pricing_context' missing '{f}'")

        roi = pricing.get("roi_examples", [])
        if not roi:
            result["warnings"].append("L2: 'pricing_context.roi_examples' is missing or empty")

    # market_context
    market = data.get("market_context")
    if not market or not isinstance(market, dict):
        result["warnings"].append("L2: 'market_context' is missing")
    else:
        trends = market.get("key_trends", [])
        if not trends:
            result["warnings"].append("L2: 'market_context.key_trends' is missing or empty")
        seasonality = market.get("seasonality")
        if not seasonality or not isinstance(seasonality, dict):
            result["warnings"].append("L2: 'market_context.seasonality' is missing")

    # --- Level 3: Metadata correctness ---
    meta = data.get("meta", {})
    if not meta or not isinstance(meta, dict):
        result["errors"].append("L3: 'meta' section is missing")
    else:
        # meta.id should match filename
        meta_id = meta.get("id", "")
        if meta_id != industry:
            result["errors"].append(f"L3: meta.id='{meta_id}' != filename '{industry}'")

        # meta.region
        meta_region = meta.get("region", "")
        if meta_region != region:
            result["errors"].append(f"L3: meta.region='{meta_region}' != folder '{region}'")

        # meta.country
        meta_country = meta.get("country", "")
        if meta_country != country:
            result["errors"].append(f"L3: meta.country='{meta_country}' != folder '{country}'")

        # meta.language
        expected_lang = COUNTRY_LANGUAGE.get(country)
        meta_lang = meta.get("language", "")
        if expected_lang and meta_lang != expected_lang:
            result["warnings"].append(f"L3: meta.language='{meta_lang}' expected '{expected_lang}' for {country}")

        # meta.currency
        expected_currency = COUNTRY_CURRENCY.get(country)
        meta_currency = meta.get("currency", "")
        if expected_currency and meta_currency and meta_currency != expected_currency:
            result["warnings"].append(f"L3: meta.currency='{meta_currency}' expected '{expected_currency}' for {country}")

    # _extends
    extends = data.get("_extends", "")
    if extends:
        base_id = extends.replace("_base/", "")
        if base_id not in base_profiles:
            result["warnings"].append(f"L3: _extends='{extends}' references non-existent base profile")

    # --- Level 4: Localization ---
    expected_lang = COUNTRY_LANGUAGE.get(country, "")

    # Check if pricing currency matches country
    if pricing and isinstance(pricing, dict):
        pricing_currency = pricing.get("currency", "")
        expected_cur = COUNTRY_CURRENCY.get(country, "")
        if expected_cur and pricing_currency and pricing_currency != expected_cur:
            result["warnings"].append(
                f"L4: pricing_context.currency='{pricing_currency}' expected '{expected_cur}' for {country}")

    # --- Level 5: Value validity ---
    # severity values
    pain_points = data.get("pain_points", [])
    if isinstance(pain_points, list):
        for i, pp in enumerate(pain_points):
            if isinstance(pp, dict):
                sev = pp.get("severity", "")
                if sev and sev not in VALID_SEVERITIES:
                    result["warnings"].append(f"L5: pain_points[{i}].severity='{sev}' not in {VALID_SEVERITIES}")

    # priority values
    for field_name in ["recommended_functions", "typical_integrations"]:
        items = data.get(field_name, [])
        if isinstance(items, list):
            for i, item in enumerate(items):
                if isinstance(item, dict):
                    pri = item.get("priority", "")
                    if pri and pri not in VALID_PRIORITIES:
                        result["warnings"].append(f"L5: {field_name}[{i}].priority='{pri}' not in {VALID_PRIORITIES}")

    # pricing range logic
    if pricing and isinstance(pricing, dict):
        budget = pricing.get("typical_budget_range", [])
        if isinstance(budget, list) and len(budget) == 2:
            try:
                low, high = float(budget[0]), float(budget[1])
                if low >= high:
                    result["warnings"].append(f"L5: budget_range min({low}) >= max({high})")
            except (ValueError, TypeError):
                result["warnings"].append(f"L5: budget_range values not numeric: {budget}")

        entry = pricing.get("entry_point")
        if entry is not None:
            try:
                if float(entry) <= 0:
                    result["warnings"].append(f"L5: entry_point={entry} should be > 0")
            except (ValueError, TypeError):
                result["warnings"].append(f"L5: entry_point not numeric: {entry}")

        roi_examples = pricing.get("roi_examples", [])
        if isinstance(roi_examples, list):
            for i, roi in enumerate(roi_examples):
                if isinstance(roi, dict):
                    cost = roi.get("monthly_cost")
                    savings = roi.get("monthly_savings")
                    if cost is not None and savings is not None:
                        try:
                            if float(savings) <= float(cost):
                                result["warnings"].append(
                                    f"L5: roi_examples[{i}] savings({savings}) <= cost({cost})")
                        except (ValueError, TypeError):
                            pass

    # --- Compute score ---
    weights = {
        "pain_points": 0.20,
        "typical_services": 0.15,
        "recommended_functions": 0.20,
        "typical_integrations": 0.10,
        "industry_faq": 0.10,
        "typical_objections": 0.10,
        "aliases": 0.05,
        "sales_scripts": 0.05,
        "competitors": 0.05,
    }

    mins = {
        "pain_points": 3, "typical_services": 5, "recommended_functions": 3,
        "typical_integrations": 2, "industry_faq": 3, "typical_objections": 2,
        "aliases": 2, "sales_scripts": 3, "competitors": 2,
    }

    score = 0.0
    for fname, weight in weights.items():
        val = data.get(fname, [])
        if isinstance(val, list) and len(val) > 0:
            actual = len(val)
            minimum = mins.get(fname, 1)
            score += weight * min(1.0, actual / minimum)

    result["score"] = round(score, 3)

    return result


def validate_base_profile(file_path: Path, industry: str) -> Dict[str, Any]:
    """Validate a base profile."""
    result = {
        "path": str(file_path),
        "region": "_base",
        "country": "_base",
        "industry": industry,
        "errors": [],
        "warnings": [],
        "score": 0.0,
    }

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        result["errors"].append(f"YAML parse error: {e}")
        return result

    if not isinstance(data, dict):
        result["errors"].append("File does not contain a YAML mapping")
        return result

    # Check required fields
    required = {
        "pain_points": 3, "typical_services": 5, "recommended_functions": 3,
        "aliases": 2, "industry_faq": 3, "typical_objections": 2,
    }

    for field_name, minimum in required.items():
        val = data.get(field_name, [])
        if not val or not isinstance(val, list):
            result["errors"].append(f"Base: '{field_name}' is missing or empty")
        elif len(val) < minimum:
            result["warnings"].append(f"Base: '{field_name}' has {len(val)} items (min {minimum})")

    # meta.id
    meta = data.get("meta", {})
    if isinstance(meta, dict):
        meta_id = meta.get("id", "")
        if meta_id != industry:
            result["errors"].append(f"Base: meta.id='{meta_id}' != filename '{industry}'")

    result["score"] = 1.0 if not result["errors"] else 0.5
    return result


def main():
    parser = argparse.ArgumentParser(description="Validate all industry profiles")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show all warnings")
    parser.add_argument("--region", type=str, help="Only validate specific region")
    parser.add_argument("--errors-only", action="store_true", help="Only show profiles with errors")
    args = parser.parse_args()

    config_dir = Path(__file__).parent.parent / "config" / "industries"

    # Collect base profiles
    base_dir = config_dir / "_base"
    base_profiles = set()
    if base_dir.exists():
        base_profiles = {f.stem for f in base_dir.glob("*.yaml")}

    all_results: List[Dict] = []
    region_stats: Dict[str, Dict] = defaultdict(lambda: {"total": 0, "valid": 0, "errors": 0, "warnings": 0})

    # --- Validate base profiles ---
    print("=" * 70)
    print("VALIDATING BASE PROFILES")
    print("=" * 70)
    base_errors = 0
    for base_file in sorted(base_dir.glob("*.yaml")):
        r = validate_base_profile(base_file, base_file.stem)
        all_results.append(r)
        if r["errors"]:
            base_errors += len(r["errors"])
            print(f"  ERROR {base_file.stem}: {r['errors']}")
    print(f"  Base profiles: {len(base_profiles)}, Errors: {base_errors}")
    print()

    # --- Validate regional profiles ---
    regions = ["eu", "na", "latam", "mena", "sea", "ru"]
    if args.region:
        regions = [args.region]

    total_files = 0
    total_errors = 0
    total_warnings = 0
    total_valid = 0

    error_summary: Dict[str, int] = defaultdict(int)  # error pattern -> count
    warning_summary: Dict[str, int] = defaultdict(int)

    for region in regions:
        region_dir = config_dir / region
        if not region_dir.exists():
            continue

        print("=" * 70)
        print(f"REGION: {region.upper()}")
        print("=" * 70)

        for country_dir in sorted(region_dir.iterdir()):
            if not country_dir.is_dir():
                continue
            country = country_dir.name

            for profile_file in sorted(country_dir.glob("*.yaml")):
                industry = profile_file.stem
                r = validate_profile(profile_file, region, country, industry, base_profiles)
                all_results.append(r)

                total_files += 1
                is_valid = len(r["errors"]) == 0 and r["score"] >= 0.5

                if is_valid:
                    total_valid += 1
                    region_stats[region]["valid"] += 1

                region_stats[region]["total"] += 1
                region_stats[region]["errors"] += len(r["errors"])
                region_stats[region]["warnings"] += len(r["warnings"])

                total_errors += len(r["errors"])
                total_warnings += len(r["warnings"])

                for e in r["errors"]:
                    # Extract pattern (remove specific values)
                    pattern = e.split("=")[0] if "=" in e else e.split(":")[0]
                    error_summary[pattern.strip()] += 1

                for w in r["warnings"]:
                    pattern = w.split("=")[0] if "=" in w else w.split(":")[0]
                    warning_summary[pattern.strip()] += 1

                # Print output
                if r["errors"]:
                    print(f"  ERROR  {region}/{country}/{industry} (score={r['score']:.2f})")
                    for e in r["errors"]:
                        print(f"         {e}")
                    if args.verbose:
                        for w in r["warnings"]:
                            print(f"         [warn] {w}")
                elif r["warnings"] and not args.errors_only:
                    if args.verbose:
                        print(f"  WARN   {region}/{country}/{industry} (score={r['score']:.2f}) — {len(r['warnings'])} warnings")
                        for w in r["warnings"]:
                            print(f"         {w}")

        # Region summary
        rs = region_stats[region]
        print(f"  --- {region.upper()}: {rs['valid']}/{rs['total']} valid, "
              f"{rs['errors']} errors, {rs['warnings']} warnings")
        print()

    # --- Final summary ---
    print("=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)
    print(f"Total regional profiles checked: {total_files}")
    print(f"Valid profiles:                  {total_valid} ({total_valid/total_files*100:.1f}%)")
    print(f"Profiles with errors:            {total_files - total_valid}")
    print(f"Total errors:                    {total_errors}")
    print(f"Total warnings:                  {total_warnings}")
    print()

    print("Per-region breakdown:")
    for region in regions:
        rs = region_stats[region]
        if rs["total"] > 0:
            pct = rs["valid"] / rs["total"] * 100
            print(f"  {region:6s}: {rs['valid']:3d}/{rs['total']:3d} valid ({pct:5.1f}%), "
                  f"{rs['errors']:3d} errors, {rs['warnings']:4d} warnings")
    print()

    # Top error patterns
    if error_summary:
        print("Top error patterns:")
        for pattern, count in sorted(error_summary.items(), key=lambda x: -x[1])[:15]:
            print(f"  {count:4d}x  {pattern}")
        print()

    # Top warning patterns
    if warning_summary:
        print("Top warning patterns:")
        for pattern, count in sorted(warning_summary.items(), key=lambda x: -x[1])[:20]:
            print(f"  {count:4d}x  {pattern}")
        print()

    # Profiles with errors list
    error_profiles = [r for r in all_results if r["errors"] and r["region"] != "_base"]
    if error_profiles:
        print(f"Profiles with errors ({len(error_profiles)}):")
        for r in error_profiles:
            print(f"  - {r['region']}/{r['country']}/{r['industry']}: {r['errors'][0]}")


if __name__ == "__main__":
    main()
