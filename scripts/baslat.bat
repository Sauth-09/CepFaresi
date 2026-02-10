@echo off
title Cep Faresi - Sunucu ve Hotspot Baslatici
color 0A

:: 1. Yonetici izni kontrolu ve Otomatik Yukseltme
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [BILGI] Yonetici izni gerekiyor. Otomatik olarak isteniyor...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit
)

:: Yonetici olarak basladik, calisma dizinini bat dosyasinin oldugu yer yap
cd /d "%~dp0"

echo [INFO] Guvenlik duvari izni ekleniyor (Port 5050)...
netsh advfirewall firewall delete rule name="Orbit Mouse Sunucu" >nul 2>&1
netsh advfirewall firewall delete rule name="Cep Faresi Sunucu" >nul 2>&1
netsh advfirewall firewall add rule name="Cep Faresi Sunucu" dir=in action=allow protocol=TCP localport=5050 profile=any >nul
echo [OK] Guvenlik duvari izni verildi.

echo ==================================================
echo   CEP FARESI BASLATILIYOR (Sunucu)
echo ==================================================
echo.

:: Hotspot otomatik acilis devre disi
echo [BILGI] Hotspot otomatik olarak acilmayacak. QR ekranindan acabilirsiniz.

:: 3. Python Sunucusunu Baslatma - YONETICI YETKISIYLE
echo.
echo [INFO] Python sunucusu baslatiliyor (Yonetici yetkisiyle)...
echo.

:: Python sunucusunu yeni bir gizli pencerede YÖNETİCİ olarak baslat
:: wmic ile baslatilan process yetkiyi devralir
start /B /MIN "" pythonw "%~dp0app.py"

:: CMD penceresini hemen kapat
exit
