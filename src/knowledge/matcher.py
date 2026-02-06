"""
Industry Matcher - determines industry from text using aliases.

v1.0: Initial implementation with fuzzy matching support
"""

import re
from typing import Dict, List, Optional, Tuple

import structlog

from .loader import IndustryProfileLoader

logger = structlog.get_logger("knowledge")


class IndustryMatcher:
    """
    Определяет отрасль из текста диалога.

    Использует aliases из профилей отраслей для сопоставления.
    """

    def __init__(self, loader: Optional[IndustryProfileLoader] = None):
        """
        Инициализация matcher'а.

        Args:
            loader: Загрузчик профилей (создаётся если не передан)
        """
        self.loader = loader or IndustryProfileLoader()
        self._alias_map: Dict[str, str] = {}  # alias -> industry_id
        self._loaded = False

    def _build_alias_map(self):
        """Построить карту aliases -> industry_id."""
        if self._loaded:
            return

        index = self.loader.load_index()

        for industry_id, entry in index.industries.items():
            # Добавляем aliases из индекса
            for alias in entry.aliases:
                self._alias_map[alias.lower()] = industry_id

            # Также добавляем само название
            self._alias_map[entry.name.lower()] = industry_id

            # Загружаем полный профиль для дополнительных aliases
            profile = self.loader.load_profile(industry_id)
            if profile:
                for alias in profile.aliases:
                    self._alias_map[alias.lower()] = industry_id

        self._loaded = True
        logger.info("Alias map built", total_aliases=len(self._alias_map))

    def _get_russian_stem(self, word: str) -> str:
        """
        Получить примерный корень русского слова (без морфологической библиотеки).

        Убирает типичные русские окончания для matching.
        """
        # Типичные окончания существительных/прилагательных
        endings = [
            'ками', 'ками', 'ость', 'ение', 'ание',
            'ами', 'ями', 'ией', 'ием', 'ого', 'его',
            'ов', 'ев', 'ей', 'ий', 'ый', 'ой', 'ая',
            'ие', 'ые', 'ое', 'ую', 'юю', 'ах', 'ях',
            'ом', 'ем', 'им', 'ым', 'их', 'ых',
            'и', 'ы', 'а', 'я', 'у', 'ю', 'е', 'о'
        ]

        word_lower = word.lower()
        for ending in endings:
            if len(word_lower) > len(ending) + 3 and word_lower.endswith(ending):
                return word_lower[:-len(ending)]

        return word_lower

    def _make_word_pattern(self, word: str) -> str:
        """
        Создать паттерн для поиска слова с учётом Unicode (кириллица).

        Стандартный \\b не работает с кириллицей, поэтому используем
        lookbehind/lookahead с явным указанием границ слов.

        Для русских слов >= 6 символов используем stem matching,
        чтобы учесть морфологию (грузоперевозки -> грузоперевозками).
        """
        # Проверяем, русское ли слово
        is_russian = bool(re.search(r'[а-яё]', word.lower()))

        if len(word) >= 6 and is_russian:
            # Получаем корень и ищем слова с таким корнем
            stem = self._get_russian_stem(word)
            escaped_stem = re.escape(stem)
            # Stem + любые русские буквы (0-6 символов для окончаний)
            return r'(?<![а-яёa-z0-9])' + escaped_stem + r'[а-яё]{0,6}(?![а-яёa-z0-9])'
        else:
            # Точное совпадение для коротких или нерусских слов
            escaped = re.escape(word)
            return r'(?<![а-яёa-z0-9])' + escaped + r'(?![а-яёa-z0-9])'

    def detect(self, text: str) -> Optional[str]:
        """
        Определить отрасль из текста.

        Args:
            text: Текст для анализа (сообщение клиента, диалог и т.д.)

        Returns:
            ID отрасли или None если не определена
        """
        self._build_alias_map()

        text_lower = text.lower()

        # Считаем совпадения для каждой отрасли
        scores: Dict[str, int] = {}

        for alias, industry_id in self._alias_map.items():
            # Ищем как целое слово (с поддержкой кириллицы)
            pattern = self._make_word_pattern(alias)
            matches = len(re.findall(pattern, text_lower, re.IGNORECASE))

            if matches > 0:
                scores[industry_id] = scores.get(industry_id, 0) + matches

        if not scores:
            logger.debug("No industry detected", text_preview=text[:100])
            return None

        # Возвращаем отрасль с максимальным счётом
        best_industry = max(scores, key=scores.get)

        logger.debug(
            "Industry detected",
            industry=best_industry,
            score=scores[best_industry],
            all_scores=scores
        )

        return best_industry

    def detect_with_confidence(self, text: str) -> Tuple[Optional[str], float]:
        """
        Определить отрасль с уровнем уверенности.

        Args:
            text: Текст для анализа

        Returns:
            Tuple (industry_id, confidence) где confidence от 0.0 до 1.0
        """
        self._build_alias_map()

        text_lower = text.lower()
        scores: Dict[str, int] = {}

        for alias, industry_id in self._alias_map.items():
            pattern = self._make_word_pattern(alias)
            matches = len(re.findall(pattern, text_lower, re.IGNORECASE))

            if matches > 0:
                scores[industry_id] = scores.get(industry_id, 0) + matches

        if not scores:
            return None, 0.0

        # Сортируем по убыванию
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        best_industry, best_score = sorted_scores[0]

        # Вычисляем confidence
        # Если только одна отрасль — высокая уверенность
        # Если несколько близких — ниже уверенность
        if len(sorted_scores) == 1:
            confidence = min(1.0, best_score * 0.3)  # Cap at 1.0
        else:
            second_score = sorted_scores[1][1]
            # Разница между первым и вторым
            diff_ratio = (best_score - second_score) / best_score if best_score > 0 else 0
            confidence = min(1.0, (best_score * 0.2) + (diff_ratio * 0.5))

        return best_industry, confidence

    def get_all_aliases(self, industry_id: str) -> List[str]:
        """
        Получить все aliases для отрасли.

        Args:
            industry_id: ID отрасли

        Returns:
            Список всех aliases
        """
        self._build_alias_map()

        return [
            alias for alias, ind_id in self._alias_map.items()
            if ind_id == industry_id
        ]

    def find_mentions(self, text: str, industry_id: str) -> List[str]:
        """
        Найти все упоминания отрасли в тексте.

        Args:
            text: Текст для анализа
            industry_id: ID отрасли

        Returns:
            Список найденных aliases в тексте
        """
        self._build_alias_map()

        text_lower = text.lower()
        found = []

        for alias, ind_id in self._alias_map.items():
            if ind_id != industry_id:
                continue

            pattern = self._make_word_pattern(alias)
            if re.search(pattern, text_lower, re.IGNORECASE):
                found.append(alias)

        return found

    def reload(self):
        """Перезагрузить данные."""
        self._alias_map.clear()
        self._loaded = False
        self.loader.reload()
