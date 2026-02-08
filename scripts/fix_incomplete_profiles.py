#!/usr/bin/env python3
"""
Fix incomplete profiles — regenerate missing sections via LLM.

Handles two categories:
- P2: Critical errors (missing typical_services / recommended_functions)
- P5: Missing v2.0 sections (sales_scripts, competitors, pricing_context, market_context)

Usage:
    python scripts/fix_incomplete_profiles.py --dry-run
    python scripts/fix_incomplete_profiles.py --provider azure
    python scripts/fix_incomplete_profiles.py --p2-only
    python scripts/fix_incomplete_profiles.py --region eu --limit 10
"""

import argparse
import asyncio
import glob
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
import structlog

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.llm.factory import create_llm_client
from src.knowledge.country_detector import CountryDetector

logger = structlog.get_logger("fix_profiles")


# Required sections and their minimum items
REQUIRED_SECTIONS = {
    "typical_services": 5,
    "recommended_functions": 3,
}

V2_SECTIONS = ["sales_scripts", "competitors", "pricing_context", "market_context"]


def get_country_meta(country: str) -> dict:
    """Get country metadata."""
    detector = CountryDetector()
    meta = detector.get_country_meta(country)
    if meta:
        return meta
    return {"name": country.upper(), "language": "en", "currency": "USD"}


def find_incomplete_profiles(base_dir: str) -> List[dict]:
    """Find profiles with missing sections."""
    results = []

    for path in sorted(glob.glob(f"{base_dir}/**/*.yaml", recursive=True)):
        if "/_base/" in path or "_index" in path or "_countries" in path:
            continue

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except yaml.YAMLError:
            continue

        # Determine region/country/industry from path
        rel = Path(path).relative_to(base_dir)
        parts = list(rel.parts)
        if len(parts) < 3:
            continue

        region = parts[0]
        country = parts[1]
        industry = parts[2].replace(".yaml", "")

        missing = []

        # Check required sections (P2)
        for section, min_items in REQUIRED_SECTIONS.items():
            val = data.get(section)
            if not val or (isinstance(val, list) and len(val) < min_items):
                missing.append(section)

        # Check v2.0 sections (P5)
        for section in V2_SECTIONS:
            val = data.get(section)
            if val is None or (isinstance(val, list) and len(val) == 0):
                missing.append(section)
            elif isinstance(val, dict) and not val:
                missing.append(section)

        if missing:
            results.append({
                "path": path,
                "region": region,
                "country": country,
                "industry": industry,
                "missing": missing,
                "data": data,
            })

    return results


def build_enrichment_prompt(
    industry: str,
    country: str,
    region: str,
    country_meta: dict,
    existing_data: dict,
    missing_sections: List[str],
) -> str:
    """Build prompt to generate only the missing sections."""
    language = country_meta.get("language", "en")
    country_name = country_meta.get("name", country.upper())
    currency = country_meta.get("currency", "EUR")
    compliance = country_meta.get("compliance", [])

    # Show existing context (abbreviated)
    context_keys = ["pain_points", "typical_services", "recommended_functions",
                    "typical_integrations", "industry_faq"]
    existing_context = {}
    for k in context_keys:
        val = existing_data.get(k)
        if val:
            if isinstance(val, list) and len(val) > 3:
                existing_context[k] = val[:3]  # Abbreviate
            else:
                existing_context[k] = val

    existing_yaml = yaml.dump(existing_context, allow_unicode=True, default_flow_style=False) if existing_context else "No context available"

    sections_spec = []
    for section in missing_sections:
        if section == "typical_services":
            sections_spec.append(f"""**typical_services** (8-10 items) - Services in local terminology ({language})
   Format: simple list of strings""")
        elif section == "recommended_functions":
            sections_spec.append(f"""**recommended_functions** (5-7 items) - Voice agent functions
   - name: Function name in {language}
   - priority: high/medium/low (MUST be English)
   - reason: Why important in {language}""")
        elif section == "sales_scripts":
            sections_spec.append(f"""**sales_scripts** (3-5 items) - Sales scripts in {language}
   - trigger: Machine-readable trigger (e.g., "price_question", "competitor_mention")
   - situation: When to use in {language}
   - script: The script text in {language}
   - goal: What we're trying to achieve in {language}
   - effectiveness: high/medium/low""")
        elif section == "competitors":
            sections_spec.append(f"""**competitors** (3-5 items) - Local/regional competitors in {country_name}
   - name: Competitor company name
   - positioning: Market position in {language}
   - strengths: [List in {language}]
   - weaknesses: [List in {language}]
   - our_differentiation: How AI voice agent is better in {language}""")
        elif section == "pricing_context":
            sections_spec.append(f"""**pricing_context** - Local pricing in {currency}
   - currency: "{currency}"
   - typical_budget_range: [min_number, max_number] (numbers only, no text)
   - entry_point: Number (starting price, number only)
   - roi_examples:
     - scenario: Description in {language}
       monthly_cost: Number
       monthly_savings: Number (MUST be greater than monthly_cost)
       payback_months: Number
   - value_anchors: [Statements in {language}]""")
        elif section == "market_context":
            sections_spec.append(f"""**market_context** - Local market info for {industry} in {country_name}
   - market_size: Market size estimate (string)
   - growth_rate: YoY growth (string like "5-7%")
   - key_trends: [Trends in {language}]
   - seasonality:
       high: [Peak months/periods]
       low: [Slow months/periods]""")

    sections_text = "\n\n".join(f"{i+1}. {s}" for i, s in enumerate(sections_spec))

    return f"""Generate ONLY the following missing sections for a {industry} industry profile in {country_name}.

**Language:** All text content must be in {language}.
**Country:** {country_name} ({country.upper()})
**Currency:** {currency}
**Compliance:** {', '.join(compliance) if compliance else 'None specified'}

**Existing profile context (do NOT repeat these — only generate missing sections):**
```yaml
{existing_yaml}
```

**Generate these missing sections:**

{sections_text}

IMPORTANT:
- severity and priority values MUST be in English: high, medium, or low
- entry_point and budget_range values MUST be numbers only (no currency text)
- monthly_savings MUST be greater than monthly_cost (positive ROI)
- Output valid YAML only, no markdown code blocks, no explanations
- Output ONLY the requested sections, nothing else"""


SYSTEM_PROMPT = """You are an expert consultant specializing in business process automation and AI voice agents.
Your task is to generate specific sections of localized industry profiles.
Output valid YAML only, no markdown code blocks, no explanations.
IMPORTANT: severity and priority values MUST always be in English: high, medium, or low."""


def parse_yaml_response(response: str) -> dict:
    """Parse YAML from LLM response."""
    text = response.strip()
    if "```yaml" in text:
        text = text.split("```yaml")[1].split("```")[0]
    elif "```" in text:
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1]
    text = text.strip()
    try:
        return yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        logger.error(f"YAML parse error: {e}")
        return {}


def merge_sections(existing: dict, new_sections: dict, missing: List[str]) -> dict:
    """Merge new sections into existing profile data."""
    result = dict(existing)
    for section in missing:
        if section in new_sections and new_sections[section]:
            result[section] = new_sections[section]
    return result


async def fix_profile(profile_info: dict, llm, retries: int = 2) -> bool:
    """Fix a single profile by generating missing sections."""
    path = profile_info["path"]
    industry = profile_info["industry"]
    country = profile_info["country"]
    region = profile_info["region"]
    missing = profile_info["missing"]
    existing_data = profile_info["data"]

    country_meta = get_country_meta(country)

    prompt = build_enrichment_prompt(
        industry=industry,
        country=country,
        region=region,
        country_meta=country_meta,
        existing_data=existing_data,
        missing_sections=missing,
    )

    for attempt in range(retries + 1):
        try:
            response = await llm.chat(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=4096,
            )

            new_sections = parse_yaml_response(response)
            if not new_sections:
                logger.warning(f"Empty response for {path}, attempt {attempt+1}")
                continue

            # Check that at least some missing sections were generated
            generated = [s for s in missing if s in new_sections and new_sections[s]]
            if not generated:
                logger.warning(f"No missing sections in response for {path}, attempt {attempt+1}")
                continue

            merged = merge_sections(existing_data, new_sections, missing)

            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(
                    merged, f,
                    allow_unicode=True,
                    default_flow_style=False,
                    sort_keys=False,
                    width=200,
                )

            still_missing = [s for s in missing if s not in generated]
            key = f"{region}/{country}/{industry}"
            if still_missing:
                print(f"  Partially fixed: got {generated}, still missing {still_missing}")
            else:
                print(f"  OK: generated {len(generated)} sections")

            return True

        except Exception as e:
            logger.error(f"Error fixing {path}: {e}, attempt {attempt+1}")
            if attempt < retries:
                await asyncio.sleep(2)

    return False


async def main():
    parser = argparse.ArgumentParser(description="Fix incomplete profiles via LLM")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be fixed")
    parser.add_argument("--provider", type=str, default=None, help="LLM provider (azure, deepseek)")
    parser.add_argument("--p2-only", action="store_true", help="Fix only P2 critical errors")
    parser.add_argument("--p5-only", action="store_true", help="Fix only P5 v2.0 sections")
    parser.add_argument("--region", type=str, help="Fix only specific region")
    parser.add_argument("--limit", type=int, default=0, help="Max profiles to fix")
    args = parser.parse_args()

    base_dir = str(Path(__file__).parent.parent / "config" / "industries")

    print("Scanning for incomplete profiles...")
    incomplete = find_incomplete_profiles(base_dir)

    # Filter by mode
    if args.p2_only:
        incomplete = [p for p in incomplete
                      if any(s in REQUIRED_SECTIONS for s in p["missing"])]
    elif args.p5_only:
        incomplete = [p for p in incomplete
                      if any(s in V2_SECTIONS for s in p["missing"])
                      and not any(s in REQUIRED_SECTIONS for s in p["missing"])]

    if args.region:
        incomplete = [p for p in incomplete if p["region"] == args.region]

    if args.limit > 0:
        incomplete = incomplete[:args.limit]

    if not incomplete:
        print("No incomplete profiles found!")
        return

    # Sort: P2 (critical) first, then P5
    def sort_key(p):
        has_critical = any(s in REQUIRED_SECTIONS for s in p["missing"])
        return (0 if has_critical else 1, p["path"])

    incomplete.sort(key=sort_key)

    # Summary
    p2_count = sum(1 for p in incomplete if any(s in REQUIRED_SECTIONS for s in p["missing"]))
    p5_count = len(incomplete) - p2_count

    print(f"\nFound {len(incomplete)} profiles to fix (P2 critical: {p2_count}, P5 v2.0: {p5_count}):")
    for p in incomplete:
        critical = any(s in REQUIRED_SECTIONS for s in p["missing"])
        marker = "CRITICAL" if critical else "v2.0"
        print(f"  [{marker}] {p['region']}/{p['country']}/{p['industry']}: {', '.join(p['missing'])}")

    if args.dry_run:
        print(f"\n(dry-run) Would fix {len(incomplete)} profiles")
        return

    print(f"\nStarting LLM enrichment...")
    llm = create_llm_client(args.provider)

    success = 0
    failed = 0

    for i, profile in enumerate(incomplete):
        key = f"{profile['region']}/{profile['country']}/{profile['industry']}"
        print(f"\n[{i+1}/{len(incomplete)}] Fixing {key} ({', '.join(profile['missing'])})...")

        ok = await fix_profile(profile, llm)
        if ok:
            success += 1
        else:
            failed += 1
            print(f"  FAILED")

        # Small delay to avoid rate limits
        await asyncio.sleep(1)

    print(f"\n{'='*50}")
    print(f"RESULTS: {success} fixed, {failed} failed out of {len(incomplete)}")


if __name__ == "__main__":
    asyncio.run(main())
