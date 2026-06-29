@echo off
chcp 65001 >nul
cd /d %~dp0
echo SpeechNote v0.3 starting...
python main.py --gui
if errorlevel 1 pause
