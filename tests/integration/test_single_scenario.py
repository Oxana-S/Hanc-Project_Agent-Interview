#!/usr/bin/env python3
"""Быстрый тест одного сценария для проверки v5.0"""
import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Import full test
from test_v5_realtime_scenarios import SCENARIOS, test_scenario

async def main():
    # Тест только первого сценария
    result = await test_scenario(SCENARIOS[0], 1)

    print("\n" + "="*70)
    print("РЕЗУЛЬТАТ:")
    print("="*70)
    print(f"Успех: {result['success']}")
    print(f"Extraction count: {result['extraction_count']}")
    print(f"Fields progress: {result['fields_progress']}")
    print(f"Completion rates: {result['completion_rates']}")
    print(f"Review triggered: {result['review_triggered']}")
    if result['errors']:
        print(f"Ошибки: {result['errors']}")

    return 0 if result['success'] else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
