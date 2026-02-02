"""
Главный файл для запуска голосового агента-интервьюера
"""

import asyncio
import os
from dotenv import load_dotenv
import structlog
from rich.console import Console

from models import InterviewPattern
from redis_storage import RedisStorageManager
from postgres_storage import PostgreSQLStorageManager
from voice_interviewer_agent import VoiceInterviewerAgent
from cli_interface import InterviewCLI, print_welcome_banner, print_pattern_selection

# Настройка логирования
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ],
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger()
console = Console()


def load_configuration():
    """
    Загрузить конфигурацию из .env файла
    
    Returns:
        Словарь с конфигурациями
    """
    load_dotenv()
    
    config = {
        "redis": {
            "host": os.getenv("REDIS_HOST", "localhost"),
            "port": int(os.getenv("REDIS_PORT", "6379")),
            "password": os.getenv("REDIS_PASSWORD") or None,
            "db": int(os.getenv("REDIS_DB", "0")),
            "session_ttl": int(os.getenv("REDIS_SESSION_TTL", "7200"))
        },
        "postgres": {
            "database_url": os.getenv(
                "DATABASE_URL",
                f"postgresql://{os.getenv('POSTGRES_USER', 'user')}:"
                f"{os.getenv('POSTGRES_PASSWORD', 'password')}@"
                f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
                f"{os.getenv('POSTGRES_PORT', '5432')}/"
                f"{os.getenv('POSTGRES_DB', 'voice_interviewer')}"
            )
        },
        "azure_openai": {
            "api_key": os.getenv("AZURE_OPENAI_API_KEY"),
            "endpoint": os.getenv("AZURE_OPENAI_ENDPOINT"),
            "deployment_name": os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
            "api_version": os.getenv("AZURE_OPENAI_API_VERSION")
        },
        "deepseek": {
            "api_key": os.getenv("DEEPSEEK_API_KEY"),
            "endpoint": os.getenv("DEEPSEEK_API_ENDPOINT", "https://api.deepseek.com/v1"),
            "model": os.getenv("DEEPSEEK_MODEL", "deepseek-reasoner")
        },
        "livekit": {
            "api_key": os.getenv("LIVEKIT_API_KEY"),
            "api_secret": os.getenv("LIVEKIT_API_SECRET"),
            "url": os.getenv("LIVEKIT_URL")
        },
        "general": {
            "environment": os.getenv("ENVIRONMENT", "development"),
            "log_level": os.getenv("LOG_LEVEL", "INFO"),
            "max_clarifications": int(os.getenv("MAX_CLARIFICATIONS_PER_QUESTION", "3")),
            "min_answer_length": int(os.getenv("MIN_ANSWER_LENGTH_WORDS", "15"))
        }
    }
    
    return config


def validate_configuration(config: dict) -> bool:
    """
    Валидировать конфигурацию
    
    Args:
        config: Конфигурация
        
    Returns:
        True если валидна
    """
    required_fields = [
        ("azure_openai", "api_key"),
        ("azure_openai", "endpoint"),
        ("deepseek", "api_key"),
    ]
    
    missing_fields = []
    
    for section, field in required_fields:
        if not config.get(section, {}).get(field):
            missing_fields.append(f"{section}.{field}")
    
    if missing_fields:
        console.print("[red]❌ Missing required configuration fields:[/red]")
        for field in missing_fields:
            console.print(f"   - {field}")
        console.print()
        console.print("[yellow]💡 Please check your .env file[/yellow]")
        return False
    
    return True


async def initialize_storage_managers(config: dict):
    """
    Инициализировать storage managers
    
    Args:
        config: Конфигурация
        
    Returns:
        (redis_manager, postgres_manager)
    """
    console.print("[yellow]🔄 Initializing storage...[/yellow]")
    
    # Redis
    try:
        redis_manager = RedisStorageManager(**config["redis"])
        
        if redis_manager.health_check():
            console.print("[green]✓ Redis connected[/green]")
        else:
            console.print("[red]✗ Redis connection failed[/red]")
            return None, None
    except Exception as e:
        console.print(f"[red]✗ Redis initialization failed: {e}[/red]")
        return None, None
    
    # PostgreSQL
    try:
        postgres_manager = PostgreSQLStorageManager(
            database_url=config["postgres"]["database_url"]
        )
        
        if postgres_manager.health_check():
            console.print("[green]✓ PostgreSQL connected[/green]")
        else:
            console.print("[red]✗ PostgreSQL connection failed[/red]")
            return None, None
    except Exception as e:
        console.print(f"[red]✗ PostgreSQL initialization failed: {e}[/red]")
        return None, None
    
    console.print()
    return redis_manager, postgres_manager


async def select_pattern() -> InterviewPattern:
    """
    Выбрать паттерн интервью
    
    Returns:
        Выбранный паттерн
    """
    print_pattern_selection()
    
    while True:
        try:
            choice = input("Enter choice (1 or 2): ").strip()
            
            if choice == "1":
                console.print("[green]✓ Selected: INTERACTION pattern[/green]")
                return InterviewPattern.INTERACTION
            elif choice == "2":
                console.print("[green]✓ Selected: MANAGEMENT pattern[/green]")
                return InterviewPattern.MANAGEMENT
            else:
                console.print("[red]✗ Invalid choice. Please enter 1 or 2.[/red]")
        except KeyboardInterrupt:
            console.print("\n[yellow]Cancelled by user[/yellow]")
            exit(0)


async def main():
    """Главная функция"""
    # Приветственный баннер
    print_welcome_banner()
    
    # Загрузка конфигурации
    console.print("[yellow]📋 Loading configuration...[/yellow]")
    config = load_configuration()
    
    if not validate_configuration(config):
        return
    
    console.print("[green]✓ Configuration loaded[/green]")
    console.print()
    
    # Инициализация storage
    redis_manager, postgres_manager = await initialize_storage_managers(config)
    
    if not redis_manager or not postgres_manager:
        console.print("[red]❌ Failed to initialize storage. Exiting.[/red]")
        return
    
    # Выбор паттерна
    pattern = await select_pattern()
    console.print()
    
    # Инициализация агента
    console.print("[yellow]🤖 Initializing voice interviewer agent...[/yellow]")
    
    try:
        agent = VoiceInterviewerAgent(
            pattern=pattern,
            redis_manager=redis_manager,
            postgres_manager=postgres_manager,
            azure_openai_config=config["azure_openai"],
            deepseek_config=config["deepseek"],
            livekit_config=config["livekit"],
            max_clarifications=config["general"]["max_clarifications"],
            min_answer_length=config["general"]["min_answer_length"]
        )
        
        console.print("[green]✓ Agent initialized successfully![/green]")
        console.print()
        
    except Exception as e:
        console.print(f"[red]❌ Agent initialization failed: {e}[/red]")
        logger.error("agent_initialization_failed", error=str(e))
        return
    
    # Запуск интервью
    console.print("[yellow]🎙️ Starting interview...[/yellow]")
    console.print()
    
    try:
        # Стартуем интервью
        await agent.start_interview()
        
        # Создаём CLI интерфейс
        cli = InterviewCLI(agent)
        
        # Запускаем с мониторингом
        await cli.run_with_monitoring()
        
        console.print()
        console.print("[bold green]🎉 Interview completed successfully![/bold green]")
        
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️ Interview interrupted by user[/yellow]")
        
        if agent.context:
            console.print("[yellow]💾 Saving progress...[/yellow]")
            await agent.pause_interview()
            console.print(f"[green]✓ Progress saved. Session ID: {agent.context.session_id}[/green]")
            console.print("[yellow]You can resume later with this session ID[/yellow]")
        
    except Exception as e:
        console.print(f"\n[red]❌ Error during interview: {e}[/red]")
        logger.error("interview_error", error=str(e))
        
        if agent.context:
            await agent.pause_interview()
    
    finally:
        console.print()
        console.print("[cyan]👋 Thank you for using Voice Interviewer Agent![/cyan]")


async def resume_interview(session_id: str):
    """
    Возобновить прерванное интервью
    
    Args:
        session_id: ID сессии для возобновления
    """
    print_welcome_banner()
    
    console.print(f"[yellow]📂 Loading interview session: {session_id}[/yellow]")
    
    # Загрузка конфигурации
    config = load_configuration()
    
    # Инициализация storage
    redis_manager, postgres_manager = await initialize_storage_managers(config)
    
    if not redis_manager or not postgres_manager:
        console.print("[red]❌ Failed to initialize storage. Exiting.[/red]")
        return
    
    # Загружаем контекст
    context = await redis_manager.load_context(session_id)
    
    if not context:
        console.print(f"[red]❌ Session {session_id} not found or expired[/red]")
        return
    
    console.print(f"[green]✓ Session loaded: {context.pattern.value.upper()} pattern[/green]")
    console.print(f"[green]✓ Progress: {context.get_progress_percentage():.1f}%[/green]")
    console.print()
    
    # Инициализация агента
    agent = VoiceInterviewerAgent(
        pattern=context.pattern,
        redis_manager=redis_manager,
        postgres_manager=postgres_manager,
        azure_openai_config=config["azure_openai"],
        deepseek_config=config["deepseek"],
        livekit_config=config["livekit"],
        max_clarifications=config["general"]["max_clarifications"],
        min_answer_length=config["general"]["min_answer_length"]
    )
    
    # Загружаем сессию
    await agent.start_interview(session_id=session_id)
    await agent.resume_interview()
    
    # CLI
    cli = InterviewCLI(agent)
    await cli.run_with_monitoring()


if __name__ == "__main__":
    import sys
    
    # Проверяем аргументы командной строки
    if len(sys.argv) > 1 and sys.argv[1] == "resume":
        if len(sys.argv) < 3:
            console.print("[red]Usage: python main.py resume <session_id>[/red]")
            sys.exit(1)
        
        session_id = sys.argv[2]
        asyncio.run(resume_interview(session_id))
    else:
        # Обычный запуск
        asyncio.run(main())
