@echo off
REM Voice Interviewer Agent - Quick Setup for Windows

echo ================================================
echo Voice Interviewer Agent - Quick Setup
echo ================================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.9+
    pause
    exit /b 1
)

echo [OK] Python found
python --version

REM Check Docker
docker --version >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Docker not found
    echo For full functionality, install Docker Desktop
    echo Or use local Redis and PostgreSQL
)

REM Create virtual environment
echo.
echo Creating virtual environment...
python -m venv venv

REM Activate
echo [OK] Virtual environment created
echo Activating environment...
call venv\Scripts\activate.bat

REM Install dependencies
echo Installing dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt

echo [OK] Dependencies installed

REM Create .env
if not exist .env (
    echo.
    echo Creating .env file...
    copy .env.example .env
    echo [OK] .env file created
    echo.
    echo [IMPORTANT] Edit .env and fill in API keys:
    echo    - AZURE_OPENAI_API_KEY
    echo    - DEEPSEEK_API_KEY
    echo.
    echo    Open file: notepad .env
)

REM Start Docker Compose
docker --version >nul 2>&1
if not errorlevel 1 (
    echo.
    echo Starting Redis and PostgreSQL...
    docker-compose up -d
    
    echo Waiting for databases to start (5 sec)...
    timeout /t 5 /nobreak >nul
    
    echo [OK] Infrastructure started
    echo.
    docker-compose ps
)

echo.
echo ================================================
echo Setup completed!
echo ================================================
echo.
echo Next steps:
echo.
echo 1. Edit .env and fill in API keys:
echo    notepad .env
echo.
echo 2. Run the agent:
echo    python main.py
echo.
echo 3. Or run demo (no API required):
echo    python demo.py
echo.
echo Documentation: README.md
echo Quick start: START_HERE.md
echo.
echo Happy interviewing!
echo.
pause
