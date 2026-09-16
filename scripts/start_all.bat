@echo off
cd /d "%~dp0\.."
if not exist ".env" if exist ".env.example" copy ".env.example" ".env" >nul
start "AgentBus" cmd /k python dispatcher.py
timeout /t 2 /nobreak >nul
python dispatcher_ui.py
