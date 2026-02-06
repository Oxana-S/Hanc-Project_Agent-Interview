-- Инициализация базы данных для Voice Interviewer Agent

-- Создание расширений
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Таблица для хранения завершённых анкет (FinalAnketa)
-- Гибридная структура: 6 индексированных колонок + 1 JSONB для полных данных
CREATE TABLE IF NOT EXISTS anketas (
    anketa_id VARCHAR(255) PRIMARY KEY,
    interview_id VARCHAR(255) UNIQUE NOT NULL,
    pattern VARCHAR(50) NOT NULL,  -- 'interaction' или 'management'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    company_name VARCHAR(255) NOT NULL,
    industry VARCHAR(100) NOT NULL,

    -- Полные данные анкеты в JSONB (FinalAnketa.model_dump())
    anketa_json JSONB NOT NULL
);

-- Индексы для анкет
CREATE INDEX IF NOT EXISTS idx_anketas_company ON anketas(company_name);
CREATE INDEX IF NOT EXISTS idx_anketas_industry ON anketas(industry);
CREATE INDEX IF NOT EXISTS idx_anketas_pattern ON anketas(pattern);
CREATE INDEX IF NOT EXISTS idx_anketas_created_at ON anketas(created_at);


-- Таблица для истории интервью (включая незавершённые)
CREATE TABLE IF NOT EXISTS interview_sessions (
    session_id VARCHAR(255) PRIMARY KEY,
    interview_id VARCHAR(255) UNIQUE NOT NULL,
    pattern VARCHAR(50) NOT NULL,
    
    -- Временные метки
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(50) NOT NULL,
    
    -- Метрики
    duration_seconds FLOAT,
    questions_asked INTEGER,
    questions_answered INTEGER,
    clarifications_total INTEGER,
    completeness_score FLOAT,
    
    -- Метаданные сессии (переименовано из metadata т.к. это зарезервированное слово)
    session_metadata JSONB
);

-- Индексы для сессий
CREATE INDEX IF NOT EXISTS idx_sessions_pattern ON interview_sessions(pattern);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON interview_sessions(status);
CREATE INDEX IF NOT EXISTS idx_sessions_started_at ON interview_sessions(started_at);
CREATE INDEX IF NOT EXISTS idx_sessions_completed_at ON interview_sessions(completed_at);


-- Таблица для статистики (опционально)
CREATE TABLE IF NOT EXISTS statistics (
    id SERIAL PRIMARY KEY,
    date DATE DEFAULT CURRENT_DATE,
    pattern VARCHAR(50),
    total_interviews INTEGER DEFAULT 0,
    completed_interviews INTEGER DEFAULT 0,
    average_duration_minutes FLOAT DEFAULT 0.0,
    average_completeness_score FLOAT DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(date, pattern)
);

-- Индекс для статистики
CREATE INDEX IF NOT EXISTS idx_statistics_date ON statistics(date);


-- Функция для автоматического обновления статистики
CREATE OR REPLACE FUNCTION update_daily_statistics()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO statistics (date, pattern, total_interviews, completed_interviews)
    VALUES (
        CURRENT_DATE,
        NEW.pattern,
        1,
        CASE WHEN NEW.status = 'completed' THEN 1 ELSE 0 END
    )
    ON CONFLICT (date, pattern)
    DO UPDATE SET
        total_interviews = statistics.total_interviews + 1,
        completed_interviews = statistics.completed_interviews + 
            CASE WHEN NEW.status = 'completed' THEN 1 ELSE 0 END;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Триггер для обновления статистики
DROP TRIGGER IF EXISTS trigger_update_statistics ON interview_sessions;
CREATE TRIGGER trigger_update_statistics
    AFTER INSERT OR UPDATE ON interview_sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_daily_statistics();


-- Вьюха для быстрого доступа к завершённым интервью
CREATE OR REPLACE VIEW completed_interviews AS
SELECT
    s.session_id,
    s.interview_id,
    s.pattern,
    s.started_at,
    s.completed_at,
    s.duration_seconds,
    s.questions_answered,
    s.clarifications_total,
    s.completeness_score,
    a.company_name,
    a.industry,
    a.anketa_json->>'agent_name' as agent_name
FROM interview_sessions s
LEFT JOIN anketas a ON s.interview_id = a.interview_id
WHERE s.status = 'completed';


-- Вьюха для статистики по отраслям
CREATE OR REPLACE VIEW industry_statistics AS
SELECT
    a.industry,
    COUNT(*) as total_anketas,
    AVG((a.anketa_json->>'consultation_duration_seconds')::float / 60) as avg_duration_minutes,
    AVG((a.anketa_json->'quality_metrics'->>'completeness_score')::float) as avg_completeness
FROM anketas a
GROUP BY a.industry
ORDER BY total_anketas DESC;


-- Вьюха для статистики по паттернам
CREATE OR REPLACE VIEW pattern_statistics AS
SELECT 
    pattern,
    COUNT(*) as total_sessions,
    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
    AVG(duration_seconds / 60) as avg_duration_minutes,
    AVG(completeness_score) as avg_completeness
FROM interview_sessions
GROUP BY pattern;


-- Комментарии к таблицам
COMMENT ON TABLE anketas IS 'Хранит заполненные анкеты FinalAnketa для создания голосовых агентов';
COMMENT ON TABLE interview_sessions IS 'История всех интервью, включая незавершённые';
COMMENT ON TABLE statistics IS 'Ежедневная статистика по интервью';

-- Комментарии к важным колонкам
COMMENT ON COLUMN anketas.pattern IS 'Паттерн интервью: interaction или management';
COMMENT ON COLUMN anketas.anketa_json IS 'Полные данные FinalAnketa в формате JSONB';

COMMENT ON COLUMN interview_sessions.session_metadata IS 'Дополнительная информация о сессии: IP, user_agent и т.д.';


-- Начальные данные (опционально)
-- Можно добавить примеры для тестирования

-- Готово!
SELECT 'Database initialized successfully!' as message;
