from PIL import Image

# PNG dosyasını aç (az önce ürettiğimiz ikonun orijinali)
img = Image.open("C:/Users/Sadullah/.gemini/antigravity/brain/4ea6f11c-558b-4d33-9ee1-1f83b686dc2c/app_icon_1767038288301.png")

# ICO olarak kaydet (farklı boyutlarla)
img.save("gercek_icon.ico", format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])

print("Dönüştürme tamamlandı: gercek_icon.ico")
