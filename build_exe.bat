@echo off
setlocal
chcp 65001 > nul
cd /d "%~dp0"
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name shearing_combiner ^
  app.py
if errorlevel 1 exit /b 1
copy /y "dist\shearing_combiner.exe" "dist\シャーリング取り合わせツール.exe" > nul
if errorlevel 1 exit /b 1
echo Build complete: dist\シャーリング取り合わせツール.exe
