@echo off
setlocal
cd /d "%~dp0"

if not exist .env (
  copy .env.example .env >nul
  echo.
  echo A new .env file was created.
  echo Open .env, add your OPENAI_API_KEY and private APP_PASSWORD, then run this file again.
  pause
  exit /b 1
)

where py >nul 2>nul
if %errorlevel%==0 (
  start "" http://127.0.0.1:5000
  py -3 app.py
) else (
  start "" http://127.0.0.1:5000
  python app.py
)
