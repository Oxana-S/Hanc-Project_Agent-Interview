#!/usr/bin/env python3
"""
Fix L2 warnings: add missing sub-fields (sales_scripts, competitors, seasonality, key_trends, roi_examples).
Uses LLM to generate contextually appropriate content in the correct language.
"""

import asyncio
import json
import os
import re
import sys
import yaml
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.llm.factory import create_llm_client

BASE = Path(__file__).parent.parent / "config" / "industries"

COUNTRY_LANGUAGE = {
    "de": "German", "at": "German", "ch": "German", "fr": "French", "it": "Italian",
    "es": "Spanish", "pt": "Portuguese", "ro": "Romanian", "bg": "Bulgarian",
    "hu": "Hungarian", "gr": "Greek",
    "us": "English", "ca": "English",
    "br": "Portuguese", "ar": "Spanish", "mx": "Spanish",
    "ae": "Arabic", "sa": "Arabic", "qa": "Arabic",
    "cn": "Chinese", "vn": "Vietnamese", "id": "Indonesian",
    "ru": "Russian",
}

# L2 issues to fix — gathered from validation output
ISSUES = [
    # Sales scripts too few (need min 3)
    {"path": "eu/fr/legal.yaml", "fix": "add_sales_scripts", "current": 2, "need": 3},
    {"path": "eu/gr/art_culture.yaml", "fix": "add_sales_scripts", "current": 2, "need": 3},
    {"path": "eu/gr/events.yaml", "fix": "add_sales_scripts", "current": 2, "need": 3},
    {"path": "eu/gr/retail.yaml", "fix": "add_sales_scripts", "current": 1, "need": 3},
    {"path": "eu/ro/coworking.yaml", "fix": "add_sales_scripts", "current": 1, "need": 3},
    {"path": "na/ca/medical.yaml", "fix": "add_sales_scripts", "current": 2, "need": 3},
    {"path": "latam/mx/events.yaml", "fix": "add_sales_scripts", "current": 2, "need": 3},
    {"path": "latam/mx/religion.yaml", "fix": "add_sales_scripts", "current": 2, "need": 3},
    # Competitors too few (need min 2)
    {"path": "eu/es/printing.yaml", "fix": "add_competitors", "current": 1, "need": 2},
    {"path": "eu/gr/marine.yaml", "fix": "add_competitors", "current": 1, "need": 2},
    {"path": "eu/pt/marine.yaml", "fix": "add_competitors", "current": 1, "need": 2},
    {"path": "latam/br/telecom.yaml", "fix": "add_competitors", "current": 1, "need": 2},
    # Seasonality missing
    {"path": "eu/ro/it_services.yaml", "fix": "add_seasonality"},
    {"path": "latam/mx/crypto.yaml", "fix": "add_seasonality_and_trends"},
    {"path": "sea/vn/beauty_supplies.yaml", "fix": "add_seasonality"},
    # ROI examples missing
    {"path": "latam/ar/construction.yaml", "fix": "add_roi_examples"},
]


def load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_yaml_raw(path, data):
    """Save YAML preserving reasonable formatting."""
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False, width=200)


def get_language(path_str):
    parts = path_str.split("/")
    country = parts[1] if len(parts) > 1 else "us"
    return COUNTRY_LANGUAGE.get(country, "English")


def generate_content(client, profile_data, path_str, fix_type, current_count=0, need_count=0):
    """Use LLM to generate missing content."""
    language = get_language(path_str)
    industry = profile_data.get("meta", {}).get("id", "unknown")
    country = profile_data.get("meta", {}).get("country", "unknown")

    if fix_type == "add_sales_scripts":
        existing_triggers = []
        for s in (profile_data.get("sales_scripts") or []):
            if isinstance(s, dict):
                existing_triggers.append(s.get("trigger", ""))

        n = need_count - current_count
        prompt = f"""Generate {n} additional sales scripts for a {industry} business in {country}.
Language: {language}. Existing triggers: {existing_triggers}.

Each script MUST have these fields:
- trigger: (short English identifier, e.g. 'follow_up', 'objection_handling', 'upsell')
- situation: (when to use, in {language})
- script: (actual sales dialog, in {language}, 50-150 words)
- goal: (what the script achieves, in {language})

IMPORTANT: severity and priority values MUST always be in English: high, medium, or low.
Return ONLY valid YAML (a list of dicts), no markdown fences."""

    elif fix_type == "add_competitors":
        existing_names = []
        for c in (profile_data.get("competitors") or []):
            if isinstance(c, dict):
                existing_names.append(c.get("name", ""))

        n = need_count - current_count
        prompt = f"""Generate {n} additional competitor(s) for a {industry} business in {country}.
Language: {language}. Existing competitors: {existing_names}.

Each competitor MUST have:
- name: (real company name relevant to {country})
- positioning: (in {language})
- strengths: (list of 2-3, in {language})
- weaknesses: (list of 1-2, in {language})
- our_differentiation: (in {language})

Return ONLY valid YAML (a list of dicts), no markdown fences."""

    elif fix_type in ("add_seasonality", "add_seasonality_and_trends"):
        prompt = f"""Generate market seasonality data for a {industry} business in {country}.
Language: {language}.

Return ONLY valid YAML with this structure:
seasonality:
  high:
  - (month or period name in {language})
  - (month or period name in {language})
  low:
  - (month or period name in {language})
  - (month or period name in {language})
"""
        if fix_type == "add_seasonality_and_trends":
            prompt += f"""
Also add:
key_trends:
- (trend 1 in {language})
- (trend 2 in {language})
- (trend 3 in {language})
"""
        prompt += "\nReturn ONLY valid YAML, no markdown fences."

    elif fix_type == "add_roi_examples":
        currency = profile_data.get("pricing_context", {}).get("currency", "USD")
        prompt = f"""Generate 1-2 ROI examples for a {industry} business in {country}.
Currency: {currency}. Language: {language}.

Each ROI example MUST have:
- scenario: (description in {language})
- monthly_cost: (number only)
- monthly_savings: (number only, MUST be greater than monthly_cost)
- payback_months: (integer 1-24)

Return ONLY valid YAML (a list of dicts), no markdown fences."""

    else:
        return None

    messages = [
        {"role": "system", "content": "You are a YAML generator. Return ONLY valid YAML. No markdown, no explanations."},
        {"role": "user", "content": prompt},
    ]
    response = asyncio.run(client.chat(
        messages=messages,
        temperature=0.7,
        max_tokens=1500,
    ))
    return response


def parse_yaml_response(text):
    """Parse YAML from LLM response."""
    text = text.strip()
    # Remove markdown fences
    text = re.sub(r"```ya?ml\s*", "", text)
    text = re.sub(r"```\s*$", "", text)
    text = text.strip()
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        return None


def fix_issue(client, issue):
    path = BASE / issue["path"]
    if not path.exists():
        print(f"  SKIP: {issue['path']} not found")
        return False

    data = load_yaml(path)
    if not data:
        print(f"  SKIP: {issue['path']} empty")
        return False

    fix_type = issue["fix"]
    current = issue.get("current", 0)
    need = issue.get("need", 0)

    print(f"  Generating {fix_type} for {issue['path']}...", end=" ", flush=True)

    response = generate_content(client, data, issue["path"], fix_type, current, need)
    if not response:
        print("ERROR: no response")
        return False

    parsed = parse_yaml_response(response)
    if parsed is None:
        print(f"ERROR: could not parse YAML")
        print(f"    Raw: {response[:200]}")
        return False

    # Merge into data
    if fix_type == "add_sales_scripts":
        if isinstance(parsed, list):
            items = parsed
        elif isinstance(parsed, dict) and "sales_scripts" in parsed:
            items = parsed["sales_scripts"]
        else:
            items = [parsed] if isinstance(parsed, dict) else []
        existing = data.get("sales_scripts", []) or []
        data["sales_scripts"] = existing + items

    elif fix_type == "add_competitors":
        if isinstance(parsed, list):
            items = parsed
        elif isinstance(parsed, dict) and "competitors" in parsed:
            items = parsed["competitors"]
        else:
            items = [parsed] if isinstance(parsed, dict) else []
        existing = data.get("competitors", []) or []
        data["competitors"] = existing + items

    elif fix_type in ("add_seasonality", "add_seasonality_and_trends"):
        mc = data.get("market_context", {})
        if not isinstance(mc, dict):
            mc = {}
        if isinstance(parsed, dict):
            if "seasonality" in parsed:
                mc["seasonality"] = parsed["seasonality"]
            elif "high" in parsed or "low" in parsed:
                mc["seasonality"] = parsed
            if "key_trends" in parsed:
                mc["key_trends"] = parsed["key_trends"]
        data["market_context"] = mc

    elif fix_type == "add_roi_examples":
        pc = data.get("pricing_context", {})
        if not isinstance(pc, dict):
            pc = {}
        if isinstance(parsed, list):
            pc["roi_examples"] = parsed
        elif isinstance(parsed, dict) and "roi_examples" in parsed:
            pc["roi_examples"] = parsed["roi_examples"]
        else:
            pc["roi_examples"] = [parsed] if isinstance(parsed, dict) else []
        data["pricing_context"] = pc

    save_yaml_raw(path, data)
    print("OK")
    return True


def main():
    provider = "azure"
    for arg in sys.argv[1:]:
        if arg.startswith("--provider="):
            provider = arg.split("=")[1]

    client = create_llm_client(provider)
    print(f"Using provider: {provider}")
    print(f"Total issues to fix: {len(ISSUES)}\n")

    fixed = 0
    for issue in ISSUES:
        ok = fix_issue(client, issue)
        if ok:
            fixed += 1

    print(f"\nFixed: {fixed}/{len(ISSUES)}")


if __name__ == "__main__":
    main()
