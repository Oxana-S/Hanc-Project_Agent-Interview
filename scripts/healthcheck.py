"""
Скрипт для проверки работоспособности Voice Interviewer Agent
Проверяет все компоненты системы
"""

import asyncio
import os
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


class SystemHealthCheck:
    """Проверка работоспособности системы"""
    
    def __init__(self):
        self.results = {}
        load_dotenv()
    
    def check_env_variables(self) -> bool:
        """Проверка переменных окружения"""
        console.print("\n[yellow]🔍 Checking environment variables...[/yellow]")
        
        required_vars = [
            "AZURE_OPENAI_API_KEY",
            "AZURE_OPENAI_ENDPOINT",
            "DEEPSEEK_API_KEY",
        ]
        
        optional_vars = [
            "REDIS_HOST",
            "REDIS_PORT",
            "POSTGRES_HOST",
            "POSTGRES_PORT",
            "POSTGRES_DB",
            "POSTGRES_USER",
            "POSTGRES_PASSWORD"
        ]
        
        all_ok = True
        
        # Проверка обязательных
        for var in required_vars:
            value = os.getenv(var)
            if value:
                console.print(f"  [green]✓[/green] {var}: {'*' * 10}")
            else:
                console.print(f"  [red]✗[/red] {var}: MISSING")
                all_ok = False
        
        # Проверка опциональных
        for var in optional_vars:
            value = os.getenv(var)
            if value:
                console.print(f"  [green]✓[/green] {var}: {value}")
            else:
                console.print(f"  [yellow]⚠[/yellow] {var}: using default")
        
        self.results["env_variables"] = all_ok
        return all_ok
    
    def check_python_dependencies(self) -> bool:
        """Проверка Python зависимостей"""
        console.print("\n[yellow]📦 Checking Python dependencies...[/yellow]")
        
        dependencies = [
            ("redis", "Redis client"),
            ("sqlalchemy", "SQLAlchemy ORM"),
            ("pydantic", "Pydantic models"),
            ("rich", "Rich CLI"),
            ("structlog", "Structured logging"),
            ("dotenv", "python-dotenv")
        ]
        
        all_ok = True
        
        for module, description in dependencies:
            try:
                __import__(module)
                console.print(f"  [green]✓[/green] {module}: OK ({description})")
            except ImportError:
                console.print(f"  [red]✗[/red] {module}: MISSING ({description})")
                all_ok = False
        
        self.results["dependencies"] = all_ok
        return all_ok
    
    async def check_redis(self) -> bool:
        """Проверка подключения к Redis"""
        console.print("\n[yellow]🔴 Checking Redis connection...[/yellow]")
        
        try:
            import redis
            
            host = os.getenv("REDIS_HOST", "localhost")
            port = int(os.getenv("REDIS_PORT", "6379"))
            password = os.getenv("REDIS_PASSWORD") or None
            
            client = redis.Redis(
                host=host,
                port=port,
                password=password,
                decode_responses=True
            )
            
            # Ping
            response = client.ping()
            
            if response:
                console.print(f"  [green]✓[/green] Redis connected at {host}:{port}")
                
                # Информация о сервере
                info = client.info("server")
                console.print(f"  [cyan]ℹ[/cyan] Redis version: {info.get('redis_version')}")
                
                # Тестовая запись
                client.set("healthcheck", "ok", ex=10)
                value = client.get("healthcheck")
                
                if value == "ok":
                    console.print(f"  [green]✓[/green] Read/Write test: OK")
                
                self.results["redis"] = True
                return True
            else:
                console.print(f"  [red]✗[/red] Redis ping failed")
                self.results["redis"] = False
                return False
                
        except Exception as e:
            console.print(f"  [red]✗[/red] Redis connection failed: {e}")
            self.results["redis"] = False
            return False
    
    async def check_postgresql(self) -> bool:
        """Проверка подключения к PostgreSQL"""
        console.print("\n[yellow]🐘 Checking PostgreSQL connection...[/yellow]")
        
        try:
            from sqlalchemy import create_engine, text
            
            host = os.getenv("POSTGRES_HOST", "localhost")
            port = os.getenv("POSTGRES_PORT", "5432")
            db = os.getenv("POSTGRES_DB", "voice_interviewer")
            user = os.getenv("POSTGRES_USER", "interviewer_user")
            password = os.getenv("POSTGRES_PASSWORD", "change_me_in_production")
            
            database_url = f"postgresql://{user}:{password}@{host}:{port}/{db}"
            
            engine = create_engine(database_url, echo=False)
            
            # Проверка подключения
            with engine.connect() as connection:
                result = connection.execute(text("SELECT 1"))
                row = result.fetchone()
                
                if row and row[0] == 1:
                    console.print(f"  [green]✓[/green] PostgreSQL connected at {host}:{port}/{db}")
                    
                    # Проверка версии
                    result = connection.execute(text("SELECT version()"))
                    version = result.fetchone()[0]
                    version_short = version.split(" ")[1]
                    console.print(f"  [cyan]ℹ[/cyan] PostgreSQL version: {version_short}")
                    
                    # Проверка таблиц
                    result = connection.execute(text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    ))
                    tables = [row[0] for row in result.fetchall()]
                    
                    expected_tables = ["anketas", "interview_sessions", "statistics"]
                    
                    for table in expected_tables:
                        if table in tables:
                            console.print(f"  [green]✓[/green] Table '{table}' exists")
                        else:
                            console.print(f"  [yellow]⚠[/yellow] Table '{table}' not found")
                    
                    self.results["postgresql"] = True
                    return True
                else:
                    console.print(f"  [red]✗[/red] PostgreSQL query failed")
                    self.results["postgresql"] = False
                    return False
                    
        except Exception as e:
            console.print(f"  [red]✗[/red] PostgreSQL connection failed: {e}")
            self.results["postgresql"] = False
            return False
    
    def check_file_structure(self) -> bool:
        """Проверка структуры файлов проекта"""
        console.print("\n[yellow]📁 Checking file structure...[/yellow]")
        
        required_files = [
            "main.py",
            "voice_interviewer_agent.py",
            "models.py",
            "redis_storage.py",
            "postgres_storage.py",
            "interview_questions_interaction.py",
            "interview_questions_management.py",
            "cli_interface.py",
            "requirements.txt",
            ".env.example",
            "docker-compose.yml",
            "init_db.sql"
        ]
        
        all_ok = True
        
        for filename in required_files:
            if os.path.exists(filename):
                console.print(f"  [green]✓[/green] {filename}")
            else:
                console.print(f"  [red]✗[/red] {filename}: MISSING")
                all_ok = False
        
        self.results["file_structure"] = all_ok
        return all_ok
    
    def print_summary(self):
        """Вывести итоговую таблицу"""
        console.print("\n")
        
        table = Table(title="🏥 System Health Check Summary", show_header=True, header_style="bold magenta")
        table.add_column("Component", style="cyan", no_wrap=True)
        table.add_column("Status", justify="center")
        table.add_column("Result", justify="left")
        
        for component, status in self.results.items():
            status_icon = "[green]✓ PASS[/green]" if status else "[red]✗ FAIL[/red]"
            status_text = "OK" if status else "ERROR"
            table.add_row(component.replace("_", " ").title(), status_icon, status_text)
        
        console.print(table)
        console.print()
        
        # Общий результат
        all_passed = all(self.results.values())
        
        if all_passed:
            panel = Panel(
                "[bold green]✅ All systems operational!\n\nYou can now run: python main.py[/bold green]",
                title="SUCCESS",
                border_style="green"
            )
        else:
            failed_components = [k for k, v in self.results.items() if not v]
            panel = Panel(
                f"[bold red]❌ Some components failed:\n\n{', '.join(failed_components)}\n\n"
                f"Please check the errors above and fix them.[/bold red]",
                title="FAILURE",
                border_style="red"
            )
        
        console.print(panel)
        console.print()


async def main():
    """Главная функция"""
    console.print("""
    ╔════════════════════════════════════════════════════════════╗
    ║                                                            ║
    ║            🏥 SYSTEM HEALTH CHECK                          ║
    ║                                                            ║
    ║            Voice Interviewer Agent                         ║
    ║                                                            ║
    ╚════════════════════════════════════════════════════════════╝
    """, style="bold cyan")
    
    checker = SystemHealthCheck()
    
    # Запуск всех проверок
    checker.check_file_structure()
    checker.check_env_variables()
    checker.check_python_dependencies()
    await checker.check_redis()
    await checker.check_postgresql()
    
    # Итоговая таблица
    checker.print_summary()


if __name__ == "__main__":
    asyncio.run(main())
