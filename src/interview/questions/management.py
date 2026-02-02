"""
Структура вопросов для голосового интервью
Паттерн: MANAGEMENT (агент для сотрудников компании)
"""

from typing import List, Dict, Optional
from dataclasses import dataclass
from enum import Enum


class QuestionType(Enum):
    OPEN = "open"
    CHOICE = "choice"
    MULTI_CHOICE = "multi_choice"
    NUMERIC = "numeric"
    TEXT = "text"


class QuestionPriority(Enum):
    REQUIRED = "required"
    IMPORTANT = "important"
    OPTIONAL = "optional"


@dataclass
class Question:
    id: str
    section: str
    text: str
    question_type: QuestionType
    priority: QuestionPriority
    validation_rules: Optional[Dict] = None
    follow_up_questions: Optional[List['Question']] = None
    examples: Optional[List[str]] = None
    min_answer_length: int = 15


# ==================================================
# СЕКЦИЯ 1: БАЗОВАЯ ИНФОРМАЦИЯ
# ==================================================

SECTION_1_QUESTIONS = [
    Question(
        id="1.1",
        section="Базовая информация",
        text="Начнём с основ. Как называется ваша компания?",
        question_type=QuestionType.TEXT,
        priority=QuestionPriority.REQUIRED,
        min_answer_length=2
    ),
    
    Question(
        id="1.2",
        section="Базовая информация",
        text="""В какой отрасли работает ваша компания? Выберите один из вариантов:
        1 - Медицина и Здоровье
        2 - Красота и Wellness
        3 - Недвижимость
        4 - Финансы и Страхование
        5 - IT и Технологии
        6 - Розничная торговля
        7 - HoReCa (отели, рестораны, кафе)
        8 - Образование
        9 - Логистика и Доставка
        10 - Производство
        11 - Другая отрасль
        
        Просто назовите номер или название отрасли.""",
        question_type=QuestionType.CHOICE,
        priority=QuestionPriority.REQUIRED,
        validation_rules={
            "options": [
                "Медицина / Здоровье",
                "Красота / Wellness",
                "Недвижимость",
                "Финансы / Страхование",
                "IT / Технологии",
                "Розничная торговля",
                "HoReCa",
                "Образование",
                "Логистика / Доставка",
                "Производство",
                "Другое"
            ]
        }
    ),
    
    Question(
        id="1.3",
        section="Базовая информация",
        text="На каком языке агент будет общаться с сотрудниками? Русский, немецкий или английский?",
        question_type=QuestionType.CHOICE,
        priority=QuestionPriority.REQUIRED,
        validation_rules={
            "options": ["Русский", "Немецкий", "Английский"]
        }
    ),
    
    Question(
        id="1.4",
        section="Базовая информация",
        text="""Теперь самое важное. Опишите своими словами, что именно должен делать голосовой агент для ваших сотрудников? 
        
        Расскажите подробно - какие задачи он должен решать, какие процессы автоматизировать, что упростить в работе?""",
        question_type=QuestionType.OPEN,
        priority=QuestionPriority.REQUIRED,
        min_answer_length=30,
        examples=[
            "Отвечать на вопросы сотрудников о политиках компании, помогать с оформлением отпусков, собирать заявки на IT-поддержку",
            "Проводить первичный скрининг кандидатов, назначать собеседования, собирать документы от новых сотрудников",
            "Управлять расписанием руководителя, фильтровать входящие звонки, напоминать о встречах"
        ]
    )
]


# ==================================================
# СЕКЦИЯ 2: СТРУКТУРА И ФУНКЦИИ
# ==================================================

SECTION_2_QUESTIONS = [
    Question(
        id="2.1",
        section="Структура и функции",
        text="""Какую основную функцию управления будет выполнять агент? Выберите наиболее подходящий вариант:
        
        1 - HR Рекрутинг (первичный отбор кандидатов, скрининг резюме, назначение собеседований)
        2 - HR Онбординг (помощь новым сотрудникам, ответы на вопросы, сбор документов)
        3 - HR Справочная для сотрудников (отпуска, больничные, справки, внутренние политики)
        4 - Секретарь руководителя (управление звонками и расписанием, фильтрация контактов)
        5 - Координация задач (распределение задач, напоминания о дедлайнах, статусы проектов)
        6 - Согласования (заявки на отпуск, закупки, командировки, документы на подпись)
        7 - IT поддержка сотрудников (пароли, доступы, проблемы с техникой, заявки)
        8 - Сбор данных и опросы (внутренние опросы, сбор отчётов, обратная связь)
        9 - Закупки и поставщики (работа с поставщиками, статусы заказов, согласование счетов)
        10 - Диспетчеризация (распределение выездов, координация бригад, логистика)
        11 - Другое
        
        Назовите номер или функцию.""",
        question_type=QuestionType.CHOICE,
        priority=QuestionPriority.REQUIRED,
        validation_rules={
            "options": [
                "HR Рекрутинг",
                "HR Онбординг",
                "HR Справочная",
                "Секретарь руководителя",
                "Координация задач",
                "Согласования",
                "IT поддержка",
                "Сбор данных и опросы",
                "Закупки и поставщики",
                "Диспетчеризация",
                "Другое"
            ]
        }
    ),
    
    Question(
        id="2.2.1",
        section="Структура и функции",
        text="""Сколько сотрудников в вашей компании?
        
        1 - До 20 сотрудников
        2 - 20-100 сотрудников
        3 - 100-500 сотрудников
        4 - Более 500 сотрудников""",
        question_type=QuestionType.CHOICE,
        priority=QuestionPriority.REQUIRED,
        validation_rules={
            "options": ["До 20", "20-100", "100-500", "Более 500"]
        }
    ),
    
    Question(
        id="2.2.2",
        section="Структура и функции",
        text="""Какие отделы или подразделения есть в компании? Можете назвать несколько:
        
        - Руководство / Топ-менеджмент
        - Продажи
        - Маркетинг
        - Финансы / Бухгалтерия
        - HR / Кадры
        - IT / Техподдержка
        - Производство
        - Склад / Логистика
        - Юридический
        - Другие отделы
        
        Перечислите все имеющиеся отделы.""",
        question_type=QuestionType.MULTI_CHOICE,
        priority=QuestionPriority.IMPORTANT,
        min_answer_length=10
    ),
    
    Question(
        id="2.2.3",
        section="Структура и функции",
        text="Для какого конкретно отдела создаётся этот агент?",
        question_type=QuestionType.TEXT,
        priority=QuestionPriority.REQUIRED,
        min_answer_length=3,
        examples=["HR отдел", "IT поддержка", "Приёмная генерального директора", "Отдел закупок"]
    ),
    
    Question(
        id="2.2.4",
        section="Структура и функции",
        text="Кто будет 'владельцем' агента? То есть, кто будет отвечать за его работу, обновления и обучение? Назовите должность и имя, если возможно.",
        question_type=QuestionType.TEXT,
        priority=QuestionPriority.REQUIRED,
        min_answer_length=5,
        examples=["HR-директор Иванова Мария", "Руководитель IT отдела Петров Сергей", "Офис-менеджер Смирнова Анна"]
    ),
    
    Question(
        id="2.3.1",
        section="Структура и функции",
        text="""Кто именно будет общаться с агентом? Можете выбрать несколько вариантов:
        
        - Все сотрудники компании
        - Только определённые отделы
        - Руководители и менеджеры
        - Кандидаты на вакансии
        - Новые сотрудники на испытательном сроке
        - Поставщики и подрядчики
        - Другие пользователи
        
        Назовите все категории пользователей.""",
        question_type=QuestionType.MULTI_CHOICE,
        priority=QuestionPriority.REQUIRED,
        min_answer_length=10
    ),
    
    Question(
        id="2.3.2",
        section="Структура и функции",
        text="""Сколько примерно обращений к агенту ожидается в день?
        
        1 - До 10 обращений
        2 - 10-50 обращений
        3 - 50-100 обращений
        4 - Более 100 обращений""",
        question_type=QuestionType.CHOICE,
        priority=QuestionPriority.IMPORTANT,
        validation_rules={
            "options": ["До 10", "10-50", "50-100", "Более 100"]
        }
    ),
    
    Question(
        id="2.3.3",
        section="Структура и функции",
        text="""Теперь очень важный момент. Назовите 3-5 самых типичных вопросов или запросов, с которыми к агенту будут обращаться сотрудники.
        
        Примеры для HR:
        - Сколько дней отпуска осталось?
        - Как оформить командировку?
        - Когда зарплата?
        
        Примеры для IT:
        - Забыл пароль
        - Не работает принтер
        - Нужен доступ к системе
        
        Расскажите о ваших типичных запросах подробно.""",
        question_type=QuestionType.OPEN,
        priority=QuestionPriority.REQUIRED,
        min_answer_length=40,
        examples=[
            "Сотрудники часто спрашивают: где найти справку о доходах, как записаться к врачу по ДМС, когда следующий корпоратив, как заказать пропуск на парковку, куда обратиться с предложением"
        ]
    ),
    
    Question(
        id="2.3.4",
        section="Структура и функции",
        text="""Есть ли VIP-пользователи, которых нужно обрабатывать приоритетно? 
        
        Например, руководство компании или ключевые специалисты?
        
        Если да - назовите кто именно. Если нет - скажите 'нет'.""",
        question_type=QuestionType.TEXT,
        priority=QuestionPriority.IMPORTANT,
        min_answer_length=2,
        examples=["Генеральный директор и его заместители", "Топ-менеджмент", "Нет, все равны"]
    ),
    
    Question(
        id="2.4",
        section="Структура и функции",
        text="""Какие системы и инструменты вы используете в компании? Это нужно для возможных интеграций.
        
        Например:
        - HRIS системы (SAP, Personio, BambooHR)
        - Календари (Google Calendar, Outlook)
        - ERP системы (1С, SAP)
        - Трекеры задач (Trello, Jira, Asana)
        - Мессенджеры (Slack, Microsoft Teams)
        - Другие системы
        
        Перечислите все используемые системы.""",
        question_type=QuestionType.OPEN,
        priority=QuestionPriority.IMPORTANT,
        min_answer_length=10,
        examples=[
            "Используем 1С для учёта, Google Calendar для расписания, Trello для задач, Slack для общения",
            "У нас SAP для всего HR, Outlook для почты и календаря, Teams для мессенджера"
        ]
    ),
    
    Question(
        id="2.5",
        section="Структура и функции",
        text="Как агент будет представляться сотрудникам? Придумайте имя для вашего голосового помощника.",
        question_type=QuestionType.TEXT,
        priority=QuestionPriority.REQUIRED,
        min_answer_length=1,
        examples=["Анна", "Максим", "Ассистент HR", "Алиса", "Помощник"]
    ),
    
    Question(
        id="2.6",
        section="Структура и функции",
        text="""Какой тон общения должен быть у агента?
        
        1 - Формальный (обращение на "Вы", официальный стиль)
        2 - Дружелюбный (обращение на "ты", неформальный стиль)
        3 - Адаптивный (подстраивается под стиль собеседника)""",
        question_type=QuestionType.CHOICE,
        priority=QuestionPriority.REQUIRED,
        validation_rules={
            "options": ["Формальный", "Дружелюбный", "Адаптивный"]
        }
    ),
    
    Question(
        id="2.7",
        section="Структура и функции",
        text="""В какие часы агент должен быть доступен?
        
        Например: "Понедельник-пятница с 9 до 18, выходные не работает"
        
        Или: "Круглосуточно доступен"
        
        Расскажите график работы агента.""",
        question_type=QuestionType.TEXT,
        priority=QuestionPriority.REQUIRED,
        min_answer_length=10
    ),
    
    Question(
        id="2.8",
        section="Структура и функции",
        text="""В каких случаях агент должен переводить обращение на живого сотрудника?
        
        Например:
        - По запросу пользователя
        - Если агент не знает ответа
        - Конфиденциальные вопросы
        - Обращения от руководства (VIP)
        - Конфликтные ситуации
        
        Назовите все случаи, когда нужна переадресация.""",
        question_type=QuestionType.OPEN,
        priority=QuestionPriority.REQUIRED,
        min_answer_length=20,
        examples=[
            "Переводить на человека при запросе сотрудника, при личных конфиденциальных вопросах, при обращениях от руководства, если вопрос требует принятия решения"
        ]
    )
]


# ==================================================
# СЕКЦИЯ 3: ИНТЕГРАЦИИ
# ==================================================

SECTION_3_QUESTIONS = [
    # EMAIL
    Question(
        id="3.1",
        section="Интеграции",
        text="Нужно ли агенту отправлять email-письма сотрудникам? Да или нет?",
        question_type=QuestionType.CHOICE,
        priority=QuestionPriority.REQUIRED,
        validation_rules={"options": ["Да", "Нет"]}
    ),
    
    Question(
        id="3.1.1",
        section="Интеграции",
        text="С какого email-адреса агент будет отправлять письма? Назовите полный адрес.",
        question_type=QuestionType.TEXT,
        priority=QuestionPriority.REQUIRED,
        min_answer_length=5,
        validation_rules={"pattern": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"}
    ),
    
    Question(
        id="3.1.2",
        section="Интеграции",
        text="""Для чего агент будет отправлять email? Можете выбрать несколько вариантов:
        
        - Резюме разговора
        - Инструкции и документы
        - Напоминания о встречах
        - Подтверждение заявок
        - Другое
        
        Перечислите все нужные варианты.""",
        question_type=QuestionType.MULTI_CHOICE,
        priority=QuestionPriority.REQUIRED,
        min_answer_length=10
    ),
    
    # КАЛЕНДАРЬ
    Question(
        id="3.2",
        section="Интеграции",
        text="Нужна ли интеграция с календарём для записи встреч и собеседований? Используете ли вы cal.com или похожую систему?",
        question_type=QuestionType.CHOICE,
        priority=QuestionPriority.REQUIRED,
        validation_rules={"options": ["Да", "Нет"]}
    ),
    
    Question(
        id="3.2.1",
        section="Интеграции",
        text="Назовите ссылку на ваш cal.com Event. Это должна быть ссылка вида https://cal.com/ваша-компания/тип-встречи",
        question_type=QuestionType.TEXT,
        priority=QuestionPriority.REQUIRED,
        min_answer_length=10,
        validation_rules={"pattern": r"^https://cal\.com/.+"}
    ),
    
    Question(
        id="3.2.2",
        section="Интеграции",
        text="""Какая стандартная длительность встречи?
        
        1 - 15 минут
        2 - 30 минут
        3 - 45 минут
        4 - 60 минут
        5 - Другая длительность
        
        Выберите вариант или назовите свою длительность.""",
        question_type=QuestionType.CHOICE,
        priority=QuestionPriority.REQUIRED,
        validation_rules={"options": ["15 минут", "30 минут", "45 минут", "60 минут", "Другое"]}
    ),
    
    Question(
        id="3.2.3",
        section="Интеграции",
        text="Что именно бронируется через календарь? Собеседования, встречи 1-on-1, консультации, что-то ещё?",
        question_type=QuestionType.TEXT,
        priority=QuestionPriority.IMPORTANT,
        min_answer_length=5
    ),
    
    # ПЕРЕАДРЕСАЦИЯ
    Question(
        id="3.3",
        section="Интеграции",
        text="Нужна ли переадресация звонков/обращений на живого сотрудника в определённых случаях?",
        question_type=QuestionType.CHOICE,
        priority=QuestionPriority.REQUIRED,
        validation_rules={"options": ["Да", "Нет"]}
    ),
    
    Question(
        id="3.3.1",
        section="Интеграции",
        text="На какой номер телефона или контакт агент должен переадресовывать обращения? Назовите номер в международном формате, начиная с плюса.",
        question_type=QuestionType.TEXT,
        priority=QuestionPriority.REQUIRED,
        min_answer_length=10,
        validation_rules={"pattern": r"^\+[0-9]{10,15}$"}
    ),
    
    Question(
        id="3.3.2",
        section="Интеграции",
        text="""В каких именно случаях нужна переадресация? Перечислите все ситуации:
        
        Например:
        - По запросу сотрудника
        - При сложных вопросах
        - Конфиденциальные вопросы
        - Обращения от руководства (VIP)
        - Срочные ситуации""",
        question_type=QuestionType.OPEN,
        priority=QuestionPriority.REQUIRED,
        min_answer_length=15
    ),
    
    Question(
        id="3.3.3",
        section="Интеграции",
        text="Есть ли резервный номер на случай, если основной недоступен? Если да, назовите его. Если нет, скажите 'нет'.",
        question_type=QuestionType.TEXT,
        priority=QuestionPriority.OPTIONAL,
        min_answer_length=2
    ),
    
    # SMS
    Question(
        id="3.4",
        section="Интеграции",
        text="Нужна ли отправка SMS-сообщений сотрудникам?",
        question_type=QuestionType.CHOICE,
        priority=QuestionPriority.REQUIRED,
        validation_rules={"options": ["Да", "Нет"]}
    ),
    
    Question(
        id="3.4.1",
        section="Интеграции",
        text="Какое имя отправителя (Sender ID) должно отображаться в SMS? Обычно это название компании.",
        question_type=QuestionType.TEXT,
        priority=QuestionPriority.REQUIRED,
        min_answer_length=2
    ),
    
    Question(
        id="3.4.2",
        section="Интеграции",
        text="""Для чего нужны SMS? Можете выбрать несколько вариантов:
        
        - Напоминания о встречах
        - Коды подтверждения
        - Срочные уведомления
        - Статусы заявок
        - Другое""",
        question_type=QuestionType.MULTI_CHOICE,
        priority=QuestionPriority.REQUIRED,
        min_answer_length=10
    ),
    
    Question(
        id="3.4.3",
        section="Интеграции",
        text="""За сколько времени до события отправлять напоминание?
        
        1 - За 1 час
        2 - За 3 часа
        3 - За 24 часа (за сутки)
        4 - За 24 часа и за 1 час (два напоминания)
        5 - Другое
        
        Выберите вариант или скажите свой.""",
        question_type=QuestionType.CHOICE,
        priority=QuestionPriority.IMPORTANT,
        validation_rules={"options": ["За 1 час", "За 3 часа", "За 24 часа", "За 24 часа и за 1 час", "Другое"]}
    ),
    
    # WHATSAPP
    Question(
        id="3.5",
        section="Интеграции",
        text="Нужна ли интеграция с WhatsApp для отправки сообщений сотрудникам?",
        question_type=QuestionType.CHOICE,
        priority=QuestionPriority.REQUIRED,
        validation_rules={"options": ["Да", "Нет"]}
    ),
    
    Question(
        id="3.5.1",
        section="Интеграции",
        text="Какой номер WhatsApp Business используется? Назовите в международном формате с плюсом.",
        question_type=QuestionType.TEXT,
        priority=QuestionPriority.REQUIRED,
        min_answer_length=10,
        validation_rules={"pattern": r"^\+[0-9]{10,15}$"}
    ),
    
    Question(
        id="3.5.2",
        section="Интеграции",
        text="""Для чего используется WhatsApp? Можете выбрать несколько:
        
        - Отправка документов (PDF, инструкции)
        - Напоминания
        - Интерактивное общение (кнопки, списки)
        - Групповые уведомления
        - Другое""",
        question_type=QuestionType.MULTI_CHOICE,
        priority=QuestionPriority.REQUIRED,
        min_answer_length=10
    )
]


# ==================================================
# СЕКЦИЯ 4: ДОПОЛНИТЕЛЬНАЯ ИНФОРМАЦИЯ
# ==================================================

SECTION_4_QUESTIONS = [
    Question(
        id="4.1",
        section="Дополнительная информация",
        text="""Теперь давайте разберём конкретные сценарии. 
        
        Опишите 2-3 типичных диалога между сотрудником и агентом. 
        
        Для каждого диалога расскажите:
        - Что говорит или спрашивает сотрудник
        - Как должен ответить или что должен сделать агент
        
        Например:
        Диалог 1: Сотрудник звонит и говорит "Забыл пароль от рабочей почты". Агент должен уточнить email, проверить личность, создать заявку в IT и сообщить номер заявки.
        
        Расскажите подробно ваши типичные диалоги.""",
        question_type=QuestionType.OPEN,
        priority=QuestionPriority.REQUIRED,
        min_answer_length=80,
        examples=[
            "Диалог 1: Сотрудник хочет узнать остаток отпуска. Агент проверяет в базе, называет количество дней, предлагает подать заявку. Диалог 2: Кандидат звонит уточнить про собеседование. Агент проверяет запись, подтверждает время и адрес, отправляет напоминание на email. Диалог 3: Сотрудник жалуется на неработающий принтер. Агент создаёт заявку в IT, сообщает номер, обещает что IT свяжется в течение часа."
        ]
    ),
    
    Question(
        id="4.2",
        section="Дополнительная информация",
        text="""Очень важный момент: что агент НЕ должен делать?
        
        Перечислите ограничения и запреты. Например:
        - Не разглашать персональные данные других сотрудников
        - Не принимать решения о повышении или увольнении
        - Не давать медицинские или юридические консультации
        - Не обсуждать размеры зарплат
        
        Расскажите о всех ограничениях для агента.""",
        question_type=QuestionType.OPEN,
        priority=QuestionPriority.REQUIRED,
        min_answer_length=30,
        examples=[
            "Агент не должен разглашать личную информацию о сотрудниках, не может самостоятельно одобрять отпуска без согласования с руководителем, не должен обсуждать конфиденциальные вопросы зарплат и премий, не может давать гарантии по срокам решения вопросов"
        ]
    ),
    
    Question(
        id="4.3",
        section="Дополнительная информация",
        text="""Есть ли какие-то требования по соблюдению стандартов и конфиденциальности?
        
        Например:
        - GDPR (защита персональных данных)
        - Персональные данные сотрудников
        - Коммерческая тайна
        - NDA и конфиденциальность
        - Другие требования
        
        Назовите все применимые стандарты, или скажите "нет" если нет особых требований.""",
        question_type=QuestionType.OPEN,
        priority=QuestionPriority.IMPORTANT,
        min_answer_length=5
    ),
    
    Question(
        id="4.4.1",
        section="Дополнительная информация",
        text="Как зовут контактное лицо, ответственное за работу агента?",
        question_type=QuestionType.TEXT,
        priority=QuestionPriority.REQUIRED,
        min_answer_length=2
    ),
    
    Question(
        id="4.4.2",
        section="Дополнительная информация",
        text="Email контактного лица для связи?",
        question_type=QuestionType.TEXT,
        priority=QuestionPriority.REQUIRED,
        min_answer_length=5,
        validation_rules={"pattern": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"}
    ),
    
    Question(
        id="4.4.3",
        section="Дополнительная информация",
        text="Телефон контактного лица?",
        question_type=QuestionType.TEXT,
        priority=QuestionPriority.REQUIRED,
        min_answer_length=10
    ),
    
    Question(
        id="4.4.4",
        section="Дополнительная информация",
        text="Сайт вашей компании, если есть?",
        question_type=QuestionType.TEXT,
        priority=QuestionPriority.OPTIONAL,
        min_answer_length=5
    )
]


# ==================================================
# ПОЛНАЯ СТРУКТУРА ВОПРОСОВ
# ==================================================

ALL_MANAGEMENT_QUESTIONS = {
    "section_1": SECTION_1_QUESTIONS,
    "section_2": SECTION_2_QUESTIONS,
    "section_3": SECTION_3_QUESTIONS,
    "section_4": SECTION_4_QUESTIONS
}


def get_all_questions() -> List[Question]:
    """Получить все вопросы в виде плоского списка"""
    all_questions = []
    for section_questions in ALL_MANAGEMENT_QUESTIONS.values():
        all_questions.extend(section_questions)
    return all_questions


def get_required_questions() -> List[Question]:
    """Получить только обязательные вопросы"""
    return [q for q in get_all_questions() if q.priority == QuestionPriority.REQUIRED]


def get_questions_by_section(section_name: str) -> List[Question]:
    """Получить вопросы по названию секции"""
    section_map = {
        "Базовая информация": "section_1",
        "Структура и функции": "section_2",
        "Интеграции": "section_3",
        "Дополнительная информация": "section_4"
    }
    section_key = section_map.get(section_name)
    return ALL_MANAGEMENT_QUESTIONS.get(section_key, [])
