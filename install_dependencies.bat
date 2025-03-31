@echo off
echo Installing all required dependencies...

pip install -v praw
pip install -v schedule
pip install -v google-generativeai
pip install -v python-dotenv
pip install -v fastapi
pip install -v uvicorn
pip install -v pydantic
pip install -v requests
pip install -v jinja2
pip install -v authlib
pip install -v itsdangerous
pip install -v "python-jose[cryptography]"
pip install -v python-multipart
pip install -v SQLAlchemy
pip install -v httpx

echo Dependencies installation complete!
pause 