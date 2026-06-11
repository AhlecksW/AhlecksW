@echo off
REM Build a single-file Windows .exe for Cryo Chamber.
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
  --name cryochamber ^
  --paths src ^
  --collect-submodules pynput ^
  main.py

echo.
echo === Done ===
echo Your executable is at: dist\cryochamber.exe
pause
