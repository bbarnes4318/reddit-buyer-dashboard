@echo off
echo Starting Reddit Buyer Intent Dashboard...

:: Activate virtual environment if it exists
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
    echo Virtual environment activated
) else (
    echo Warning: Virtual environment not found. Please run setup.bat first.
    exit /b 1
)

:: Start the application
python run.py

:: If the application crashes, pause to see error
pause 