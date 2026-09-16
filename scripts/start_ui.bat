@echo off
cd /d "%~dp0\.."
start "AgentBus Dispatcher" cmd /k python dispatcher.py
timeout /t 2 /nobreak >nul
python dispatcher_ui.py
