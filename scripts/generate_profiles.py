#!/usr/bin/env python3
"""
LLM Profile Generator - generates localized industry profiles.

Usage:
    python scripts/generate_profiles.py --region eu --country de --industry automotive
    python scripts/generate_profiles.py --batch eu de,at,ch automotive,medical
    python scripts/generate_profiles.py --wave1  # Generate priority profiles
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any

import yaml

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.llm.factory import create_llm_client
from src.knowledge.loader import IndustryProfileLoader
from src.knowledge.validator import ProfileValidator
from src.knowledge.country_detector import CountryDetector

import structlog

logger = structlog.get_logger("profile_generator")


class ProfileGenerator:
    """Generates localized industry profiles using LLM."""

    # Default industries to generate (40 industries total)
    DEFAULT_INDUSTRIES = [
        # === Текущие (8) ===
        "automotive", "medical", "logistics", "horeca",
        "education", "franchise", "real_estate", "wellness",
        # === Высокий приоритет (8) ===
        "legal", "finance", "insurance", "retail",
        "construction", "it_services", "recruitment", "travel",
        # === Средний приоритет (12) ===
        "manufacturing", "agriculture", "veterinary", "cleaning",
        "security", "telecom", "events", "funeral",
        "photo_video", "printing", "repair_services", "beauty_supplies",
        # === Нишевые (12) ===
        "gaming", "art_culture", "religion", "marine",
        "aviation", "energy", "waste", "childcare",
        "elderly_care", "coworking", "crypto", "cannabis",
    ]

    # Wave 1 priority countries
    WAVE1_COUNTRIES = [
        ("eu", "de"),   # Germany - main EU market
        ("na", "us"),   # USA - main NA market
        ("mena", "ae"), # UAE - main MENA market
        ("latam", "br"), # Brazil - main LATAM market
    ]

    def __init__(self, provider: Optional[str] = None):
        self.llm = create_llm_client(provider)
        self.loader = IndustryProfileLoader()
        self.validator = ProfileValidator()
        self.country_detector = CountryDetector()

    async def generate(
        self,
        region: str,
        country: str,
        industry: str,
        base_profile: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate a localized industry profile.

        Args:
            region: Region code (eu, na, latam, mena, sea, ru)
            country: Country code (de, us, br, etc.)
            industry: Industry ID (automotive, medical, etc.)
            base_profile: Optional base profile to adapt

        Returns:
            Generated profile as dict
        """
        # Get country metadata
        country_meta = self.country_detector.get_country_meta(country)
        if not country_meta:
            logger.warning(f"No metadata for country {country}, using defaults")
            country_meta = {
                "name": country.upper(),
                "language": "en",
                "currency": "USD",
            }

        # Load base profile if not provided
        if base_profile is None:
            base = self.loader.load_profile(industry)
            if base:
                base_profile = base.model_dump()
            else:
                base_profile = {}

        # Build prompt
        prompt = self._build_generation_prompt(
            region=region,
            country=country,
            industry=industry,
            country_meta=country_meta,
            base_profile=base_profile
        )

        logger.info(
            "Generating profile",
            region=region,
            country=country,
            industry=industry,
            language=country_meta.get("language")
        )

        # Call LLM
        response = await self.llm.chat(
            messages=[
                {"role": "system", "content": self._get_system_prompt()},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=8192
        )

        # Parse YAML response
        profile_data = self._parse_yaml_response(response)

        # Enrich with metadata
        if "meta" not in profile_data:
            profile_data["meta"] = {}

        profile_data["meta"]["id"] = industry
        profile_data["meta"]["region"] = region
        profile_data["meta"]["country"] = country
        profile_data["meta"]["language"] = country_meta.get("language", "en")
        profile_data["meta"]["currency"] = country_meta.get("currency", "EUR")
        profile_data["meta"]["phone_codes"] = country_meta.get("phone_codes", [])

        # Add inheritance marker
        profile_data["_extends"] = f"_base/{industry}"

        return profile_data

    def _get_system_prompt(self) -> str:
        """Get system prompt for profile generation."""
        return """You are an expert consultant specializing in business process automation and AI voice agents.

Your task is to generate localized industry profiles that help AI voice agents understand:
- Local business pain points and challenges
- Typical services and terminology in the local language
- Local competitors and market context
- Pricing expectations in local currency
- Effective sales approaches for the local market

Output valid YAML only, no markdown code blocks, no explanations."""

    def _build_generation_prompt(
        self,
        region: str,
        country: str,
        industry: str,
        country_meta: Dict[str, Any],
        base_profile: Dict[str, Any]
    ) -> str:
        """Build the generation prompt."""
        language = country_meta.get("language", "en")
        country_name = country_meta.get("name", country.upper())
        currency = country_meta.get("currency", "EUR")
        compliance = country_meta.get("compliance", [])

        # Serialize base profile for reference
        base_yaml = yaml.dump(base_profile, allow_unicode=True, default_flow_style=False) if base_profile else "No base profile available"

        return f"""Generate a detailed industry profile for {industry} industry in {country_name}.

**Language:** All text content (pain_points descriptions, FAQ answers, sales scripts, etc.) must be in {language}.

**Country context:**
- Currency: {currency}
- Compliance requirements: {', '.join(compliance) if compliance else 'None specified'}
- Region: {region}

**Base profile to adapt (not copy):**
```yaml
{base_yaml}
```

**Generate YAML with these sections:**

1. **pain_points** (5-7 items) - Local business problems in {language}
   - description: Problem description in {language}
   - severity: high/medium/low
   - solution_hint: How AI voice agent can help

2. **typical_services** (8-10 items) - Services in local terminology ({language})

3. **recommended_functions** (5-7 items) - Voice agent functions
   - name: Function name
   - priority: high/medium/low
   - reason: Why important

4. **typical_integrations** (4-6 items) - Local software systems
   - name: System type
   - examples: [Local system names]
   - priority: high/medium/low

5. **industry_faq** (5-7 items) - Common questions in {language}
   - question: Customer question in {language}
   - answer_template: Response template in {language}

6. **sales_scripts** (3-5 items) - Sales scripts in {language}
   - trigger: Machine-readable trigger (e.g., "price_question")
   - situation: When to use in {language}
   - script: The script text in {language}
   - goal: What we're trying to achieve

7. **competitors** (3-5 items) - Local/regional competitors
   - name: Competitor name
   - positioning: Market position
   - strengths: [List]
   - weaknesses: [List]
   - our_differentiation: How we're better

8. **pricing_context** - Local pricing in {currency}
   - currency: {currency}
   - typical_budget_range: [min, max]
   - entry_point: Starting price
   - roi_examples:
     - scenario: Description
       monthly_cost: Amount
       monthly_savings: Amount
       payback_months: Number
   - value_anchors: [Statements in {language}]

9. **market_context** - Local market info
   - market_size: Market size estimate
   - growth_rate: YoY growth
   - key_trends: [Trends in {language}]
   - seasonality:
     high: [Peak periods]
     low: [Slow periods]

10. **typical_objections** (3-5 items) - Objections in {language}
    - objection: Customer objection in {language}
    - response: Response in {language}

Output valid YAML only. Use the base profile as inspiration but adapt everything for {country_name}."""

    def _parse_yaml_response(self, response: str) -> Dict[str, Any]:
        """Parse YAML from LLM response."""
        # Clean up response
        text = response.strip()

        # Remove markdown code blocks
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
            logger.error(f"Failed to parse YAML: {e}")
            logger.debug(f"Response text: {text[:500]}")
            return {}

    async def generate_and_save(
        self,
        region: str,
        country: str,
        industry: str
    ) -> bool:
        """Generate profile and save to file."""
        try:
            profile_data = await self.generate(region, country, industry)

            if not profile_data or "pain_points" not in profile_data:
                logger.error(
                    "Generated profile is incomplete",
                    region=region,
                    country=country,
                    industry=industry
                )
                return False

            # Save to file
            output_dir = self.loader.config_dir / region / country
            output_dir.mkdir(parents=True, exist_ok=True)

            output_path = output_dir / f"{industry}.yaml"

            with open(output_path, "w", encoding="utf-8") as f:
                yaml.dump(
                    profile_data,
                    f,
                    allow_unicode=True,
                    default_flow_style=False,
                    sort_keys=False
                )

            logger.info(
                "Profile saved",
                path=str(output_path),
                pain_points=len(profile_data.get("pain_points", [])),
                sales_scripts=len(profile_data.get("sales_scripts", []))
            )

            return True

        except Exception as e:
            logger.error(
                "Failed to generate profile",
                region=region,
                country=country,
                industry=industry,
                error=str(e)
            )
            return False

    async def generate_batch(
        self,
        region: str,
        countries: List[str],
        industries: List[str]
    ) -> Dict[str, List[str]]:
        """
        Batch generate profiles for multiple countries and industries.

        Returns:
            Dict with 'success' and 'failed' lists
        """
        results = {"success": [], "failed": []}

        for country in countries:
            for industry in industries:
                key = f"{region}/{country}/{industry}"
                logger.info(f"Generating {key}...")

                success = await self.generate_and_save(region, country, industry)

                if success:
                    results["success"].append(key)
                else:
                    results["failed"].append(key)

                # Small delay to avoid rate limits
                await asyncio.sleep(1)

        return results

    async def generate_wave1(self) -> Dict[str, List[str]]:
        """Generate Wave 1 priority profiles."""
        results = {"success": [], "failed": []}

        for region, country in self.WAVE1_COUNTRIES:
            for industry in self.DEFAULT_INDUSTRIES:
                key = f"{region}/{country}/{industry}"
                logger.info(f"Generating {key}...")

                success = await self.generate_and_save(region, country, industry)

                if success:
                    results["success"].append(key)
                else:
                    results["failed"].append(key)

                await asyncio.sleep(1)

        return results


async def main():
    parser = argparse.ArgumentParser(description="Generate localized industry profiles")

    parser.add_argument("--region", type=str, help="Region code (eu, na, latam, mena, sea)")
    parser.add_argument("--country", type=str, help="Country code (de, us, br, etc.)")
    parser.add_argument("--industry", type=str, help="Industry ID (automotive, medical, etc.)")
    parser.add_argument("--batch", nargs=3, metavar=("REGION", "COUNTRIES", "INDUSTRIES"),
                        help="Batch mode: region 'de,at,ch' 'automotive,medical'")
    parser.add_argument("--wave1", action="store_true", help="Generate Wave 1 priority profiles")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be generated")
    parser.add_argument("--provider", type=str, default=None,
                        help="LLM provider (azure, deepseek). Default: env LLM_PROVIDER or azure")

    args = parser.parse_args()

    generator = ProfileGenerator(provider=args.provider)

    if args.wave1:
        if args.dry_run:
            print("Wave 1 profiles to generate:")
            for region, country in ProfileGenerator.WAVE1_COUNTRIES:
                for industry in ProfileGenerator.DEFAULT_INDUSTRIES:
                    print(f"  - {region}/{country}/{industry}")
            return

        print("Generating Wave 1 profiles...")
        results = await generator.generate_wave1()

        print(f"\nResults:")
        print(f"  Success: {len(results['success'])}")
        print(f"  Failed: {len(results['failed'])}")

        if results['failed']:
            print("\nFailed profiles:")
            for key in results['failed']:
                print(f"  - {key}")

    elif args.batch:
        region, countries_str, industries_str = args.batch
        countries = [c.strip() for c in countries_str.split(",")]
        industries = [i.strip() for i in industries_str.split(",")]

        if args.dry_run:
            print(f"Batch profiles to generate for {region}:")
            for country in countries:
                for industry in industries:
                    print(f"  - {region}/{country}/{industry}")
            return

        print(f"Generating batch profiles for {region}...")
        results = await generator.generate_batch(region, countries, industries)

        print(f"\nResults:")
        print(f"  Success: {len(results['success'])}")
        print(f"  Failed: {len(results['failed'])}")

    elif args.region and args.country and args.industry:
        if args.dry_run:
            print(f"Would generate: {args.region}/{args.country}/{args.industry}")
            return

        print(f"Generating {args.region}/{args.country}/{args.industry}...")
        success = await generator.generate_and_save(args.region, args.country, args.industry)

        if success:
            print("Profile generated successfully!")
        else:
            print("Failed to generate profile")
            sys.exit(1)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
