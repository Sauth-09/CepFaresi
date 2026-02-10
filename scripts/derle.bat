@echo off
echo Derleme islemi baslatiliyor...
pyinstaller --clean --noconfirm CepFaresi.spec
echo.
echo Derleme tamamlandi!
pause
