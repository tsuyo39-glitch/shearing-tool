@echo off
setlocal
chcp 65001 > nul
cd /d "%~dp0"
python -m PyInstaller --noconfirm --clean --onefile --windowed --name "シャーリング取り合わせ_長さ自動計算版" app_auto_length.py
if errorlevel 1 exit /b 1
