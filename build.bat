@echo off
REM Build a single-file Windows .exe for the AhlecksW Macro Automator.
REM Run this in a Windows command prompt with Python 3.9+ installed.

echo === Creating virtual environment ===
python -m venv .venv
call .venv\Scripts\activate.bat

echo === Installing dependencies ===
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

echo === Building executable ===
pyinstaller --noconfirm --onefile --windowed ^
  --name AhlecksWMacro ^
  --paths src ^
  --collect-submodules pynput ^
  main.py

echo.
echo === Done ===
echo Your executable is at: dist\AhlecksWMacro.exe
pause
