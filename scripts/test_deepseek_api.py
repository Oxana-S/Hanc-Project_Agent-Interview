#!/usr/bin/env python3
"""
Диагностика DeepSeek API - проверка подключения и лимитов.
"""

import os
import sys
import asyncio
import httpx
from dotenv import load_dotenv

# Добавляем корень проекта
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

API_KEY = os.getenv("DEEPSEEK_API_KEY")
ENDPOINT = os.getenv("DEEPSEEK_API_ENDPOINT", "https://api.deepseek.com/v1")
MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


async def test_api():
    """Тест API с простым запросом."""
    print("=" * 60)
    print("ДИАГНОСТИКА DEEPSEEK API")
    print("=" * 60)

    if not API_KEY:
        print("❌ DEEPSEEK_API_KEY не установлен в .env")
        return

    print(f"✓ API Key: {API_KEY[:8]}...{API_KEY[-4:]}")
    print(f"✓ Endpoint: {ENDPOINT}")
    print(f"✓ Model: {MODEL}")
    print("-" * 60)

    # Простой тестовый запрос
    url = f"{ENDPOINT}/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    # Минимальный запрос (увеличен для reasoner)
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": "Ответь одним словом: 2+2=?"}
        ],
        "temperature": 0.1,
        "max_tokens": 500  # Для reasoner нужно больше
    }

    print("\n📤 Отправляю тестовый запрос...")
    print(f"   Prompt: 'Ответь одним словом: 2+2=?'")

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(url, headers=headers, json=payload)

            print(f"\n📥 HTTP Status: {response.status_code}")
            print(f"   Headers:")

            # Проверяем rate limit headers
            for key in response.headers:
                if 'rate' in key.lower() or 'limit' in key.lower() or 'remaining' in key.lower():
                    print(f"   - {key}: {response.headers[key]}")

            if response.status_code == 200:
                data = response.json()

                print("\n✅ ОТВЕТ ПОЛУЧЕН:")
                print("-" * 40)

                # Извлекаем данные
                choice = data.get("choices", [{}])[0]
                content = choice.get("message", {}).get("content", "")
                finish_reason = choice.get("finish_reason", "unknown")
                usage = data.get("usage", {})

                print(f"   Content: '{content}'")
                print(f"   Content length: {len(content)}")
                print(f"   Finish reason: {finish_reason}")
                print(f"\n📊 Token Usage:")
                print(f"   - Prompt tokens: {usage.get('prompt_tokens', 'N/A')}")
                print(f"   - Completion tokens: {usage.get('completion_tokens', 'N/A')}")
                print(f"   - Total tokens: {usage.get('total_tokens', 'N/A')}")

                if not content:
                    print("\n⚠️  ВНИМАНИЕ: Контент пустой!")
                    print(f"   Полный ответ API: {data}")

            else:
                print(f"\n❌ ОШИБКА API:")
                print(f"   Status: {response.status_code}")
                print(f"   Response: {response.text}")

        except httpx.TimeoutException:
            print("\n❌ TIMEOUT: Запрос превысил 60 секунд")
        except Exception as e:
            print(f"\n❌ ОШИБКА: {type(e).__name__}: {e}")

    # Тест с большим контекстом (как в extraction)
    print("\n" + "=" * 60)
    print("ТЕСТ С БОЛЬШИМ КОНТЕКСТОМ (симуляция extraction)")
    print("=" * 60)

    # Создаём большой промпт как в реальном extraction
    long_dialogue = """
ASSISTANT: Здравствуйте! Расскажите о вашей компании.
USER: Добрый день. Я представляю компанию «ГрузовикОнлайн» — мы занимаемся логистикой.
ASSISTANT: Отлично! Какие задачи хотите автоматизировать?
USER: Нужно автоматизировать информирование клиентов о статусе доставки.
""" * 5  # Умножаем для увеличения размера

    payload_large = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "Извлеки название компании из диалога. Верни только JSON: {\"company_name\": \"...\"}"},
            {"role": "user", "content": long_dialogue}
        ],
        "temperature": 0.1,
        "max_tokens": 500
    }

    print(f"\n📤 Отправляю большой запрос...")
    print(f"   Размер контекста: ~{len(long_dialogue)} символов")

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            response = await client.post(url, headers=headers, json=payload_large)

            print(f"\n📥 HTTP Status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                choice = data.get("choices", [{}])[0]
                content = choice.get("message", {}).get("content", "")
                finish_reason = choice.get("finish_reason", "unknown")
                usage = data.get("usage", {})

                print(f"\n✅ ОТВЕТ:")
                print(f"   Content: '{content[:200]}{'...' if len(content) > 200 else ''}'")
                print(f"   Content length: {len(content)}")
                print(f"   Finish reason: {finish_reason}")
                print(f"\n📊 Token Usage:")
                print(f"   - Prompt tokens: {usage.get('prompt_tokens', 'N/A')}")
                print(f"   - Completion tokens: {usage.get('completion_tokens', 'N/A')}")
                print(f"   - Total tokens: {usage.get('total_tokens', 'N/A')}")

                if not content:
                    print("\n⚠️  ВНИМАНИЕ: Контент пустой!")
                    print(f"   Finish reason: {finish_reason}")
                    print(f"   Полный response: {data}")
            else:
                print(f"\n❌ ОШИБКА: {response.status_code}")
                print(f"   {response.text}")

        except Exception as e:
            print(f"\n❌ ОШИБКА: {type(e).__name__}: {e}")

    print("\n" + "=" * 60)
    print("ДИАГНОСТИКА ЗАВЕРШЕНА")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_api())
