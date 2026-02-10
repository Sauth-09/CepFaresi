@echo off
title Cep Faresi - Kapatiliyor...
color 0C
echo.
echo ==================================================
echo           CEP FARESI KAPATILIYOR
echo ==================================================
echo.

:: Port 5050'yi kullanan Python process'lerini bul ve kapat
echo [*] Sunucu kapatiliyor...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5050"') do (
    taskkill /F /PID %%a >nul 2>&1
    echo [OK] Process (PID: %%a) kapatildi.
)

echo.
echo [✓] Tum Cep Faresi sunuculari kapatildi.
echo.
timeout /t 3
