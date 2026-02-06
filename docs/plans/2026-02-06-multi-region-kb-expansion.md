# Multi-Region Knowledge Base Expansion

**Date:** 2026-02-06
**Status:** ✅ Implemented
**Author:** Claude + User
**Implementation Date:** 2026-02-07

## Overview

Расширение Knowledge Base для поддержки мультирегионального/мультиязычного развёртывания с полной адаптацией профилей отраслей под локальные рынки.

## Goals

1. **Больше клиентов** — охватить бизнесы в EU, NA, LATAM, MENA, SEA
2. **Качество консультаций** — глубже понимать локальные боли, давать точные рекомендации
3. **Автономность агента** — агент сам подбирает решения на основе региональных данных

## Architecture

### Directory Structure

```
config/industries/
├── _index.yaml                    # Глобальный индекс
├── _countries.yaml                # Коды стран, языки, телефонные коды
│
├── _base/                         # Базовые профили (шаблоны)
│   ├── automotive.yaml
│   ├── healthcare.yaml
│   └── ...
│
├── eu/
│   ├── de/                        # Германия
│   │   ├── _meta.yaml            # lang: de, phone: +49, currency: EUR
│   │   ├── automotive.yaml
│   │   └── healthcare.yaml
│   ├── ch/                        # Швейцария
│   ├── at/                        # Австрия
│   ├── fr/                        # Франция
│   ├── it/                        # Италия
│   ├── es/                        # Испания
│   ├── pt/                        # Португалия
│   ├── ro/                        # Румыния
│   ├── bg/                        # Болгария
│   ├── hu/                        # Венгрия
│   └── gr/                        # Греция
│
├── na/                            # North America
│   ├── us/                        # США
│   └── ca/                        # Канада
│
├── latam/
│   ├── br/                        # Бразилия
│   ├── ar/                        # Аргентина
│   └── mx/                        # Мексика
│
├── mena/
│   ├── ae/                        # ОАЭ
│   ├── sa/                        # Саудовская Аравия
│   └── qa/                        # Катар
│
├── sea/
│   ├── cn/                        # Китай
│   ├── vn/                        # Вьетнам
│   └── id/                        # Индонезия
│
└── ru/                            # Russia (legacy, lowest priority)
    └── ...
```

### Inheritance Model

Country profiles extend base profiles:

```yaml
# eu/de/automotive.yaml
_extends: _base/automotive

# Override only what differs
pain_points:
  - description: "Kunden rufen wegen Reparaturstatus an"
    severity: high

typical_integrations:
  - name: "SAP Business One"
  - name: "DATEV"
```

## Extended Profile Schema (v2.0)

### New Meta Fields

```yaml
meta:
  id: automotive
  region: eu
  country: de
  language: de
  languages: [de, en]
  phone_codes: ["+49"]
  currency: EUR
  timezone: "Europe/Berlin"
  compliance: [GDPR, KFZ-Verordnung]
```

### New Content Fields

```yaml
# Sales Scripts
sales_scripts:
  - trigger: "price_question"
    situation: "Клиент спрашивает цену в лоб"
    script: |
      Der Preis hängt von mehreren Faktoren ab...
    goal: "Перевести в диалог"
    effectiveness: 0.72

# Competitors
competitors:
  - name: "Parloa"
    website: "parloa.com"
    positioning: "Enterprise voice AI"
    market_share: "~15% DACH"
    strengths: ["Brand recognition", "SAP integration"]
    weaknesses: ["Expensive", "Long implementation"]
    our_differentiation: "2-day setup, 3x cheaper"

# Pricing Context
pricing_context:
  currency: EUR
  typical_budget_range: [3000, 12000]
  entry_point: 2500
  enterprise_threshold: 15000
  roi_examples:
    - scenario: "1 FTE savings"
      monthly_cost: 4500
      monthly_savings: 6000
      payback_months: 1
  value_anchors:
    - "Ein Mitarbeiter kostet ~6000€/Monat"

# Market Context
market_context:
  market_size: "€2.3B DACH automotive service"
  growth_rate: "8% YoY"
  key_trends:
    - "Electrification driving service complexity"
  seasonality:
    high: ["March-April", "October-November"]
    low: ["July-August"]
```

## Country Detection

Combination approach:

1. **Phone code** — primary signal (+49 → Germany)
2. **Language detection** — from dialogue text
3. **Manual override** — user can switch

```python
class CountryDetector:
    def detect(
        self,
        phone: Optional[str] = None,
        dialogue_text: Optional[str] = None,
        explicit_country: Optional[str] = None
    ) -> Tuple[str, str]:  # (region, country)
```

## LLM Profile Generator

```python
# scripts/generate_profiles.py

class ProfileGenerator:
    def generate(
        self,
        region: str,
        country: str,
        industry: str,
        base_profile: Optional[dict] = None
    ) -> IndustryProfile:
        """Generate profile via LLM with validation."""

    def generate_batch(
        self,
        region: str,
        countries: List[str],
        industries: List[str]
    ) -> Dict[str, List[IndustryProfile]]:
        """Batch generation for region."""
```

### Generation Prompt

```
You are an expert in {industry} industry in {country}.
Generate a detailed industry profile in {language}.

Base profile (adapt, don't copy):
{base_profile_yaml}

Country context:
- Currency: {currency}
- Major cities: {cities}
- Key regulations: {regulations}
- Business culture: {culture_notes}

Generate YAML with:
1. pain_points (5-7, localized problems)
2. typical_services (8-10, local terms)
3. competitors (3-5 local/regional players)
4. pricing_context (local currency, local rates)
5. sales_scripts (3-5, in {language})
6. typical_integrations (local systems)

Output valid YAML only.
```

## Implementation Plan

| Phase | Tasks | Deliverable | Status |
|-------|-------|-------------|--------|
| 1. Schema | Update models.py with new dataclasses | Extended IndustryProfile | ✅ Done |
| 2. Loader | Regional structure support + inheritance | `load_regional_profile()` | ✅ Done |
| 3. Detector | Country detection by phone + language | CountryDetector class | ✅ Done |
| 4. Generator | LLM profile generation script | `scripts/generate_profiles.py` | ✅ Done |
| 5. EU Wave | Generate profiles for 11 EU countries | ~50 profiles | 🟡 1/50 (test) |
| 6. NA/LATAM | USA, Canada, Brazil, Argentina | ~20 profiles | ⏳ Pending |
| 7. MENA/SEA | UAE, Saudi Arabia, China, Vietnam | ~20 profiles | ⏳ Pending |
| 8. Tests | Unit + integration tests | 100% coverage | ✅ 25/25 pass |

## Implementation Details

### Files Created/Modified

| File | Description |
|------|-------------|
| `src/knowledge/models.py` | +6 new models: SalesScript, Competitor, ROIExample, PricingContext, Seasonality, MarketContext |
| `src/knowledge/loader.py` | +`load_regional_profile()`, +`_merge_profiles()`, +region/country helpers |
| `src/knowledge/country_detector.py` | NEW: CountryDetector class with phone/language detection |
| `src/knowledge/__init__.py` | Exports for new models and CountryDetector |
| `scripts/generate_profiles.py` | NEW: LLM-based profile generator |
| `config/industries/_countries.yaml` | NEW: 22 countries metadata |
| `config/industries/_base/` | NEW: 8 base profiles for inheritance |
| `config/industries/eu/de/automotive.yaml` | NEW: Test profile (German automotive) |

### Usage Examples

```python
# Load regional profile
from src.knowledge.loader import IndustryProfileLoader
loader = IndustryProfileLoader()
profile = loader.load_regional_profile("eu", "de", "automotive")

# Detect country
from src.knowledge import get_country_detector
detector = get_country_detector()
region, country = detector.detect(phone="+49 151 12345678")
# → ("eu", "de")

# Generate profiles (CLI)
python scripts/generate_profiles.py --region eu --country de --industry automotive
python scripts/generate_profiles.py --wave1  # All priority countries
```

## Priority Countries (Wave 1)

1. 🇩🇪 **Germany** — main EU market
2. 🇺🇸 **USA** — main NA market
3. 🇦🇪 **UAE** — main MENA market
4. 🇧🇷 **Brazil** — main LATAM market

## Success Criteria

- [x] Schema extended with v2.0 models (SalesScript, Competitor, PricingContext, MarketContext)
- [x] Regional directory structure created (6 regions, 22 countries)
- [x] Profile inheritance working (`_extends` field)
- [x] CountryDetector working (phone + language detection)
- [x] LLM profile generator working (tested with DE/automotive)
- [x] All existing tests pass (25/25)
- [ ] 90+ industry profiles across 20+ countries
- [ ] ProfileValidator passes all profiles at ≥70% completeness
- [ ] Voice agent receives localized context

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| LLM generates inaccurate data | Validation + human review for wave 1 |
| Too many profiles to maintain | Inheritance reduces duplication |
| Detection errors | Fallback to manual selection |

---

*Approved for implementation: 2026-02-06*
