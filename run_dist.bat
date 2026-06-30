@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo SpeechNote v0.3 (packaged build)
echo Model will download on first run (~500 MB)
echo.
SpeechNote.exe
if errorlevel 1 (
    echo.
    pause
)
