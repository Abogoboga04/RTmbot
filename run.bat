@echo off
chcp 65001 >nul
title RTM Discord Bot Runner

echo ===================================================
echo Memulai RTM Discord Bot
echo ===================================================

if exist ".venv\Scripts\activate.bat" (
    echo Mengaktifkan virtual environment (.venv)...
    call .venv\Scripts\activate.bat
) else (
    echo Virtual environment .venv tidak ditemukan, menggunakan Python sistem.
)

if not exist ".env" (
    echo [PERINGATAN] File .env belum ditemukan di direktori bot.
    echo Silakan salin .env.example menjadi .env dan isi kredensial yang diperlukan.
    echo.
)

echo Menjalankan main.py...
python main.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Bot berhenti dengan kode error: %ERRORLEVEL%
)

echo.
echo Sesi bot telah berakhir.
pause
