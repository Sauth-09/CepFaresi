# CepFaresi - Mobil Fare ve Klavye Kontrol Uygulaması

Bu proje, mobil cihazınızı bilgisayarınız için bir fare ve klavye olarak kullanmanızı sağlayan bir Python uygulamasıdır. Flask ve Socket.IO kullanarak web tabanlı bir arayüz sunar ve PyAutoGUI ile bilgisayarı kontrol eder.

## Özellikler

- **Fare Kontrolü**: Dokunmatik yüzey ile fare imlecini hareket ettirin, tıklayın ve kaydırın.
- **Klavye**: Mobil cihazınızdan metin girişi yapın.
- **Medya Kontrolü**: Oynat/Duraklat, Önceki/Sonraki, Ses Aç/Kapa/Kıs.
- **Sunum Modu**: Slayt geçişleri için özel kontroller.
- **Gamepad Modu**: Oyunlar için sanal joystick ve butonlar.

## Kurulum ve Çalıştırma

### Gereksinimler

- Python 3.x
- `pip` paket yöneticisi

### Kurulum

1. Projeyi bilgisayarınıza indirin veya klonlayın.
2. Gerekli kütüphaneleri yükleyin:

```bash
pip install -r requirements.txt
```

### Çalıştırma

Uygulamayı başlatmak için `src` klasöründeki `app.py` dosyasını çalıştırın:

```bash
python src/app.py
```

Uygulama açıldığında, ekranda beliren QR kodunu mobil cihazınızla taratın veya tarayıcıdan gösterilen IP adresine gidin.

## Derleme (Exe Oluşturma)

PyInstaller kullanarak projeyi `.exe` dosyasına dönüştürebilirsiniz.

### Tek Dosya (Portable)

```bash
pyinstaller CepFaresi.spec
```

### Klasörlü Yapı

```bash
pyinstaller CepFaresi_Folder.spec
```

Veya `scripts` klasöründeki hazır `.bat` dosyalarını kullanabilirsiniz:
- `scripts/derle.bat`: Portable sürümü derler.
- `scripts/tam_derle.bat`: Hem portable hem de klasörlü sürümü derler.

## Proje Yapısı

- `src/`: Kaynak kodlar (`app.py`) ve statik dosyalar (`static/`).
- `assets/`: İkonlar ve görseller.
- `scripts/`: Derleme ve çalıştırma betikleri.
- `requirements.txt`: Python bağımlılıkları.
- `CepFaresi.spec`: PyInstaller yapılandırma dosyası.

## Lisans

Bu proje açık kaynaklıdır ve geliştirilmeye açıktır.
