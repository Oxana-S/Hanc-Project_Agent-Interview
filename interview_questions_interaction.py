"""
Структура вопросов для голосового интервью
Паттерн: INTERACTION (агент для клиентов компании)
"""

from typing import List, Dict, Optional
from dataclasses import dataclass
from enum import Enum


class QuestionType(Enum):
    OPEN = "open"  # Открытый вопрос
    CHOICE = "choice"  # Выбор из вариантов
    MULTI_CHOICE = "multi_choice"  # Множественный выбор
    NUMERIC = "numeric"  # Числовой ввод
    TEXT = "text"  # Текстовый ввод


class QuestionPriority(Enum):
    REQUIRED = "required"  # Обязательный вопрос
    IMPORTANT = "important"  # Важный, но не критичный
    OPTIONAL = "optional"  # Опциональный


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
    min_answer_length: int = 15  # минимальная длина ответа в словах


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
        },
        follow_up_questions=[
            Question(
                id="1.2.1",
                section="Базовая информация",
                text="Уточните, пожалуйста, какая именно отрасль?",
                question_type=QuestionType.TEXT,
                priority=QuestionPriority.REQUIRED,
                min_answer_length=3
            )
        ]
    ),
    
    Question(
        id="1.3",
        section="Базовая информация",
        text="На каком языке агент будет общаться с клиентами? Русский, немецкий или английский?",
        question_type=QuestionType.CHOICE,
        priority=QuestionPriority.REQUIRED,
        validation_rules={
            "options": ["Русский", "Немецкий", "Английский"]
        }
    ),
    
    Question(
        id="1.4",
        section="Базовая информация",
        text="""Теперь самое важное. Опишите своими словами, что именно должен делать голосовой агент для ваших клиентов? 
        
        Расскажите подробно - какие задачи он должен решать, с какими вопросами справляться, что упростить в работе?""",
        question_type=QuestionType.OPEN,
        priority=QuestionPriority.REQUIRED,
        min_answer_length=30,
        examples=[
            "Принимать звонки от клиентов, записывать на приём к врачам, отвечать на вопросы о ценах и услугах",
            "Бронировать столики в ресторане, рассказывать о меню, принимать заказы на доставку",
            "Консультировать по недвижимости, записывать на просмотры квартир, собирать заявки"
        ]
    )
]


# ==================================================
# СЕКЦИЯ 2: КЛИЕНТЫ И УСЛУГИ
# ==================================================

SECTION_2_QUESTIONS = [
    Question(
        id="2.1",
        section="Клиенты и услуги",
        text="""Какой у вас тип бизнеса? Выберите наиболее подходящий вариант:
        
        1 - Запись на услуги к специалисту (клиники, салоны, автосервисы, юристы)
        2 - Бронирование ресурсов (отели, рестораны, аренда, коворкинги)
        3 - Продажи с длинным циклом (недвижимость, B2B услуги, страхование)
        4 - Техподдержка и решение проблем (SaaS, телеком, банки)
        5 - Заказы и доставка (интернет-магазины, доставка еды)
        6 - Исходящие звонки (напоминания, опросы, промо-акции)
        7 - Справочная и маршрутизация (ресепшен, колл-центр)
        8 - Другое
        
        Назовите номер или тип бизнеса.""",
        question_type=QuestionType.CHOICE,
        priority=QuestionPriority.REQUIRED,
        validation_rules={
            "options": [
                "Запись на услуги",
                "Бронирование ресурсов",
                "Продажи с длинным циклом",
                "Техподдержка",
                "Заказы и доставка",
                "Исходящие звонки",
                "Справочная",
                "Другое"
            ]
        }
    ),
    
    Question(
        id="2.2",
        section="Клиенты и услуги",
        text="Агент будет принимать входящие звонки от клиентов, делать исходящие звонки или и то, и другое?",
        question_type=QuestionType.CHOICE,
        priority=QuestionPriority.REQUIRED,
        validation_rules={
            "options": ["Входящие", "Исходящие", "Оба направления"]
        }
    ),
    
    Question(
        id="2.3",
        section="Клиенты и услуги",
        text="""Перечислите основные услуги или продукты, которые вы предлагаете клиентам. 
        
        По каждой услуге укажите, если применимо:
        - Название услуги
        - Примерная длительность
        - Цена или диапазон цен
        
        Например: "Стрижка мужская - 30 минут - 1500 рублей"
        
        Расскажите о 3-5 основных услугах.""",
        question_type=QuestionType.OPEN,
        priority=QuestionPriority.REQUIRED,
        min_answer_length=40,
        examples=[
            "Консультация терапевта - 30 минут - 2000 рублей. УЗИ диагностика - 20 минут - от 1500 до 3000 рублей в зависимости от зоны",
            "Аренда переговорной - почасовая - от 1000 рублей в час. Аренда рабочего места - помесячная - 15000 рублей"
        ]
    ),
    
    Question(
        id="2.3.1",
        section="Клиенты и услуги",
        text="Есть ли у вас разные категории или уровни услуг? Например, эконом, стандарт, премиум? Или услуги зависят от конкретного специалиста?",
        question_type=QuestionType.CHOICE,
        priority=QuestionPriority.IMPORTANT,
        validation_rules={
            "options": [
                "Нет, всё стандартно",
                "Да, есть уровни (эконом/стандарт/премиум)",
                "Да, зависит от специалиста",
                "Другое"
            ]
        }
    ),
    
    Question(
        id="2.3.2",
        section="Клиенты и услуги",
        text="""Как агент должен сообщать клиентам о ценах?
        
        1 - Фиксированные цены (агент может называть точную стоимость)
        2 - Цены "от..." (называем минимальную стоимость)
        3 - Цены по запросу (не называем, говорим что перезвоним)
        4 - Бесплатная консультация""",
        question_type=QuestionType.CHOICE,
        priority=QuestionPriority.REQUIRED,
        validation_rules={
            "options": [
                "Фиксированные цены",
                "Цены от",
                "По запросу",
                "Бесплатная консультация"
            ]
        }
    ),
    
    Question(
        id="2.4",
        section="Клиенты и услуги",
        text="Ваши клиенты - это частные лица, компании или и те, и другие?",
        question_type=QuestionType.MULTI_CHOICE,
        priority=QuestionPriority.REQUIRED,
        validation_rules={
            "options": ["B2C (частные лица)", "B2B (компании)", "Оба типа"]
        }
    ),
    
    Question(
        id="2.4.1",
        section="Клиенты и услуги",
        text="""Если ваши клиенты - частные лица, какая основная возрастная группа?
        
        1 - Молодёжь (18-30 лет)
        2 - Средний возраст (30-50 лет)
        3 - Старшее поколение (50+)
        4 - Все возрасты""",
        question_type=QuestionType.CHOICE,
        priority=QuestionPriority.IMPORTANT,
        validation_rules={
            "options": ["Молодёжь 18-30", "Средний возраст 30-50", "Старшее поколение 50+", "Все возрасты"]
        }
    ),
    
    Question(
        id="2.4.2",
        section="Клиенты и услуги",
        text="""Откуда обычно приходят ваши клиенты?
        
        - Сами звонят (видели рекламу, нашли в интернете)
        - По рекомендации других клиентов
        - Постоянные клиенты, которые уже пользовались вашими услугами
        - Вы сами им звоните первыми
        - Разные варианты
        
        Можете назвать несколько вариантов.""",
        question_type=QuestionType.MULTI_CHOICE,
        priority=QuestionPriority.IMPORTANT
    ),
    
    Question(
        id="2.4.3",
        section="Клиенты и услуги",
        text="""Теперь очень важный момент. Назовите 3-5 самых типичных вопросов или запросов, с которыми к вам обращаются клиенты.
        
        Например:
        - Сколько стоит консультация?
        - Есть ли свободное время на завтра?
        - Можно ли перенести запись?
        - Как долго длится процедура?
        
        Расскажите о ваших типичных запросах подробно.""",
        question_type=QuestionType.OPEN,
        priority=QuestionPriority.REQUIRED,
        min_answer_length=40,
        examples=[
            "Клиенты часто спрашивают: работаете ли вы в выходные, можно ли оплатить картой, есть ли парковка, делаете ли вы выезд на дом, какие документы нужны для записи"
        ]
    ),
    
    Question(
        id="2.5",
        section="Клиенты и услуги",
        text="Как агент будет представляться клиентам? Придумайте имя для вашего голосового помощника.",
        question_type=QuestionType.TEXT,
        priority=QuestionPriority.REQUIRED,
        min_answer_length=1,
        examples=["Алиса", "Максим", "Анна", "Виктория", "Дмитрий"]
    ),
    
    Question(
        id="2.6",
        section="Клиенты и услуги",
        text="""Какой тон общения должен быть у агента?
        
        1 - Формальный (обращение на "Вы", официальный стиль)
        2 - Дружелюбный (обращение на "ты", неформальный стиль)
        3 - Адаптивный (подстраивается под стиль клиента)""",
        question_type=QuestionType.CHOICE,
        priority=QuestionPriority.REQUIRED,
        validation_rules={
            "options": ["Формальный", "Дружелюбный", "Адаптивный"]
        }
    ),
    
    Question(
        id="2.7",
        section="Клиенты и услуги",
        text="""Назовите рабочие часы вашей компании.
        
        Например: "Понедельник-пятница с 9 до 18, суббота с 10 до 15, воскресенье выходной"
        
        Или: "Работаем круглосуточно"
        
        Расскажите ваш график работы.""",
        question_type=QuestionType.TEXT,
        priority=QuestionPriority.REQUIRED,
        min_answer_length=10
    ),
    
    Question(
        id="2.8",
        section="Клиенты и услуги",
        text="""В каких случаях агент должен переводить звонок на живого сотрудника?
        
        Например:
        - По запросу клиента
        - Если агент не знает ответа на вопрос
        - При жалобах и конфликтных ситуациях
        - Для VIP клиентов
        - При вопросах о финансах и оплате
        
        Назовите все случаи, когда нужна переадресация.""",
        question_type=QuestionType.OPEN,
        priority=QuestionPriority.REQUIRED,
        min_answer_length=20,
        examples=[
            "Переводить на человека, если клиент явно просит, если возникла конфликтная ситуация, если нужно обсудить индивидуальные условия или скидки"
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
        text="Нужно ли агенту отправлять email-письма клиентам? Да или нет?",
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
        
        - Подтверждение записи или брони
        - Резюме разговора с клиентом
        - Отправка документов (счета, договоры, инструкции)
        - Напоминания о предстоящих встречах
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
        text="Нужна ли интеграция с календарём для записи клиентов? Используете ли вы cal.com или похожую систему?",
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
        text="""Какая стандартная длительность встречи или услуги?
        
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
        text="Что именно клиенты бронируют через календарь? Консультации, встречи, демо продукта, что-то ещё?",
        question_type=QuestionType.TEXT,
        priority=QuestionPriority.IMPORTANT,
        min_answer_length=5
    ),
    
    # ПЕРЕАДРЕСАЦИЯ
    Question(
        id="3.3",
        section="Интеграции",
        text="Нужна ли переадресация звонков на живого сотрудника в определённых случаях?",
        question_type=QuestionType.CHOICE,
        priority=QuestionPriority.REQUIRED,
        validation_rules={"options": ["Да", "Нет"]}
    ),
    
    Question(
        id="3.3.1",
        section="Интеграции",
        text="На какой номер телефона агент должен переадресовывать звонки? Назовите номер в международном формате, начиная с плюса.",
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
        - По запросу клиента
        - При сложных вопросах
        - При жалобах и конфликтах
        - Для VIP клиентов
        - При финансовых вопросах
        - В срочных ситуациях""",
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
        text="Нужна ли отправка SMS-сообщений клиентам?",
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
        
        - Напоминания о записи или встрече
        - Подтверждение заказа
        - Статус доставки или выполнения
        - Коды подтверждения
        - Срочные уведомления
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
        text="Нужна ли интеграция с WhatsApp для отправки сообщений клиентам?",
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
        
        - Отправка фото и изображений
        - Отправка документов (PDF, прайсы)
        - Подтверждения и напоминания
        - Каталоги товаров
        - Интерактивное общение (кнопки, списки)
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
        
        Опишите 2-3 типичных диалога между клиентом и агентом. 
        
        Для каждого диалога расскажите:
        - Что говорит или спрашивает клиент
        - Как должен ответить или что должен сделать агент
        
        Например:
        Диалог 1: Клиент звонит и говорит "Хочу записаться на стрижку". Агент должен уточнить дату и время, проверить свободные слоты, записать клиента и отправить подтверждение на email.
        
        Расскажите подробно ваши типичные диалоги.""",
        question_type=QuestionType.OPEN,
        priority=QuestionPriority.REQUIRED,
        min_answer_length=80,
        examples=[
            "Диалог 1: Клиент спрашивает про цены на услуги. Агент называет прайс, предлагает записаться. Диалог 2: Клиент хочет перенести запись. Агент проверяет текущую запись, предлагает новые варианты времени, переносит. Диалог 3: Клиент интересуется наличием парковки и способами оплаты. Агент отвечает на оба вопроса и предлагает помощь в записи."
        ]
    ),
    
    Question(
        id="4.2",
        section="Дополнительная информация",
        text="""Очень важный момент: что агент НЕ должен делать?
        
        Перечислите ограничения и запреты. Например:
        - Не давать медицинские рекомендации
        - Не предлагать скидки без согласования
        - Не разглашать личные данные других клиентов
        - Не обещать то, что не можем выполнить
        
        Расскажите о всех ограничениях для агента.""",
        question_type=QuestionType.OPEN,
        priority=QuestionPriority.REQUIRED,
        min_answer_length=30,
        examples=[
            "Агент не должен давать юридические консультации, не может обещать конкретные результаты работы, не должен обсуждать цены на индивидуальные проекты без менеджера, не может разглашать информацию о других клиентах"
        ]
    ),
    
    Question(
        id="4.3",
        section="Дополнительная информация",
        text="""Есть ли какие-то требования по соблюдению стандартов и конфиденциальности?
        
        Например:
        - GDPR (защита персональных данных в Европе)
        - Медицинская тайна
        - Банковская тайна
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

ALL_INTERACTION_QUESTIONS = {
    "section_1": SECTION_1_QUESTIONS,
    "section_2": SECTION_2_QUESTIONS,
    "section_3": SECTION_3_QUESTIONS,
    "section_4": SECTION_4_QUESTIONS
}


def get_all_questions() -> List[Question]:
    """Получить все вопросы в виде плоского списка"""
    all_questions = []
    for section_questions in ALL_INTERACTION_QUESTIONS.values():
        all_questions.extend(section_questions)
    return all_questions


def get_required_questions() -> List[Question]:
    """Получить только обязательные вопросы"""
    return [q for q in get_all_questions() if q.priority == QuestionPriority.REQUIRED]


def get_questions_by_section(section_name: str) -> List[Question]:
    """Получить вопросы по названию секции"""
    section_map = {
        "Базовая информация": "section_1",
        "Клиенты и услуги": "section_2",
        "Интеграции": "section_3",
        "Дополнительная информация": "section_4"
    }
    section_key = section_map.get(section_name)
    return ALL_INTERACTION_QUESTIONS.get(section_key, [])
