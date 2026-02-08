#!/usr/bin/env python3
"""
Regenerate missing industry profiles.

Usage:
    python scripts/regenerate_missing.py --region eu
    python scripts/regenerate_missing.py --all
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.generate_profiles import ProfileGenerator
import structlog

logger = structlog.get_logger("regenerate_missing")

# All countries by region
COUNTRIES = {
    "eu": ["de", "at", "ch", "fr", "it", "es", "pt", "ro", "bg", "hu", "gr"],
    "na": ["us", "ca"],
    "latam": ["br", "ar", "mx"],
    "mena": ["ae", "sa", "qa"],
    "sea": ["cn", "vn", "id"],
    "ru": ["ru"],
}


def get_missing_profiles(region: str, countries: list, industries: list, config_dir: Path) -> list:
    """Get list of missing profiles for a region."""
    missing = []

    for country in countries:
        country_dir = config_dir / region / country
        existing = set()

        if country_dir.exists():
            existing = {f.stem for f in country_dir.glob("*.yaml")}

        for industry in industries:
            if industry not in existing:
                missing.append((region, country, industry))

    return missing


async def regenerate_region(region: str, provider: str = None):
    """Regenerate missing profiles for a region."""
    generator = ProfileGenerator(provider=provider)
    config_dir = Path(__file__).parent.parent / "config" / "industries"

    countries = COUNTRIES.get(region, [])
    industries = ProfileGenerator.DEFAULT_INDUSTRIES

    missing = get_missing_profiles(region, countries, industries, config_dir)

    if not missing:
        print(f"[{region}] No missing profiles")
        return {"success": [], "failed": []}

    print(f"[{region}] Found {len(missing)} missing profiles")

    results = {"success": [], "failed": []}

    for i, (r, c, ind) in enumerate(missing, 1):
        key = f"{r}/{c}/{ind}"
        print(f"[{region}] [{i}/{len(missing)}] Generating {key}...")

        try:
            success = await generator.generate_and_save(r, c, ind)
            if success:
                results["success"].append(key)
            else:
                results["failed"].append(key)
        except Exception as e:
            logger.error(f"Failed: {key}", error=str(e))
            results["failed"].append(key)

        # Small delay to avoid rate limits
        await asyncio.sleep(1)

    return results


async def main():
    parser = argparse.ArgumentParser(description="Regenerate missing profiles")
    parser.add_argument("--region", type=str, help="Region to regenerate (eu, na, latam, mena, sea, ru)")
    parser.add_argument("--all", action="store_true", help="Regenerate all regions")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be generated")
    parser.add_argument("--provider", type=str, default=None,
                        help="LLM provider (azure, deepseek). Default: env LLM_PROVIDER or azure")

    args = parser.parse_args()

    config_dir = Path(__file__).parent.parent / "config" / "industries"
    industries = ProfileGenerator.DEFAULT_INDUSTRIES

    if args.dry_run:
        regions = list(COUNTRIES.keys()) if args.all else [args.region] if args.region else []

        for region in regions:
            countries = COUNTRIES.get(region, [])
            missing = get_missing_profiles(region, countries, industries, config_dir)
            print(f"\n[{region}] Missing {len(missing)} profiles:")
            for r, c, ind in missing[:10]:
                print(f"  - {r}/{c}/{ind}")
            if len(missing) > 10:
                print(f"  ... and {len(missing) - 10} more")
        return

    if args.all:
        # Run all regions sequentially (could be parallelized if needed)
        total_results = {"success": [], "failed": []}
        for region in COUNTRIES.keys():
            results = await regenerate_region(region, provider=args.provider)
            total_results["success"].extend(results["success"])
            total_results["failed"].extend(results["failed"])

        print(f"\n=== TOTAL RESULTS ===")
        print(f"Success: {len(total_results['success'])}")
        print(f"Failed: {len(total_results['failed'])}")

    elif args.region:
        results = await regenerate_region(args.region, provider=args.provider)
        print(f"\n=== {args.region.upper()} RESULTS ===")
        print(f"Success: {len(results['success'])}")
        print(f"Failed: {len(results['failed'])}")

        if results['failed']:
            print("\nFailed profiles:")
            for key in results['failed']:
                print(f"  - {key}")
    else:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
