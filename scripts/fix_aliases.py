#!/usr/bin/env python3
"""Add missing aliases to regional profiles.

Strategy: use base profile aliases + English industry synonyms.
"""

import glob
import sys
import yaml
from pathlib import Path

# English aliases per industry (used as universal identifiers)
INDUSTRY_ALIASES = {
    "agriculture": ["agriculture", "farming", "agribusiness", "farm"],
    "art_culture": ["art", "culture", "museum", "gallery", "theater"],
    "automotive": ["automotive", "car service", "auto repair", "car dealership"],
    "aviation": ["aviation", "private jet", "charter flight", "business aviation"],
    "beauty_supplies": ["beauty supplies", "cosmetics wholesale", "salon products"],
    "cannabis": ["cannabis", "dispensary", "marijuana", "CBD"],
    "childcare": ["childcare", "daycare", "nanny", "kindergarten"],
    "cleaning": ["cleaning", "janitorial", "housekeeping", "maid service"],
    "construction": ["construction", "building", "renovation", "contractor"],
    "coworking": ["coworking", "shared office", "flexible workspace"],
    "crypto": ["crypto", "cryptocurrency", "blockchain", "bitcoin", "exchange"],
    "education": ["education", "school", "training", "courses", "tutoring"],
    "elderly_care": ["elderly care", "senior care", "nursing home", "home care"],
    "energy": ["energy", "solar", "renewable", "power", "utilities"],
    "events": ["events", "event planning", "conference", "catering"],
    "finance": ["finance", "banking", "loans", "credit", "financial services"],
    "franchise": ["franchise", "franchising", "franchisee", "brand license"],
    "funeral": ["funeral", "mortuary", "cremation", "memorial"],
    "gaming": ["gaming", "esports", "game center", "internet cafe"],
    "horeca": ["HoReCa", "restaurant", "hotel", "cafe", "hospitality"],
    "insurance": ["insurance", "coverage", "policy", "underwriting"],
    "it_services": ["IT services", "tech support", "managed services", "IT consulting"],
    "legal": ["legal", "law firm", "attorney", "lawyer", "notary"],
    "logistics": ["logistics", "shipping", "freight", "delivery", "supply chain"],
    "manufacturing": ["manufacturing", "factory", "production", "industrial"],
    "marine": ["marine", "yacht club", "marina", "boating", "sailing"],
    "medical": ["medical", "healthcare", "clinic", "hospital", "doctor"],
    "photo_video": ["photo studio", "video production", "photography", "videography"],
    "printing": ["printing", "print shop", "typography", "packaging"],
    "real_estate": ["real estate", "property", "realtor", "realty"],
    "recruitment": ["recruitment", "staffing", "HR", "headhunting", "hiring"],
    "religion": ["religion", "church", "temple", "parish", "ministry"],
    "repair_services": ["repair services", "service center", "phone repair", "tech repair"],
    "retail": ["retail", "shop", "store", "e-commerce", "merchandise"],
    "security": ["security", "guard service", "surveillance", "alarm systems"],
    "telecom": ["telecom", "ISP", "internet provider", "mobile operator"],
    "travel": ["travel", "tourism", "travel agency", "tour operator"],
    "veterinary": ["veterinary", "vet clinic", "animal hospital", "pet care"],
    "waste": ["waste management", "recycling", "waste disposal", "garbage collection"],
    "wellness": ["wellness", "spa", "massage", "fitness", "health club"],
}


def add_aliases_to_file(path: str, dry_run: bool = False) -> bool:
    """Add aliases to a profile file if missing. Returns True if modified."""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    try:
        data = yaml.safe_load(content) or {}
    except yaml.YAMLError:
        return False

    # Skip if aliases already exist and non-empty
    existing = data.get("aliases")
    if existing and len(existing) >= 2:
        return False

    # Determine industry from filename
    industry = Path(path).stem

    aliases = INDUSTRY_ALIASES.get(industry)
    if not aliases:
        return False

    if dry_run:
        return True

    # Insert aliases after meta section or at the beginning
    # Find where to insert
    lines = content.split("\n")
    insert_idx = None

    # Look for existing empty aliases field
    for i, line in enumerate(lines):
        if line.startswith("aliases:"):
            # Replace the aliases line and any following list items
            end_idx = i + 1
            while end_idx < len(lines) and lines[end_idx].startswith("- "):
                end_idx += 1
            # Replace
            aliases_yaml = "aliases:\n" + "\n".join(f"- \"{a}\"" for a in aliases)
            lines[i:end_idx] = [aliases_yaml]
            insert_idx = -1  # signal that we already handled it
            break

    if insert_idx is None:
        # No existing aliases field — insert after meta block or after first line
        for i, line in enumerate(lines):
            if line.startswith("meta:"):
                # Find end of meta block
                j = i + 1
                while j < len(lines) and (lines[j].startswith("  ") or lines[j].strip() == ""):
                    j += 1
                insert_idx = j
                break

        if insert_idx is None:
            insert_idx = 0

        aliases_yaml = "aliases:\n" + "\n".join(f"- \"{a}\"" for a in aliases)
        lines.insert(insert_idx, aliases_yaml)

    new_content = "\n".join(lines)

    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)

    return True


def main():
    dry_run = "--dry-run" in sys.argv
    base_dir = "config/industries"
    files = sorted(glob.glob(f"{base_dir}/**/*.yaml", recursive=True))

    modified = 0
    for path in files:
        if "/_base/" in path or "_index" in path or "_countries" in path:
            continue
        if add_aliases_to_file(path, dry_run=dry_run):
            modified += 1

    action = "would modify" if dry_run else "modified"
    print(f"Total: {action} {modified} files")


if __name__ == "__main__":
    main()
