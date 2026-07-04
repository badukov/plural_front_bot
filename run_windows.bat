@echo off
setlocal
if not exist .env (
  echo Copying .env.example to .env
  copy .env.example .env
  echo.
  echo Open .env and paste BOT_TOKEN and ADMIN_IDS, then run this file again.
  pause
  exit /b 1
)

if not exist .venv (
  python -m venv .venv
)

call .venv\Scripts\activate
pip install -r requirements.txt
python bot.py
pause
