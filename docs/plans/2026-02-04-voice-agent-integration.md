# План: Интеграция голосового агента с системой

**Дата:** 2026-02-04
**Статус:** Готов к реализации

## Цель

Добавить в голосовой агент:
1. Сохранение транскрипта разговора
2. Генерацию анкеты после отключения клиента
3. Сохранение через OutputManager

## События livekit-agents

```python
# Доступные события AgentSession:
UserInputTranscribedEvent  # transcript, is_final
ConversationItemAddedEvent # item (ChatMessage с role и content)
CloseEvent                 # reason (user_disconnected, agent_stopped, etc.)
```

## Изменения в src/voice/consultant.py

### 1. Добавить импорты

```python
from datetime import datetime
from livekit.agents.voice.events import (
    UserInputTranscribedEvent,
    ConversationItemAddedEvent,
    CloseEvent,
)
from src.anketa.extractor import AnketaExtractor
from src.anketa.generator import AnketaGenerator
from src.output import OutputManager
from src.llm.deepseek import DeepSeekClient
```

### 2. Класс для хранения состояния сессии

```python
class VoiceConsultationSession:
    """Хранит состояние голосовой консультации."""

    def __init__(self):
        self.start_time = datetime.now()
        self.dialogue_history: List[Dict[str, str]] = []
        self.company_name: Optional[str] = None

    def add_message(self, role: str, content: str):
        self.dialogue_history.append({
            "role": role,
            "content": content,
            "phase": "voice"  # Единая фаза для голосового режима
        })

    def get_duration_seconds(self) -> float:
        return (datetime.now() - self.start_time).total_seconds()
```

### 3. Обработчики событий в entrypoint()

```python
async def entrypoint(ctx: JobContext):
    # ... существующий код создания session ...

    # Создаём хранилище состояния
    consultation = VoiceConsultationSession()

    # Обработчик транскрипции (запасной, для логирования)
    @session.on("user_input_transcribed")
    def on_transcription(event: UserInputTranscribedEvent):
        if event.is_final:
            logger.info("User said", text=event.transcript[:50])

    # Обработчик сообщений (основной)
    @session.on("conversation_item_added")
    def on_message(event: ConversationItemAddedEvent):
        item = event.item
        if hasattr(item, 'role') and hasattr(item, 'content'):
            role = "user" if item.role == "user" else "assistant"
            content = item.content if isinstance(item.content, str) else str(item.content)
            consultation.add_message(role, content)
            logger.info("Message added", role=role, preview=content[:30])

    # Обработчик завершения
    @session.on("close")
    async def on_close(event: CloseEvent):
        logger.info("Session closing", reason=event.reason)

        if len(consultation.dialogue_history) < 2:
            logger.info("Not enough dialogue to generate anketa")
            return

        await finalize_consultation(consultation)

    # ... остальной код ...
```

### 4. Функция финализации

```python
async def finalize_consultation(consultation: VoiceConsultationSession):
    """Генерирует анкету и сохраняет результаты."""
    logger.info("Finalizing consultation", messages=len(consultation.dialogue_history))

    try:
        # 1. Извлекаем анкету
        deepseek = DeepSeekClient()
        extractor = AnketaExtractor(deepseek)

        anketa = await extractor.extract(
            dialogue_history=consultation.dialogue_history,
            duration_seconds=consultation.get_duration_seconds()
        )

        logger.info("Anketa extracted", company=anketa.company_name)

        # 2. Сохраняем через OutputManager
        output_manager = OutputManager()
        company_dir = output_manager.get_company_dir(
            anketa.company_name,
            consultation.start_time
        )

        # Генерируем markdown
        anketa_md = AnketaGenerator.render_markdown(anketa)
        anketa_json = anketa.model_dump()

        # Сохраняем
        anketa_paths = output_manager.save_anketa(company_dir, anketa_md, anketa_json)
        dialogue_path = output_manager.save_dialogue(
            company_dir=company_dir,
            dialogue_history=consultation.dialogue_history,
            company_name=anketa.company_name,
            client_name=anketa.contact_name or "Клиент",
            duration_seconds=consultation.get_duration_seconds(),
            start_time=consultation.start_time
        )

        logger.info(
            "Consultation saved",
            output_dir=str(company_dir),
            anketa=str(anketa_paths["md"]),
            dialogue=str(dialogue_path)
        )

    except Exception as e:
        logger.error("Failed to finalize consultation", error=str(e))
```

## Результат

После разговора в папке `output/YYYY-MM-DD/{company}_v1/` появятся:
- `anketa.md` — анкета в markdown
- `anketa.json` — анкета в JSON
- `dialogue.md` — транскрипт разговора

## Порядок реализации

1. [ ] Добавить импорты в consultant.py
2. [ ] Создать класс VoiceConsultationSession
3. [ ] Добавить обработчики событий
4. [ ] Добавить функцию finalize_consultation()
5. [ ] Проверить статический метод AnketaGenerator.render_markdown()
6. [ ] Тест: провести разговор и проверить output/

## Зависимости

Уже установлены:
- livekit-agents (события)
- DeepSeekClient (для AnketaExtractor)
- OutputManager (сохранение)
- AnketaExtractor (извлечение)
