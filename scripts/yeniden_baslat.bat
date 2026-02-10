@echo off
title Cep Faresi - Yeniden Baslatiliyor...
color 0E
echo.
echo ==================================================
echo           CEP FARESI YENIDEN BASLATILIYOR
echo ==================================================
echo.

:: Port 5050'yi kullanan Python process'lerini bul ve kapat
echo [*] Onceki sunucu kapatiliyor...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5050"') do (
    taskkill /F /PID %%a >nul 2>&1
)

timeout /t 2 /nobreak >nul

cls
echo.
echo ==================================================
echo           CEP FARESI BASLATILIYOR
echo ==================================================
echo.

:: Yeni sunucuyu baslat
python app.py

pause
