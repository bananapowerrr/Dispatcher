@echo off
rem Конфигурация (таймауты, флаги, пути) — единый источник .env.
rem Переопределения (напр. OPENCODE_ENABLED=1) задавайте там, а не здесь.
setlocal
"C:\Users\user\AppData\Local\Programs\Python\Python312\python.exe" "%~dp0dispatcher.py"
endlocal