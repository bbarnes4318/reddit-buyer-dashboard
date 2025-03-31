@echo off
echo Reddit Buyer Intent Dashboard - Setup Script

:: Check if Python is installed
python --version > nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python is not installed or not in PATH
    echo Please install Python 3.8 or higher from https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Create virtual environment
echo Creating virtual environment...
python -m venv venv
if %errorlevel% neq 0 (
    echo Error: Failed to create virtual environment
    pause
    exit /b 1
)

:: Activate virtual environment
call venv\Scripts\activate.bat
echo Virtual environment activated

:: Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip

:: Install requirements - showing progress with verbose output
echo Installing dependencies...
pip install -v -r requirements.txt
if %errorlevel% neq 0 (
    echo Error: Failed to install dependencies
    pause
    exit /b 1
)

:: Verify PRAW is installed
echo Verifying PRAW installation...
python -c "import praw" 2>nul
if %errorlevel% neq 0 (
    echo Error: PRAW not installed correctly. Installing directly...
    pip install praw
)

:: Create .env file if not exists
if not exist .env (
    echo Creating .env file from template...
    copy .env.example .env
    echo Please edit the .env file with your configuration before running the application
    echo Edit C:\Users\Jimbo\Desktop\reddit\.env now with your editor
)

:: Initialize database
echo Initializing database...
python init_db.py
if %errorlevel% neq 0 (
    echo Error: Failed to initialize database
    pause
    exit /b 1
)

echo.
echo Setup completed successfully!
echo To start the application, run start.bat
echo.
echo Note: Make sure you've updated your .env file with your credentials first
pause 