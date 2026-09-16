@echo off
cd /d "%~dp0\.."
python dispatcher.py --init
python dispatcher.py --doctor
pause
