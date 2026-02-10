@echo off
echo ==============================================
echo      CEP FARESI - MASTER BUILD SCRIPT
echo ==============================================
echo.

echo [0/3] ON TEMIZLIK YAPILIYOR...
echo - Calisan uygulamalar kapatiliyor...
taskkill /F /IM "CepFaresi.exe" /T >nul 2>&1
taskkill /F /IM "CepFaresi_Portable.exe" /T >nul 2>&1

echo - Eski derleme dosyalari temizleniyor...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
echo [OK] Temizlik tamamlandi.
echo.

echo [1/3] PORTABLE Surum Derleniyor (Tek Dosya)...
pyinstaller --clean --noconfirm CepFaresi.spec
if %errorlevel% neq 0 (
    echo [HATA] Portable derleme basarisiz!
    pause
    exit /b %errorlevel%
)
echo [OK] Portable surum hazir: dist\CepFaresi_Portable.exe
echo.

echo [2/3] PORTABLE KLASOR Surumu Olusturuluyor (Hizli)...
pyinstaller --clean --noconfirm CepFaresi_Folder.spec
if %errorlevel% neq 0 (
    echo [HATA] Klasor derleme basarisiz!
    pause
    exit /b %errorlevel%
)
echo [OK] Klasor surumu hazir: dist\CepFaresi_Klasorlu
echo.

echo [3/3] KURULUM DOSYASI (Setup) Olusturuluyor...
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" setup_script.iss
) else (
    echo [UYARI] Inno Setup bulunamadi! Otomatik kurulum dosyasi olusturulamadi.
    echo Lutfen Inno Setup 6'yi kurun veya yolu kontrol edin.
    echo.
    echo Elle derlemek icin setup_script.iss dosyasini Inno Setup ile acip F9'a basin.
)

echo.
echo ==============================================
echo            ISLEM TAMAMLANDI!
echo ==============================================
echo.
echo CIKTILARINIZ (dist klasoru icinde):
echo -----------------------------------
echo 1. Portable EXE (Tek Dosya): dist\CepFaresi_Portable.exe
echo 2. Portable Klasor (Hizli):  dist\CepFaresi_Klasorlu
echo 3. Kurulum Dosyasi (Setup):  dist\CepFaresi_Kurulum.exe
echo.
pause
