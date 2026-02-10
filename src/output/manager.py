"""
Output Manager - управление структурой папки output/.

Структура:
    output/
    └── 2026-02-04/                  # Дата теста
        ├── glamour_v1/              # Компания + версия
        │   ├── anketa.md
        │   ├── anketa.json
        │   └── dialogue.md
        └── glamour_v2/              # Повторный тест
            └── ...
"""

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger("output")


class OutputManager:
    """Управляет структурой папки output/."""

    def __init__(self, base_dir: Path = None):
        """
        Инициализация.

        Args:
            base_dir: Базовая папка для output (по умолчанию: output/)
        """
        self.base_dir = base_dir or Path("output")
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def get_company_dir(
        self,
        company_name: str,
        date: Optional[datetime] = None
    ) -> Path:
        """
        Получить путь к папке компании с автоинкрементом версии.

        Args:
            company_name: Название компании
            date: Дата (по умолчанию: сегодня)

        Returns:
            Path: output/2026-02-04/glamour_v1/
        """
        date = date or datetime.now()
        date_str = date.strftime("%Y-%m-%d")
        date_dir = self.base_dir / date_str

        # Создаём папку даты
        date_dir.mkdir(parents=True, exist_ok=True)

        # Создаём slug из названия компании
        company_slug = self._slugify(company_name)

        # Определяем версию
        version = self._get_next_version(date_dir, company_slug)
        company_dir_name = f"{company_slug}_v{version}"

        company_dir = date_dir / company_dir_name
        company_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "Company output directory created",
            path=str(company_dir),
            company=company_name,
            version=version
        )

        return company_dir

    def save_anketa(
        self,
        company_dir: Path,
        anketa_md: str,
        anketa_json: Dict[str, Any]
    ) -> Dict[str, Path]:
        """
        Сохранить анкету в папку компании.

        Args:
            company_dir: Папка компании
            anketa_md: Анкета в формате Markdown
            anketa_json: Анкета в формате JSON

        Returns:
            Dict с путями: {"md": Path, "json": Path}
        """
        md_path = company_dir / "anketa.md"
        json_path = company_dir / "anketa.json"

        # Сохраняем Markdown
        md_path.write_text(anketa_md, encoding="utf-8")

        # Сохраняем JSON (с поддержкой datetime)
        def json_serializer(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        json_path.write_text(
            json.dumps(anketa_json, ensure_ascii=False, indent=2, default=json_serializer),
            encoding="utf-8"
        )

        logger.info(
            "Anketa saved",
            md_path=str(md_path),
            json_path=str(json_path)
        )

        return {"md": md_path, "json": json_path}

    def save_dialogue(
        self,
        company_dir: Path,
        dialogue_history: List[Dict[str, Any]],
        company_name: str,
        client_name: str,
        duration_seconds: float = 0.0,
        start_time: Optional[datetime] = None
    ) -> Path:
        """
        Сохранить лог диалога в папку компании.

        Args:
            company_dir: Папка компании
            dialogue_history: История диалога с метками фаз
            company_name: Название компании
            client_name: Имя клиента
            duration_seconds: Длительность в секундах
            start_time: Время начала

        Returns:
            Path к файлу dialogue.md
        """
        dialogue_md = self._format_dialogue_md(
            dialogue_history=dialogue_history,
            company_name=company_name,
            client_name=client_name,
            duration_seconds=duration_seconds,
            start_time=start_time or datetime.now()
        )

        dialogue_path = company_dir / "dialogue.md"
        dialogue_path.write_text(dialogue_md, encoding="utf-8")

        logger.info(
            "Dialogue saved",
            path=str(dialogue_path),
            turns=len(dialogue_history)
        )

        return dialogue_path

    def _format_dialogue_md(
        self,
        dialogue_history: List[Dict[str, Any]],
        company_name: str,
        client_name: str,
        duration_seconds: float,
        start_time: datetime
    ) -> str:
        """Форматировать диалог в Markdown."""
        lines = [
            f"# Диалог: {company_name}",
            "",
            f"**Дата:** {start_time.strftime('%Y-%m-%d %H:%M:%S')}  ",
            f"**Длительность:** {duration_seconds / 60:.1f} мин  ",
            f"**Сообщений:** {len(dialogue_history)}",
            "",
            "---",
            ""
        ]

        # Группируем сообщения по фазам
        current_phase = None
        phase_icons = {
            "discovery": "🔍 ЗНАКОМСТВО (Discovery)",
            "analysis": "📊 АНАЛИЗ (Analysis)",
            "proposal": "💡 ПРЕДЛОЖЕНИЕ (Proposal)",
            "refinement": "✅ ФИНАЛИЗАЦИЯ (Refinement)",
        }

        for entry in dialogue_history:
            role = entry.get("role", "unknown")
            content = entry.get("content", "")
            phase = entry.get("phase", "discovery")

            # Новая фаза - добавляем заголовок
            if phase != current_phase:
                current_phase = phase
                phase_title = phase_icons.get(phase, f"📌 {phase.upper()}")
                lines.extend([
                    "",
                    f"## {phase_title}",
                    ""
                ])

            # Форматируем сообщение
            if role == "assistant":
                lines.append("**AI-Консультант:**")
            elif role == "user":
                lines.append(f"**Клиент ({client_name}):**")
            else:
                lines.append(f"**{role}:**")

            # Добавляем содержимое с цитированием
            for line in content.strip().split("\n"):
                lines.append(f"> {line}")
            lines.append("")

        return "\n".join(lines)

    def _get_next_version(self, date_dir: Path, company_slug: str) -> int:
        """
        Определить следующую версию для компании.

        Args:
            date_dir: Папка с датой
            company_slug: Slug компании

        Returns:
            Номер версии (1, 2, 3, ...)
        """
        if not date_dir.exists():
            return 1

        # Ищем существующие папки этой компании
        pattern = re.compile(rf"^{re.escape(company_slug)}_v(\d+)$")
        existing_versions = []

        for item in date_dir.iterdir():
            if item.is_dir():
                match = pattern.match(item.name)
                if match:
                    existing_versions.append(int(match.group(1)))

        if not existing_versions:
            return 1

        return max(existing_versions) + 1

    def _slugify(self, text: str) -> str:
        """
        Преобразовать текст в slug для имени папки.

        Args:
            text: Исходный текст (например: "Салон красоты Glamour")

        Returns:
            Slug (например: "salon_krasoty_glamour")
        """
        # Нормализуем Unicode
        text = unicodedata.normalize("NFKD", text)

        # Приводим к нижнему регистру
        text = text.lower()

        # Транслитерация кириллицы
        translit_map = {
            'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e',
            'ё': 'e', 'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k',
            'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
            'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts',
            'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '',
            'э': 'e', 'ю': 'yu', 'я': 'ya'
        }

        result = []
        for char in text:
            if char in translit_map:
                result.append(translit_map[char])
            elif char.isalnum():
                result.append(char)
            elif char in ' -_':
                result.append('_')

        # Убираем множественные подчёркивания
        slug = '_'.join(filter(None, ''.join(result).split('_')))

        # Ограничиваем длину
        return slug[:50] if slug else "unnamed"
