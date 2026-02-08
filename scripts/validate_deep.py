#!/usr/bin/env python3
"""
Deep validation of all industry profiles — extended checks beyond basic structure.

Additional checks:
  L6. Content quality (duplicates, length, truncation, empty strings)
  L7. Localization depth (language mismatch heuristics)
  L8. Cross-profile consistency (coverage matrix, identical profiles, _extends)
  L9. Sales scripts quality (trigger uniqueness, effectiveness, script length)
  L10. Pricing coherence (entry_point in range, payback, roi count)
  L11. Data integrity (file size, None values, YAML re-serializability)
"""

import glob
import hashlib
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import yaml

# --- Mappings ---
COUNTRY_LANGUAGE = {
    "de": "de", "at": "de", "ch": "de", "fr": "fr", "it": "it",
    "es": "es", "pt": "pt", "ro": "ro", "bg": "bg", "hu": "hu", "gr": "el",
    "us": "en", "ca": "en",
    "br": "pt", "ar": "es", "mx": "es",
    "ae": "ar", "sa": "ar", "qa": "ar",
    "cn": "zh", "vn": "vi", "id": "id",
    "ru": "ru",
}

COUNTRY_CURRENCY = {
    "de": "EUR", "at": "EUR", "ch": "CHF", "fr": "EUR", "it": "EUR",
    "es": "EUR", "pt": "EUR", "ro": "RON", "bg": "BGN", "hu": "HUF", "gr": "EUR",
    "us": "USD", "ca": "CAD",
    "br": "BRL", "ar": "ARS", "mx": "MXN",
    "ae": "AED", "sa": "SAR", "qa": "QAR",
    "cn": "CNY", "vn": "VND", "id": "IDR",
    "ru": "RUB",
}

ALL_COUNTRIES = list(COUNTRY_LANGUAGE.keys())

VALID_ENUMS = {"high", "medium", "low"}

# Language detection heuristics: regex patterns for specific scripts
LANG_PATTERNS = {
    "ru": re.compile(r"[а-яА-ЯёЁ]"),
    "ar": re.compile(r"[\u0600-\u06FF]"),
    "zh": re.compile(r"[\u4e00-\u9fff]"),
    "vi": re.compile(r"[ăâđêôơư]"),
    "el": re.compile(r"[α-ωΑ-Ω]"),
    "bg": re.compile(r"[а-яА-Я]"),  # Cyrillic, same as Russian
    "de": re.compile(r"[äöüßÄÖÜ]"),
    "fr": re.compile(r"[àâçéèêëïîôùûüÿœæÀÂÇÉÈÊËÏÎÔÙÛÜŸŒÆ]"),
    "ro": re.compile(r"[ăâîșțĂÂÎȘȚ]"),
    "hu": re.compile(r"[áéíóöőúüűÁÉÍÓÖŐÚÜŰ]"),
}

# Script-level language families
CYRILLIC_LANGS = {"ru", "bg"}
ARABIC_LANGS = {"ar"}
CJK_LANGS = {"zh"}
LATIN_LANGS = {"de", "fr", "it", "es", "pt", "ro", "hu", "en", "id", "vi"}
GREEK_LANGS = {"el"}


def detect_script(text: str) -> str:
    """Detect writing script of text."""
    if re.search(r"[\u4e00-\u9fff]", text):
        return "cjk"
    if re.search(r"[\u0600-\u06FF]", text):
        return "arabic"
    if re.search(r"[α-ωΑ-Ωά-ώ]", text):
        return "greek"
    if re.search(r"[а-яА-ЯёЁ]", text):
        return "cyrillic"
    # Vietnamese-specific: đ, ơ, ư (not shared with Romanian ă â î ș ț)
    if re.search(r"[đơư]", text):
        return "vietnamese"
    # Latin covers Romanian (ăâîșț), German (äöüß), French (àçéè), etc.
    if re.search(r"[a-zA-Z]", text):
        return "latin"
    return "unknown"


def expected_script(lang: str) -> str:
    if lang in CYRILLIC_LANGS:
        return "cyrillic"
    if lang in ARABIC_LANGS:
        return "arabic"
    if lang in CJK_LANGS:
        return "cjk"
    if lang in GREEK_LANGS:
        return "greek"
    if lang == "vi":
        return "vietnamese"
    return "latin"


def content_hash(data: dict) -> str:
    """Compute hash of profile content (excluding meta and _extends)."""
    relevant = {k: v for k, v in data.items() if k not in ("meta", "_extends", "aliases")}
    return hashlib.md5(yaml.dump(relevant, allow_unicode=True, sort_keys=True).encode()).hexdigest()


class DeepValidator:
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.base_profiles: Dict[str, dict] = {}
        self.all_profiles: List[dict] = []  # [{path, region, country, industry, data, errors, warnings}]
        self.hashes: Dict[str, List[str]] = defaultdict(list)  # hash -> [paths]
        self.coverage: Dict[str, Set[str]] = defaultdict(set)  # country -> set of industries

    def load_all(self):
        """Load all profiles into memory."""
        # Load base profiles
        base_dir = self.base_dir / "_base"
        if base_dir.exists():
            for f in sorted(base_dir.glob("*.yaml")):
                try:
                    with open(f, "r", encoding="utf-8") as fh:
                        data = yaml.safe_load(fh) or {}
                    self.base_profiles[f.stem] = data
                except yaml.YAMLError:
                    pass

        # Load regional profiles
        for path in sorted(glob.glob(str(self.base_dir / "**" / "*.yaml"), recursive=True)):
            p = Path(path)
            if "/_base/" in path or "_index" in path or "_countries" in path:
                continue
            rel = p.relative_to(self.base_dir)
            parts = list(rel.parts)
            if len(parts) < 3:
                continue

            region, country, fname = parts[0], parts[1], parts[2]
            industry = fname.replace(".yaml", "")

            try:
                with open(path, "r", encoding="utf-8") as fh:
                    raw = fh.read()
                data = yaml.safe_load(raw) or {}
            except yaml.YAMLError:
                data = None
                raw = ""

            entry = {
                "path": path,
                "region": region,
                "country": country,
                "industry": industry,
                "data": data,
                "raw": raw,
                "file_size": os.path.getsize(path),
                "errors": [],
                "warnings": [],
                "info": [],
            }

            if data:
                h = content_hash(data)
                self.hashes[h].append(f"{region}/{country}/{industry}")
                self.coverage[country].add(industry)

            self.all_profiles.append(entry)

        print(f"Loaded: {len(self.base_profiles)} base, {len(self.all_profiles)} regional profiles")

    def validate_all(self):
        """Run all deep validation checks."""
        for entry in self.all_profiles:
            if entry["data"] is None:
                entry["errors"].append("YAML parse error")
                continue
            self._check_content_quality(entry)
            self._check_localization_depth(entry)
            self._check_sales_scripts(entry)
            self._check_pricing_coherence(entry)
            self._check_data_integrity(entry)
            self._check_extends(entry)

        # Cross-profile checks
        self._check_duplicates()
        self._check_coverage()

    def _check_content_quality(self, e: dict):
        """L6: Content quality — duplicates, length, truncation."""
        data = e["data"]

        # Check for duplicate typical_services
        services = data.get("typical_services", [])
        if isinstance(services, list):
            seen = set()
            for i, s in enumerate(services):
                s_str = str(s).strip().lower()
                if s_str in seen:
                    e["warnings"].append(f"L6: typical_services[{i}] duplicate: '{s}'")
                seen.add(s_str)
                if isinstance(s, str) and len(s.strip()) < 3:
                    e["warnings"].append(f"L6: typical_services[{i}] too short: '{s}'")

        # Check for duplicate pain_points
        pps = data.get("pain_points", [])
        if isinstance(pps, list):
            seen_desc = set()
            for i, pp in enumerate(pps):
                if isinstance(pp, dict):
                    desc = str(pp.get("description", "")).strip().lower()
                    if desc and desc in seen_desc:
                        e["warnings"].append(f"L6: pain_points[{i}] duplicate description")
                    seen_desc.add(desc)
                    # Check truncation: description missing severity/solution_hint indicates real truncation
                    raw_desc = str(pp.get("description", ""))
                    has_severity = pp.get("severity") is not None
                    has_solution = pp.get("solution_hint") is not None
                    if not has_severity or not has_solution:
                        e["warnings"].append(f"L6: pain_points[{i}].description likely truncated (missing severity/solution_hint): '...{raw_desc[-40:]}'")
                    # Check CJK descriptions for minimum useful length
                    if re.search(r"[\u4e00-\u9fff]", raw_desc):
                        if len(raw_desc.strip()) < 8:
                            e["warnings"].append(f"L6: pain_points[{i}].description too short ({len(raw_desc)} chars)")
                    elif len(raw_desc.strip()) < 15:
                        e["warnings"].append(f"L6: pain_points[{i}].description too short ({len(raw_desc)} chars)")

        # Check for empty string values in critical fields
        for field in ["pain_points", "recommended_functions", "industry_faq"]:
            items = data.get(field, [])
            if isinstance(items, list):
                for i, item in enumerate(items):
                    if isinstance(item, dict):
                        for k, v in item.items():
                            if isinstance(v, str) and v.strip() == "":
                                e["warnings"].append(f"L6: {field}[{i}].{k} is empty string")

        # File size check
        if e["file_size"] < 500:
            e["warnings"].append(f"L6: File suspiciously small ({e['file_size']} bytes)")
        elif e["file_size"] > 50000:
            e["info"].append(f"L6: File very large ({e['file_size']} bytes)")

    def _check_localization_depth(self, e: dict):
        """L7: Check if content matches expected language."""
        data = e["data"]
        country = e["country"]
        exp_lang = COUNTRY_LANGUAGE.get(country, "en")
        exp_scr = expected_script(exp_lang)

        # Collect text samples from key fields
        text_samples = []

        # pain_points descriptions
        for pp in (data.get("pain_points") or []):
            if isinstance(pp, dict):
                desc = pp.get("description", "")
                if desc:
                    text_samples.append(("pain_points.description", desc))

        # typical_services
        for s in (data.get("typical_services") or []):
            if isinstance(s, str):
                text_samples.append(("typical_services", s))

        # industry_faq questions
        for faq in (data.get("industry_faq") or []):
            if isinstance(faq, dict):
                q = faq.get("question", "")
                if q:
                    text_samples.append(("industry_faq.question", q))

        # Check writing script of samples
        wrong_script_count = 0
        total_checked = 0
        for field, text in text_samples[:10]:  # Check first 10 samples
            detected = detect_script(text)
            total_checked += 1
            if detected != "unknown" and detected != exp_scr:
                # Allow Latin in any language (common for technical terms)
                if detected == "latin" and exp_scr != "latin":
                    # Latin text in non-Latin language — could be OK for short terms
                    if len(text) > 30:
                        wrong_script_count += 1
                elif detected != "latin":
                    wrong_script_count += 1

        if total_checked > 0 and wrong_script_count > total_checked * 0.5:
            e["errors"].append(
                f"L7: Content script mismatch — expected {exp_scr} for {country}, "
                f"but {wrong_script_count}/{total_checked} samples in different script"
            )

        # Check if competitors are generic (same across countries)
        competitors = data.get("competitors", [])
        if isinstance(competitors, list) and len(competitors) > 0:
            generic_names = {"Competitor 1", "Competitor 2", "Company A", "Company B",
                           "Generic", "N/A", "TBD", "Unknown"}
            for i, c in enumerate(competitors):
                if isinstance(c, dict):
                    name = str(c.get("name", "")).strip()
                    if name in generic_names or name == "":
                        e["warnings"].append(f"L7: competitors[{i}].name is generic or empty: '{name}'")

    def _check_sales_scripts(self, e: dict):
        """L9: Sales scripts quality."""
        data = e["data"]
        scripts = data.get("sales_scripts", [])
        if not isinstance(scripts, list) or len(scripts) == 0:
            return

        triggers_seen = set()
        for i, s in enumerate(scripts):
            if not isinstance(s, dict):
                e["warnings"].append(f"L9: sales_scripts[{i}] is not a dict")
                continue

            # Trigger uniqueness
            trigger = s.get("trigger", "")
            if trigger:
                if trigger in triggers_seen:
                    e["warnings"].append(f"L9: sales_scripts[{i}].trigger duplicate: '{trigger}'")
                triggers_seen.add(trigger)

            # Script length
            script_text = str(s.get("script", ""))
            if len(script_text.strip()) < 20:
                e["warnings"].append(f"L9: sales_scripts[{i}].script too short ({len(script_text)} chars)")
            elif len(script_text) > 2000:
                e["info"].append(f"L9: sales_scripts[{i}].script very long ({len(script_text)} chars)")

            # Effectiveness field
            eff = s.get("effectiveness", "")
            if eff and str(eff).lower() not in VALID_ENUMS:
                e["warnings"].append(f"L9: sales_scripts[{i}].effectiveness='{eff}' not in {VALID_ENUMS}")

    def _check_pricing_coherence(self, e: dict):
        """L10: Pricing coherence."""
        data = e["data"]
        pricing = data.get("pricing_context")
        if not isinstance(pricing, dict):
            return

        budget = pricing.get("typical_budget_range", [])
        entry_point = pricing.get("entry_point")

        # Check entry_point is within budget_range
        if isinstance(budget, list) and len(budget) == 2 and entry_point is not None:
            try:
                low, high = float(budget[0]), float(budget[1])
                ep = float(entry_point)
                if ep > high:
                    e["warnings"].append(f"L10: entry_point({ep}) > budget_range max({high})")
                # entry_point can be below budget_range (intro pricing)
            except (ValueError, TypeError):
                pass

        # Check payback_months reasonableness
        roi_examples = pricing.get("roi_examples", [])
        if isinstance(roi_examples, list):
            if len(roi_examples) < 1:
                e["warnings"].append("L10: roi_examples is empty")
            for i, roi in enumerate(roi_examples):
                if isinstance(roi, dict):
                    payback = roi.get("payback_months")
                    if payback is not None:
                        try:
                            pm = float(payback)
                            if pm <= 0:
                                e["warnings"].append(f"L10: roi_examples[{i}].payback_months={pm} <= 0")
                            elif pm > 36:
                                e["warnings"].append(f"L10: roi_examples[{i}].payback_months={pm} > 36 (unrealistic)")
                        except (ValueError, TypeError):
                            e["warnings"].append(f"L10: roi_examples[{i}].payback_months not numeric: {payback}")

        # Check currency matches country
        pricing_cur = pricing.get("currency", "")
        expected_cur = COUNTRY_CURRENCY.get(e["country"], "")
        if pricing_cur and expected_cur and pricing_cur != expected_cur:
            e["errors"].append(f"L10: pricing_context.currency='{pricing_cur}' expected '{expected_cur}'")

    def _check_data_integrity(self, e: dict):
        """L11: Data integrity checks."""
        data = e["data"]

        # Check for None items in lists
        for field in ["pain_points", "typical_services", "recommended_functions",
                      "typical_integrations", "industry_faq", "typical_objections",
                      "sales_scripts", "competitors", "aliases"]:
            items = data.get(field, [])
            if isinstance(items, list):
                for i, item in enumerate(items):
                    if item is None:
                        e["warnings"].append(f"L11: {field}[{i}] is None")

        # Check meta completeness
        meta = data.get("meta", {})
        if isinstance(meta, dict):
            for req in ["id", "region", "country", "language", "currency"]:
                if req not in meta or meta[req] is None or str(meta[req]).strip() == "":
                    e["errors"].append(f"L11: meta.{req} is missing or empty")

        # Check that key dict fields have correct structure
        for pp in (data.get("pain_points") or []):
            if isinstance(pp, dict):
                if "solution_hint" not in pp or not pp["solution_hint"]:
                    e["info"].append("L11: pain_point missing solution_hint")
                    break  # Report once

        # Check learnings and success_benchmarks exist
        if "success_benchmarks" not in data:
            e["info"].append("L11: success_benchmarks section missing")
        if "industry_specifics" not in data:
            e["info"].append("L11: industry_specifics section missing")

    def _check_extends(self, e: dict):
        """Check _extends reference."""
        data = e["data"]
        extends = data.get("_extends", "")
        if not extends:
            e["warnings"].append("L8: '_extends' field missing — no base profile reference")
        else:
            base_id = extends.replace("_base/", "")
            if base_id not in self.base_profiles:
                e["errors"].append(f"L8: _extends='{extends}' references non-existent base profile")

    def _check_duplicates(self):
        """L8: Cross-profile — check for identical profiles."""
        for h, paths in self.hashes.items():
            if len(paths) > 1:
                # Group by industry to check if same industry has identical content in diff countries
                by_industry = defaultdict(list)
                for p in paths:
                    parts = p.split("/")
                    if len(parts) == 3:
                        by_industry[parts[2]].append(p)

                for industry, dupes in by_industry.items():
                    if len(dupes) > 1:
                        # Find corresponding entries and add warning to first one
                        for entry in self.all_profiles:
                            key = f"{entry['region']}/{entry['country']}/{entry['industry']}"
                            if key == dupes[0]:
                                others = ", ".join(dupes[1:])
                                entry["warnings"].append(
                                    f"L8: Identical content as: {others} "
                                    f"(possible copy instead of localization)"
                                )
                                break

    def _check_coverage(self):
        """L8: Check that every country has complete industry coverage."""
        # Get expected industries from base
        expected_industries = set(self.base_profiles.keys())

        coverage_gaps = {}
        for country in ALL_COUNTRIES:
            actual = self.coverage.get(country, set())
            missing = expected_industries - actual
            extra = actual - expected_industries
            if missing:
                coverage_gaps[country] = missing

        if coverage_gaps:
            print("\n" + "=" * 70)
            print("COVERAGE GAPS (countries missing industries)")
            print("=" * 70)
            for country, missing in sorted(coverage_gaps.items()):
                print(f"  {country}: missing {len(missing)} — {', '.join(sorted(missing))}")

    def report(self, verbose: bool = False):
        """Print comprehensive report."""
        # Count by level
        level_errors = defaultdict(int)
        level_warnings = defaultdict(int)
        level_info = defaultdict(int)

        profiles_with_errors = 0
        profiles_with_warnings = 0
        total_errors = 0
        total_warnings = 0
        total_info = 0

        for e in self.all_profiles:
            if e["errors"]:
                profiles_with_errors += 1
            if e["warnings"]:
                profiles_with_warnings += 1
            total_errors += len(e["errors"])
            total_warnings += len(e["warnings"])
            total_info += len(e["info"])

            for err in e["errors"]:
                level = err.split(":")[0].strip() if ":" in err else "OTHER"
                level_errors[level] += 1
            for w in e["warnings"]:
                level = w.split(":")[0].strip() if ":" in w else "OTHER"
                level_warnings[level] += 1
            for inf in e["info"]:
                level = inf.split(":")[0].strip() if ":" in inf else "OTHER"
                level_info[level] += 1

        print("\n" + "=" * 70)
        print("DEEP VALIDATION RESULTS")
        print("=" * 70)
        print(f"Total profiles: {len(self.all_profiles)}")
        print(f"Profiles with errors:   {profiles_with_errors}")
        print(f"Profiles with warnings: {profiles_with_warnings}")
        print(f"Total errors:   {total_errors}")
        print(f"Total warnings: {total_warnings}")
        print(f"Total info:     {total_info}")

        print("\n--- Errors by level ---")
        for level in sorted(level_errors.keys()):
            print(f"  {level}: {level_errors[level]}")

        print("\n--- Warnings by level ---")
        for level in sorted(level_warnings.keys()):
            print(f"  {level}: {level_warnings[level]}")

        print("\n--- Info by level ---")
        for level in sorted(level_info.keys()):
            print(f"  {level}: {level_info[level]}")

        # Top warning patterns
        warning_patterns = defaultdict(int)
        for e in self.all_profiles:
            for w in e["warnings"]:
                # Extract pattern up to first specific value
                parts = w.split(":")
                if len(parts) >= 2:
                    pattern = parts[0].strip() + ": " + parts[1].strip().split("=")[0].split("(")[0].split("'")[0].strip()
                else:
                    pattern = w
                warning_patterns[pattern] += 1

        print("\n--- Top 25 warning patterns ---")
        for pattern, count in sorted(warning_patterns.items(), key=lambda x: -x[1])[:25]:
            print(f"  {count:4d}x  {pattern}")

        # Top error patterns
        if total_errors > 0:
            error_patterns = defaultdict(int)
            for e in self.all_profiles:
                for err in e["errors"]:
                    parts = err.split(":")
                    if len(parts) >= 2:
                        pattern = parts[0].strip() + ": " + parts[1].strip().split("=")[0].split("(")[0].split("'")[0].strip()
                    else:
                        pattern = err
                    error_patterns[pattern] += 1

            print("\n--- Error patterns ---")
            for pattern, count in sorted(error_patterns.items(), key=lambda x: -x[1]):
                print(f"  {count:4d}x  {pattern}")

        # List profiles with errors
        error_entries = [e for e in self.all_profiles if e["errors"]]
        if error_entries:
            print(f"\n--- Profiles with errors ({len(error_entries)}) ---")
            for e in error_entries:
                key = f"{e['region']}/{e['country']}/{e['industry']}"
                print(f"  {key}:")
                for err in e["errors"]:
                    print(f"    ERROR: {err}")
                if verbose:
                    for w in e["warnings"][:5]:
                        print(f"    warn:  {w}")

        # Verbose: show all warnings
        if verbose:
            print(f"\n--- All profiles with warnings ---")
            for e in self.all_profiles:
                if e["warnings"] and not e["errors"]:
                    key = f"{e['region']}/{e['country']}/{e['industry']}"
                    print(f"  {key} ({len(e['warnings'])} warnings):")
                    for w in e["warnings"][:8]:
                        print(f"    {w}")
                    if len(e["warnings"]) > 8:
                        print(f"    ... +{len(e['warnings'])-8} more")

        # Duplicate profiles
        dupes = {h: paths for h, paths in self.hashes.items() if len(paths) > 1}
        if dupes:
            print(f"\n--- Identical content groups ({len(dupes)}) ---")
            for h, paths in sorted(dupes.items(), key=lambda x: -len(x[1]))[:20]:
                if len(paths) > 1:
                    # Check if same industry
                    industries = set(p.split("/")[-1] for p in paths)
                    if len(industries) == 1:
                        print(f"  [{list(industries)[0]}] {len(paths)} copies: {', '.join(sorted(paths))}")


def main():
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    base_dir = str(Path(__file__).parent.parent / "config" / "industries")

    validator = DeepValidator(base_dir)
    validator.load_all()
    validator.validate_all()
    validator.report(verbose=verbose)


if __name__ == "__main__":
    main()
