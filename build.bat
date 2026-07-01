@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo ========================================
echo  SpeechNote Build Script
echo  Using: conda env "speech"
echo ========================================
echo.
REM Activate conda speech environment
call C:\Users\21592\miniconda3\condabin\conda.bat activate speech
if %errorlevel% neq 0 (
    echo [ERROR] Failed to activate conda environment
    pause
    exit /b 1
)
echo [1/3] Cleaning previous build...
if exist "dist\SpeechNote" rmdir /s /q "dist\SpeechNote"
if exist "build\SpeechNote" rmdir /s /q "build\SpeechNote"
echo [2/3] Building with PyInstaller...
python -m PyInstaller --onedir --noconfirm --name SpeechNote ^
    --add-data "config.py;." ^
    --add-data "requirements.txt;." ^
    --add-data "corrector\correct_dic.json;corrector" ^
    --add-data "gui\styles.qss;gui" ^
    --exclude-module torchvision ^
    --exclude-module matplotlib ^
    --exclude-module PIL ^
    --exclude-module pandas ^
    --hidden-import funasr_onnx ^
    --hidden-import onnxruntime ^
    --hidden-import sounddevice ^
    --hidden-import pypinyin ^
    --hidden-import httpx ^
    --hidden-import yaml ^
    --hidden-import jieba ^
    --hidden-import kaldi_native_fbank ^
    --hidden-import kaldiio ^
    --hidden-import omegaconf ^
    --hidden-import hydra ^
    --hidden-import torch_complex ^
    --hidden-import onnxscript ^
    --hidden-import six ^
    --hidden-import editdistance ^
    --collect-submodules funasr_onnx ^
    --collect-data funasr_onnx ^
    main.py
if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller build failed
    pause
    exit /b 1
)
REM Copy run script
copy /y run_dist.bat dist\SpeechNote\ >nul
echo.
echo ========================================
echo  Build complete!
echo  Output: dist\SpeechNote\
echo  Size:
dir /s dist\SpeechNote\*.exe 2>nul | findstr "File(s)"
echo ========================================
echo.
REM Show size
wmic datafile where "drive='C:' and path='Git\\repositories\\AI_ASR\\dist\\SpeechNote\\' and extension='exe'" get filesize /format:value 2>nul
timeout /t 5
endlocal
