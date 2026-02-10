import socket
import qrcode
import io
import base64
import pyautogui
import subprocess
import os
import sys
from flask import Flask, render_template_string, request, jsonify
from flask_socketio import SocketIO, emit
import webbrowser
import threading
import time
import logging
import ctypes  # Windows API için

# Kaynak dosyalarını bulmak için yardımcı fonksiyon (PyInstaller uyumu)
def resource_path(relative_path):
    """ PyInstaller ile paketlendiğinde geçici klasörü, değilse normal klasörü döndürür """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_path, relative_path)

# Logları gizle
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# Flask ve SocketIO ayarları
# static_folder parametresi PyInstaller içinde doğru çalışması için güncellendi
app = Flask(__name__, static_folder=resource_path('static'))
app.config['SECRET_KEY'] = 'gizli_anahtar'
socketio = SocketIO(
    app, 
    cors_allowed_origins="*",
    # async_mode='threading', # Otomatik algılasın
    ping_timeout=60,
    ping_interval=25
)

# Pyautogui güvenlik ayarı
pyautogui.FAILSAFE = False

# Ekran boyutunu al (Hassasiyet ayarı için)
sc_width, sc_height = pyautogui.size()

# Windows Virtual Key Codes (Medya tuşları)
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1

# Windows INPUT yapısı için sabitler
# Windows INPUT yapısı için sabitler
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
INPUT_HARDWARE = 2

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_WHEEL = 0x0800

# Windows mesaj sabitleri (Winamp desteği için)
WM_APPCOMMAND = 0x319
APPCOMMAND_MEDIA_PLAY_PAUSE = 14
APPCOMMAND_MEDIA_NEXTTRACK = 11
APPCOMMAND_MEDIA_PREVIOUSTRACK = 12
HWND_BROADCAST = 0xFFFF

# Windows INPUT yapıları
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))
    ]

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))
    ]

class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("ki", KEYBDINPUT),
        ("mi", MOUSEINPUT)
    ]

class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("u", INPUT_UNION)
    ]

def move_mouse_raw(x, y):
    """Mouse'u raw input ile hareket ettir (İmleç görünürlüğü için)"""
    try:
        extra = ctypes.c_ulong(0)
        ii_ = INPUT()
        ii_.type = INPUT_MOUSE
        ii_.u.mi = MOUSEINPUT(int(x), int(y), 0, MOUSEEVENTF_MOVE, 0, ctypes.pointer(extra))
        ctypes.windll.user32.SendInput(1, ctypes.pointer(ii_), ctypes.sizeof(ii_))
    except Exception as e:
        print(f"Move error: {e}")

def send_media_command(app_command):
    """Winamp ve diğer uygulamalar için WM_APPCOMMAND mesajı gönder"""
    try:
        # WM_APPCOMMAND mesajını tüm uygulamalara broadcast et
        # lParam: (APPCOMMAND << 16) | device flags
        lParam = (app_command << 16) | 0
        ctypes.windll.user32.PostMessageW(HWND_BROADCAST, WM_APPCOMMAND, 0, lParam)
        time.sleep(0.05)  # Mesajın işlenmesi için kısa bekleme
    except Exception as e:
        print(f"Medya komutu hatası: {e}")

def _press_media_key_worker(vk_code):
    """Medya tuşunu arka planda bas ve bırak"""
    try:
        # Tuşa bas
        extra = ctypes.c_ulong(0)
        ii_ = INPUT()
        ii_.type = INPUT_KEYBOARD
        ii_.u.ki = KEYBDINPUT(vk_code, 0, 0, 0, ctypes.pointer(extra))
        ctypes.windll.user32.SendInput(1, ctypes.pointer(ii_), ctypes.sizeof(ii_))
        
        # ÖNEMLI: Tuş basılı tutma süresi (yankı engellemek için)
        time.sleep(0.08)
        
        # Tuşu bırak
        ii_.u.ki = KEYBDINPUT(vk_code, 0, KEYEVENTF_KEYUP, 0, ctypes.pointer(extra))
        ctypes.windll.user32.SendInput(1, ctypes.pointer(ii_), ctypes.sizeof(ii_))
    except Exception as e:
        print(f"Medya tuşu hatası: {e}")

def press_media_key(vk_code):
    """Windows medya tuşunu ayrı thread'te gönder (sunucuyu bloklamadan)"""
    # Ayrı thread'te çalıştır - main thread bloklanmaz
    thread = threading.Thread(target=_press_media_key_worker, args=(vk_code,), daemon=True)
    thread.start()

def get_local_ip():
    """En uygun IP adresini bul (Hotspot öncelikli)"""
    try:
        # Tüm IP adreslerini al
        hostname = socket.gethostname()
        local_ips = socket.gethostbyname_ex(hostname)[2]
        
        # 1. Öncelik: Hotspot IP'si (Genellikle 192.168.137.1)
        for ip in local_ips:
            if ip.startswith("192.168.137."):
                return ip
                
        # 2. Öncelik: Google DNS'e ulaşan IP (İnterneti olan IP)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        gw_ip = s.getsockname()[0]
        s.close()
        return gw_ip

    except Exception:
        # Fallback: Eğer hiçbiri çalışmazsa bulduğu ilk non-localhost IP'yi döndür
        try:
            hostname = socket.gethostname()
            local_ips = socket.gethostbyname_ex(hostname)[2]
            for ip in local_ips:
                if not ip.startswith("127."):
                    return ip
        except:
            pass
            
        return '127.0.0.1'

def find_available_port(start_port, max_port=5100):
    """Belirtilen aralıkta boş bir port bul"""
    for port in range(start_port, max_port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('0.0.0.0', port))
                return port
            except OSError:
                continue
    raise Exception("Boş port bulunamadı!")

HTML_CODE = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <title>Cep Faresi</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no, maximum-scale=1.0">
    <script src="/static/socket.io.min.js"></script>
    <style>
        :root {
            --primary: #00ff88;
            --bg: #1a1a1a;
            --surface: #2d2d2d;
            --danger: #ff4757;
        }
        * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
        body { 
            font-family: 'Segoe UI', sans-serif; 
            text-align: center; 
            background: var(--bg); 
            color: white; 
            margin: 0; 
            padding: 0;
            /* Mobil tarayıcı çubuğu sorununu çözmek için fixed positioning */
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            display: flex;
            flex-direction: column;
            user-select: none;
            -webkit-user-select: none;
            -webkit-touch-callout: none;
        }

        /* HEADER */
        header {
            padding: 8px 10px;
            background: var(--surface);
            display: flex;
            flex-direction: column;
            align-items: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.3);
            flex-shrink: 0;
            z-index: 10;
        }
        
        .header-top {
            display: flex;
            justify-content: space-between;
            align-items: center;
            width: 100%;
            margin-bottom: 6px;
        }
        
        h3 { 
            margin: 0; 
            font-weight: 600; 
            font-size: 0.85rem;
            color: var(--primary);
        }
        
        #status { 
            font-size: 0.65rem; 
            padding: 3px 8px; 
            border-radius: 15px; 
            background: #444;
            transition: 0.3s;
        }

        /* MODE TOGGLE */
        .mode-toggle {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            background: #444;
            border-radius: 20px;
            padding: 3px;
            gap: 2px;
            width: 100%;
        }
        .mode-btn {
            padding: 6px 2px;
            border: none;
            border-radius: 15px;
            background: transparent;
            color: #888;
            font-weight: 600;
            font-size: 0.55rem;
            transition: all 0.3s ease;
            cursor: pointer;
            white-space: nowrap;
            text-align: center;
        }
        .mode-btn.active {
            background: var(--primary);
            color: #000;
            box-shadow: 0 2px 8px rgba(0, 255, 136, 0.4);
        }

        /* MEDIA MODE */
        .media-mode {
            display: none;
            flex: 1;
            margin: 20px;
            gap: 12px;
            flex-direction: column;
            justify-content: center;
            overflow-y: auto; /* Küçük ekranlarda taşarsa kaydır */
        }
        .media-mode.active {
            display: flex;
        }
        
        .media-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            padding: 10px;
        }
        
        .media-btn {
            border: none;
            border-radius: 15px;
            font-size: 2.5rem;
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 4px 0 rgba(0,0,0,0.3);
            transition: all 0.15s;
            position: relative;
            overflow: hidden;
            min-height: 80px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            touch-action: manipulation;
            user-select: none;
            -webkit-user-select: none;
            -webkit-tap-highlight-color: transparent;
        }
        
        .media-btn:active {
            transform: translateY(4px);
            box-shadow: none;
        }
        
        .media-btn.play-pause {
            grid-column: span 2;
            min-height: 100px;
            font-size: 3.5rem;
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        }
        
        .media-btn.prev {
            background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
        }
        
        .media-btn.next {
            background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);
        }
        
        .media-btn.volume {
            background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
        }
        
        .media-btn.mute {
            grid-column: span 2;
            background: linear-gradient(135deg, #30cfd0 0%, #330867 100%);
        }
        
        .media-label {
            position: absolute;
            bottom: 8px;
            font-size: 0.7rem;
            font-weight: 600;
            letter-spacing: 1px;
            opacity: 0.9;
        }
        #touchpad {
            flex: 1;
            /* İçerik sığmasa bile küçülebilmesi için min-height: 0 şart */
            min-height: 0; 
            margin: 10px;
            background: radial-gradient(circle at center, #3d3d3d 0%, var(--surface) 100%);
            border: 2px solid var(--primary);
            border-radius: 15px;
            display: flex; 
            flex-direction: column;
            align-items: center; 
            justify-content: center;
            position: relative;
            touch-action: none;
            background: rgba(0, 255, 136, 0.05);
            cursor: pointer;
            transition: all 0.2s ease;
            overflow: hidden; /* Taşmayı önle */
        }
        #touchpad p {
            margin: 5px 0; /* Yazı boşluklarını azalt */
        }
        #touchpad:active {
            background: rgba(0, 255, 136, 0.1);
            border-color: rgba(0, 255, 136, 0.8);
        }
        #icon-mouse {
            font-size: 2.5rem; /* İkonu biraz küçült */
            opacity: 1;
            color: var(--primary);
            transition: 0.3s;
            margin-bottom: 5px;
        }

        /* BUTONLAR - Responsive Yükseklik */
        .controls {
            display: flex;
            /* Sabit piksel yerine ekranın %12'si kadar yer kaplasın */
            height: 12vh; 
            min-height: 70px; /* Çok küçük ekranlar için minimum koruma */
            max-height: 100px;
            flex-shrink: 0; /* Asla kaybolmasın */
            background: var(--surface);
            padding: 8px;
            gap: 8px;
            /* iPhone alt çubuğu için güvenli alan */
            padding-bottom: calc(8px + env(safe-area-inset-bottom)); 
        }
        .btn {
            flex: 1;
            border: none;
            border-radius: 15px;
            font-size: 1.2rem;
            font-weight: bold;
            color: white;
            transition: 0.1s;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 4px 0 rgba(0,0,0,0.2);
            height: 100%; /* Kapsayıcının yüksekliğini doldur */
        }
        .btn:active {
            transform: translateY(2px);
            box-shadow: none;
        }
        .left-click { background: #3742fa; }
        .right-click { background: var(--danger); }
        .scroll_area {
            width: 50px;
            height: 100%;
            background: #444;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 10px;
            font-size: 1.5rem;
            color: #888;
        }

        /* PRESENTATION MODE */
        .presentation-mode {
            display: none;
            flex: 1;
            margin: 20px;
            gap: 15px;
            flex-direction: column;
        }
        .presentation-mode.active {
            display: flex;
        }
        .pres-btn {
            flex: 1;
            border: none;
            border-radius: 20px;
            font-size: 2rem;
            font-weight: bold;
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 15px;
            box-shadow: 0 6px 0 rgba(0,0,0,0.3);
            transition: all 0.15s;
            position: relative;
            overflow: hidden;
            min-height: 120px;
        }
        .pres-btn::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(255, 255, 255, 0);
            transition: 0.3s;
        }
        .pres-btn:active::before {
            background: rgba(255, 255, 255, 0.2);
        }
        .pres-btn:active {
            transform: translateY(6px);
            box-shadow: none;
        }
        .pres-btn-next {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }
        .pres-btn-prev {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        }
        .pres-btn .icon {
            font-size: 4rem;
            line-height: 1;
        }
        .pres-btn .label {
            font-size: 1.5rem;
            font-weight: 700;
            letter-spacing: 2px;
        }

        /* HIDE/SHOW MODES */
        .mouse-mode {
            display: flex;
            flex-direction: column;
            flex: 1;
        }
        .mouse-mode.hidden {
            display: none;
        }

        /* KEYBOARD MODE CSS */
        .keyboard-mode {
            display: none;
            flex: 1;
            align-items: flex-start;
            justify-content: center;
            padding: 10px;
            padding-top: 10px;
        }
        .keyboard-mode.active {
            display: flex;
        }
        .keyboard-container {
            width: 100%;
            max-width: 400px;
            background: #2d2d2d;
            padding: 15px;
            border-radius: 20px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.5);
        }
        .keyboard-input {
            width: 100%;
            padding: 10px;
            font-size: 1.2rem;
            border: 2px solid #555;
            border-radius: 10px;
            background: #222;
            color: white;
            outline: none;
            margin-bottom: 10px;
            text-align: center;
            transition: 0.3s;
        }
        .keyboard-input:focus {
            border-color: #00ff88;
            box-shadow: 0 0 15px rgba(0, 255, 136, 0.2);
        }
        .keyboard-keys {
            display: flex;
            gap: 10px;
        }
        .key-btn {
            flex: 1;
            padding: 15px;
            border: none;
            border-radius: 10px;
            font-size: 1rem;
            font-weight: bold;
            color: white;
            background: #444;
            cursor: pointer;
            transition: 0.2s;
        }
        .key-btn:active {
            transform: scale(0.95);
        }
        .key-btn.action {
            background: #00ff88;
            color: #000;
        }

        /* YATAY EKRAN DÜZENLEMESİ (KLAVYE & GENEL) */
        @media (orientation: landscape) {
            /* Header'ı sabitle ve iyice küçült */
            header {
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                height: 38px; /* Daha da küçüldü */
                flex-direction: row;
                justify-content: space-between;
                padding: 0 10px;
                z-index: 10001;
                background: var(--bg);
                border-bottom: 1px solid #333;
            }
            .header-top {
                width: auto;
                margin-bottom: 0;
                gap: 10px;
            }
            header h3 { display: none; } 
            
            .mode-toggle {
                padding: 0;
                background: transparent;
                gap: 5px;
            }
            .mode-btn {
                padding: 2px 8px; /* Buton içi boşluğu azalt */
                font-size: 0.9rem; /* Fontu küçült */
                height: 28px; /* Buton yüksekliğini sabitle */
                display: flex;
                align-items: center;
                justify-content: center;
            }

            /* İçeriklerin üstte kalmasını engelle (Header kadar boşluk bırak) */
            .mouse-mode, .media-mode, .gamepad-mode, .presentation-mode {
                padding-top: 40px !important; 
                height: 100vh; 
            }

            /* Klavye modunu header'ın altına sabitle */
            .keyboard-mode {
                padding: 0 !important;
                margin-top: 38px; /* Header yüksekliği */
                display: none; 
            }
            .keyboard-mode.active {
                display: block !important; 
            }
            
            .keyboard-container {
                position: fixed !important;
                top: 38px !important; /* Header yüksekliği */
                left: 0 !important;
                right: 0 !important;
                width: 100% !important;
                max-width: none !important;
                border-radius: 0 0 15px 15px !important;
                padding: 5px 10px !important; /* Padding küçüldü */
                z-index: 10000 !important;
                margin: 0 !important;
                box-shadow: 0 5px 15px rgba(0,0,0,0.5) !important;
                background: #2d2d2d;
            }
            .keyboard-input {
                margin-bottom: 0 !important;
                padding: 4px 8px !important;
                height: 32px; /* Input küçüldü */
                font-size: 0.9rem !important;
            }
            .keyboard-keys {
                gap: 5px !important;
                margin-bottom: 0 !important;
            }
            .key-btn {
                padding: 0 !important;
                height: 32px; /* Tuşlar küçüldü */
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 0.75rem !important;
            }
        }

        /* GAMEPAD MODE */
        .gamepad-mode {
            display: none;
            flex: 1;
            padding: 15px;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            gap: 20px;
            overflow: hidden;
            position: relative;
        }
        .gamepad-mode.active {
            display: flex;
        }
        
        .gamepad-container {
            display: flex;
            justify-content: space-between;
            align-items: center;
            width: 100%;
            max-width: 400px;
            gap: 20px;
        }
        
        /* ANALOG JOYSTICK */
        .joystick-container {
            position: relative;
            width: 150px;
            height: 150px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .joystick-base {
            position: absolute;
            width: 140px;
            height: 140px;
            border-radius: 50%;
            background: radial-gradient(circle at 30% 30%, #3a3a3a, #1a1a1a);
            box-shadow: 
                inset 0 5px 15px rgba(0,0,0,0.6),
                0 5px 20px rgba(0,0,0,0.5),
                0 0 0 4px #222;
            border: 3px solid #444;
        }
        
        .joystick-ring {
            position: absolute;
            width: 100px;
            height: 100px;
            border-radius: 50%;
            border: 2px dashed rgba(0, 255, 136, 0.2);
            pointer-events: none;
        }
        
        .joystick-knob {
            position: absolute;
            width: 60px;
            height: 60px;
            border-radius: 50%;
            background: radial-gradient(circle at 35% 35%, #666, #333);
            box-shadow: 
                0 4px 15px rgba(0,0,0,0.5),
                inset 0 2px 5px rgba(255,255,255,0.1),
                0 0 20px rgba(0, 255, 136, 0.3);
            cursor: grab;
            touch-action: none;
            transition: box-shadow 0.2s;
            z-index: 10;
        }
        
        .joystick-knob.active {
            background: radial-gradient(circle at 35% 35%, #888, #444);
            box-shadow: 
                0 2px 10px rgba(0,0,0,0.4),
                inset 0 2px 5px rgba(255,255,255,0.15),
                0 0 30px rgba(0, 255, 136, 0.6);
            cursor: grabbing;
        }
        
        .joystick-indicator {
            position: absolute;
            bottom: -25px;
            left: 50%;
            transform: translateX(-50%);
            font-size: 0.65rem;
            color: #666;
            white-space: nowrap;
        }
        
        .joystick-intensity {
            color: #00ff88;
            font-weight: bold;
        }
        
        /* Tuş Ayar Toggle */
        .key-toggle {
            display: flex;
            gap: 10px;
            margin-top: 15px;
        }
        
        .key-toggle-btn {
            padding: 12px 20px;
            border: 2px solid #444;
            border-radius: 10px;
            background: #2a2a2a;
            color: #888;
            font-size: 0.8rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            touch-action: manipulation;
            -webkit-tap-highlight-color: transparent;
        }
        
        .key-toggle-btn:active {
            transform: scale(0.95);
        }
        
        .key-toggle-btn.active {
            background: linear-gradient(135deg, #00ff88, #00cc6a);
            color: #000;
            border-color: #00ff88;
            box-shadow: 0 0 15px rgba(0, 255, 136, 0.4);
        }
        
        /* D-PAD */
        .dpad {
            position: relative;
            width: 150px;
            height: 150px;
        }
        
        .dpad-btn {
            position: absolute;
            width: 50px;
            height: 50px;
            border: none;
            border-radius: 10px;
            background: linear-gradient(145deg, #3a3a3a, #2d2d2d);
            color: white;
            font-size: 1.5rem;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 4px 0 #1a1a1a, 0 6px 15px rgba(0,0,0,0.4);
            transition: all 0.1s;
            touch-action: manipulation;
            -webkit-tap-highlight-color: transparent;
        }
        
        .dpad-btn:active {
            transform: translateY(4px);
            box-shadow: 0 0 0 #1a1a1a, 0 2px 8px rgba(0,0,0,0.3);
            background: linear-gradient(145deg, #00ff88, #00cc6a);
            color: #000;
        }
        
        .dpad-up { top: 0; left: 50%; transform: translateX(-50%); }
        .dpad-down { bottom: 0; left: 50%; transform: translateX(-50%); }
        .dpad-left { left: 0; top: 50%; transform: translateY(-50%); }
        .dpad-right { right: 0; top: 50%; transform: translateY(-50%); }
        
        .dpad-center {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 45px;
            height: 45px;
            background: radial-gradient(circle, #333, #222);
            border-radius: 50%;
            border: 3px solid #444;
        }
        
        /* ACTION BUTTONS - PlayStation style */
        .action-btns {
            position: relative;
            width: 140px;
            height: 140px;
        }
        
        .action-btn {
            position: absolute;
            width: 48px;
            height: 48px;
            border: none;
            border-radius: 50%;
            font-size: 0.9rem;
            font-weight: bold;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 4px 0 rgba(0,0,0,0.4), 0 6px 15px rgba(0,0,0,0.3);
            transition: all 0.1s;
            touch-action: manipulation;
            -webkit-tap-highlight-color: transparent;
        }
        
        .action-btn:active {
            transform: translateY(4px);
            box-shadow: 0 0 0 rgba(0,0,0,0.4), 0 2px 8px rgba(0,0,0,0.2);
        }
        
        /* Buton pozisyonları - PlayStation düzeni */
        .btn-triangle { 
            top: 0; 
            left: 50%; 
            transform: translateX(-50%); 
            background: linear-gradient(135deg, #00d9ff 0%, #00a8cc 100%);
            color: white;
        }
        .btn-cross { 
            bottom: 0; 
            left: 50%; 
            transform: translateX(-50%); 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .btn-square { 
            left: 0; 
            top: 50%; 
            transform: translateY(-50%); 
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            color: white;
        }
        .btn-circle { 
            right: 0; 
            top: 50%; 
            transform: translateY(-50%); 
            background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);
            color: white;
        }
        
        /* Extra buttons row */
        .gamepad-extras {
            display: flex;
            gap: 10px;
            width: 100%;
            max-width: 350px;
            justify-content: center;
            margin-top: auto;
            padding-bottom: 10px;
        }
        
        .extra-btn {
            flex: 1;
            max-width: 90px;
            padding: 10px 8px;
            border: none;
            border-radius: 8px;
            background: linear-gradient(145deg, #3a3a3a, #2d2d2d);
            color: #777;
            font-size: 0.6rem;
            font-weight: 600;
            letter-spacing: 0.5px;
            box-shadow: 0 3px 0 #1a1a1a, 0 4px 10px rgba(0,0,0,0.3);
            transition: all 0.1s;
            touch-action: manipulation;
        }
        
        .extra-btn:active {
            transform: translateY(3px);
            box-shadow: 0 0 0 #1a1a1a;
            background: linear-gradient(145deg, #00ff88, #00cc6a);
            color: #000;
        }
        
        .gamepad-title {
            color: #666;
            font-size: 0.7rem;
            letter-spacing: 2px;
            text-transform: uppercase;
            margin-bottom: -10px;
        }

        /* LANDSCAPE MODE (Yatay) - Tüm modlar için düzenleme */
        @media screen and (orientation: landscape) {
            /* Header daha kompakt */
            header {
                padding: 5px 10px;
            }
            
            .header-top {
                margin-bottom: 3px;
            }
            
            h3 {
                font-size: 0.75rem;
            }
            
            #status {
                font-size: 0.55rem;
                padding: 2px 6px;
            }
            
            .mode-btn {
                padding: 4px 2px;
                font-size: 0.5rem;
            }
            
            /* MOUSE MODE - Yatay */
            .mouse-mode {
                flex-direction: row;
                gap: 10px;
                padding: 5px;
            }
            
            #touchpad {
                flex: 3;
                border-radius: 15px;
                padding: 10px;
            }
            
            #touchpad p {
                font-size: 0.7rem;
                margin: 2px 0;
            }
            
            #icon-mouse {
                font-size: 1.5rem;
                margin-bottom: 3px;
            }
            
            .controls {
                flex-direction: column;
                width: 80px;
                height: auto;
                min-height: auto;
                max-height: none;
                padding: 5px;
                gap: 5px;
            }
            
            .btn {
                font-size: 0.9rem;
                border-radius: 10px;
                padding: 10px 5px;
            }
            
            .scroll_area {
                width: 100%;
                height: 40px;
                font-size: 1rem;
            }
            
            /* PRESENTATION MODE - Yatay */
            .presentation-mode {
                flex-direction: row;
                margin: 10px;
                gap: 10px;
            }
            
            .pres-btn {
                min-height: auto;
                border-radius: 15px;
                font-size: 1.5rem;
            }
            
            .pres-btn .icon {
                font-size: 2.5rem;
            }
            
            .pres-btn .label {
                font-size: 1rem;
            }
            
            /* MEDIA MODE - Yatay */
            .media-mode {
                margin: 10px;
                gap: 8px;
            }
            
            .media-grid {
                grid-template-columns: repeat(3, 1fr);
                gap: 8px;
                padding: 5px;
            }
            
            .media-btn {
                font-size: 1.5rem;
                border-radius: 12px;
                padding: 10px;
                min-height: 60px;
            }
            
            .media-btn.play-pause {
                grid-column: span 1;
            }
            
            .media-btn.mute {
                grid-column: span 1;
            }
            
            .media-label {
                font-size: 0.55rem;
            }
            
            /* KEYBOARD MODE - Yatay */
            .keyboard-mode {
                padding: 10px 20px;
                align-items: center;
                justify-content: flex-start;
            }
            
            .keyboard-container {
                max-width: 600px;
                padding: 10px;
                display: flex;
                flex-direction: row;
                align-items: center;
                gap: 10px;
            }
            
            .keyboard-input {
                flex: 1;
                padding: 12px;
                font-size: 1rem;
                margin-bottom: 0;
                order: 2;
            }
            
            .keyboard-keys {
                display: contents;
            }
            
            .key-btn {
                padding: 12px 15px;
                font-size: 0.75rem;
                white-space: nowrap;
            }
            
            /* SİL butonu solda */
            .key-btn:first-child {
                order: 1;
            }
            
            /* ENTER butonu sağda */
            .key-btn.action {
                order: 3;
            }
            
            /* GAMEPAD MODE - Yatay */
            .gamepad-mode {
                padding: 10px 20px;
                gap: 10px;
            }
            
            .gamepad-title {
                display: none;
            }
            
            .key-toggle {
                margin-top: 0;
                margin-bottom: 5px;
            }
            
            .key-toggle-btn {
                padding: 8px 15px;
                font-size: 0.65rem;
            }
            
            .gamepad-container {
                flex: 1;
                max-width: none;
                width: 100%;
                justify-content: space-between;
                padding: 0 30px;
                gap: 0;
            }
            
            .joystick-container,
            .dpad {
                width: 120px;
                height: 120px;
            }
            
            .joystick-base {
                width: 110px;
                height: 110px;
            }
            
            .joystick-knob {
                width: 50px;
                height: 50px;
            }
            
            .joystick-indicator {
                display: none;
            }
            
            .action-btns {
                width: 120px;
                height: 120px;
            }
            
            .action-btn {
                width: 40px;
                height: 40px;
                font-size: 0.7rem;
            }
            
            /* Extra butonları ortaya al */
            .gamepad-extras {
                position: absolute;
                left: 50%;
                top: 50%;
                transform: translate(-50%, -50%);
                flex-direction: column;
                gap: 8px;
                max-width: 80px;
                margin-top: 0;
                padding-bottom: 0;
            }
            
            .extra-btn {
                padding: 8px 6px;
                font-size: 0.55rem;
                max-width: none;
            }
        }

    </style>
</head>
<body>

    <header>
        <div class="header-top">
            <h3>🖥️ Cep Faresi</h3>
            <div id="status">Bağlantı Yok</div>
        </div>
        
        <!-- MOD DEĞİŞTİRME -->
        <div class="mode-toggle">
            <button class="mode-btn active" onclick="switchMode('mouse')">🖱️</button>
            <button class="mode-btn" onclick="switchMode('presentation')">📊</button>
            <button class="mode-btn" onclick="switchMode('media')">🎵</button>
            <button class="mode-btn" onclick="switchMode('keyboard')">⌨️</button>
            <button class="mode-btn" onclick="switchMode('gamepad')">🎮</button>
        </div>
    </header>

    <!-- MOUSE MODE -->
    <div class="mouse-mode">
        <!-- TOUCHPAD ALANI -->
        <div id="touchpad" oncontextmenu="return false;">
            <div id="icon-mouse">🖱️</div>
            <p style="margin-top:20px; color:#00ff88; font-weight:bold;">MODERN TOUCHPAD</p>
            <p style="color:#888; font-size:0.85rem; line-height:1.4;">
                1 Tap: Sol Tık • Uzun Bas: Sağ Tık<br>
                2 Tap: Çift Tık • 2 Parmak: Scroll
            </p>
        </div>

        <!-- TIKLAMA ALANI -->
        <div class="controls">
            <button class="btn left-click" ontouchstart="clickMouse('left'); return false;">SOL</button>
            <div class="scroll_area" ontouchstart="startScroll(event)" ontouchmove="moveScroll(event)">↕</div>
            <button class="btn right-click" ontouchstart="clickMouse('right'); return false;">SAĞ</button>
        </div>
    </div>

    <!-- PRESENTATION MODE -->
    <div class="presentation-mode">
        <button class="pres-btn pres-btn-next" ontouchstart="presentationKey('next'); return false;">
            <span class="label">İLERİ</span>
            <span class="icon">→</span>
        </button>
        <button class="pres-btn pres-btn-prev" ontouchstart="presentationKey('prev'); return false;">
            <span class="icon">←</span>
            <span class="label">GERİ</span>
        </button>
    </div>

    <!-- MEDIA MODE -->
    <div class="media-mode">
        <div class="media-grid">
            <!-- Play/Pause - Tam genişlik -->
            <button class="media-btn play-pause" ontouchstart="mediaControl('playpause', event); event.preventDefault();">
                ⏯️
                <span class="media-label">OYNAT / DURAKLAT</span>
            </button>
            
            <!-- Önceki Şarkı -->
            <button class="media-btn prev" ontouchstart="mediaControl('previous', event); event.preventDefault();">
                ⏮️
                <span class="media-label">ÖNCEKİ</span>
            </button>
            
            <!-- Sonraki Şarkı -->
            <button class="media-btn next" ontouchstart="mediaControl('next', event); event.preventDefault();">
                ⏭️
                <span class="media-label">SONRAKİ</span>
            </button>
            
            <!-- Ses Azalt -->
            <button class="media-btn volume" ontouchstart="mediaControl('volumedown', event); event.preventDefault();">
                🔉
                <span class="media-label">SES -</span>
            </button>
            
            <!-- Ses Artır -->
            <button class="media-btn volume" ontouchstart="mediaControl('volumeup', event); event.preventDefault();">
                🔊
                <span class="media-label">SES +</span>
            </button>
            
            <!-- Mute - Alt satır tam genişlik -->
            <button class="media-btn mute" ontouchstart="mediaControl('mute', event); event.preventDefault();">
                🔇
                <span class="media-label">SESİ KAPAT</span>
            </button>
        </div>
    </div>

    <!-- KEYBOARD MODE -->
    <div class="keyboard-mode">
        <div class="keyboard-container">
            <!-- <div style="font-size: 4rem; margin-bottom: 20px;">⌨️</div> -->
            <!-- <p style="color:#aaa; margin-bottom: 20px;">
                Buraya yazdığınız her şey anında bilgisayara aktarılır.
            </p> -->
            <input type="text" id="keyboard-input" class="keyboard-input" placeholder="Yazmaya başla..." autocomplete="off">
            <div class="keyboard-keys">
                <button class="key-btn" onclick="sendSpecialKey('backspace')">⌫ SİL</button>
                <button class="key-btn action" onclick="sendSpecialKey('enter')">↵ ENTER</button>
            </div>
        </div>
    </div>

    <!-- GAMEPAD MODE -->
    <div class="gamepad-mode">
        <div class="gamepad-title">🎮 VIRTUAL GAMEPAD</div>
        
        <!-- Tuş Ayarı (Üstte) -->
        <div class="key-toggle">
            <button class="key-toggle-btn active" id="keys-wasd" ontouchstart="setKeyMode('wasd'); event.preventDefault();" onclick="setKeyMode('wasd')">🕹️ ANALOG</button>
            <button class="key-toggle-btn" id="keys-arrows" ontouchstart="setKeyMode('arrows'); event.preventDefault();" onclick="setKeyMode('arrows')">🎮 D-PAD</button>
        </div>
        
        <div class="gamepad-container">
            <!-- ANALOG JOYSTICK (WASD modu için) -->
            <div class="joystick-container" id="joystick-container">
                <div class="joystick-base"></div>
                <div class="joystick-ring"></div>
                <div class="joystick-knob" id="joystick-knob"></div>
                <div class="joystick-indicator">
                    <span id="joystick-dir">-</span> | 
                    <span class="joystick-intensity" id="joystick-intensity">0%</span>
                </div>
            </div>
            
            <!-- D-PAD (OK TUŞLARI modu için - başta gizli) -->
            <div class="dpad" id="dpad-container" style="display: none;">
                <button class="dpad-btn dpad-up" ontouchstart="gamepadKey('up', true, event)" ontouchend="gamepadKey('up', false, event)">▲</button>
                <button class="dpad-btn dpad-down" ontouchstart="gamepadKey('down', true, event)" ontouchend="gamepadKey('down', false, event)">▼</button>
                <button class="dpad-btn dpad-left" ontouchstart="gamepadKey('left', true, event)" ontouchend="gamepadKey('left', false, event)">◀</button>
                <button class="dpad-btn dpad-right" ontouchstart="gamepadKey('right', true, event)" ontouchend="gamepadKey('right', false, event)">▶</button>
                <div class="dpad-center"></div>
            </div>
            
            <!-- Action Buttons (Sağ taraf) -->
            <div class="action-btns">
                <button class="action-btn btn-triangle" ontouchstart="gamepadKey('space', true, event)" ontouchend="gamepadKey('space', false, event)">JUMP</button>
                <button class="action-btn btn-cross" ontouchstart="gamepadKey('ctrl', true, event)" ontouchend="gamepadKey('ctrl', false, event)">CTRL</button>
                <button class="action-btn btn-square" ontouchstart="gamepadKey('shift', true, event)" ontouchend="gamepadKey('shift', false, event)">RUN</button>
                <button class="action-btn btn-circle" ontouchstart="gamepadKey('e', true, event)" ontouchend="gamepadKey('e', false, event)">USE</button>
            </div>
        </div>
        
        <!-- Extra tuşlar -->
        <div class="gamepad-extras">
            <button class="extra-btn" ontouchstart="gamepadKey('r', true, event)" ontouchend="gamepadKey('r', false, event)">🔄 RELOAD</button>
            <button class="extra-btn" ontouchstart="gamepadKey('tab', true, event)" ontouchend="gamepadKey('tab', false, event)">📋 TAB</button>
            <button class="extra-btn" ontouchstart="gamepadKey('esc', true, event)" ontouchend="gamepadKey('esc', false, event)">⏸️ MENU</button>
        </div>
    </div>

    <script>
        var socket = io({
            transports: ['websocket', 'polling'],
            upgrade: true,
            reconnection: true,
            reconnectionDelay: 500,
            reconnectionAttempts: 10,
            timeout: 20000
        });
        var lastTouchX = null;
        var lastTouchY = null;
        var lastScrollY = 0;
        
        // Performans için buffer ve throttling
        var movementBuffer = { x: 0, y: 0 };
        var lastSendTime = 0;
        var throttleDelay = 16; // 60 FPS için ~16ms
        var isMoving = false;

        // Gesture detection için değişkenler
        var touchStartTime = 0;
        var touchStartX = 0;
        var touchStartY = 0;
        var hasMoved = false;
        var longPressTimer = null;
        var lastTapTime = 0;
        var twoFingerScrolling = false;
        var lastTwoFingerDist = 0;

        socket.on('connect', function() {
            document.getElementById("status").innerText = "Bağlandı 🟢";
            document.getElementById("status").style.color = "#00ff88";
            document.getElementById("status").style.background = "rgba(0, 255, 136, 0.2)";
        });

        socket.on('disconnect', function() {
            document.getElementById("status").innerText = "Koptu 🔴";
            document.getElementById("status").style.color = "#ff4757";
            document.getElementById("status").style.background = "rgba(255, 71, 87, 0.2)";
        });

        // Optimize edilmiş hareket gönderme
        function sendMovement() {
            var now = Date.now();
            if (now - lastSendTime >= throttleDelay && (movementBuffer.x !== 0 || movementBuffer.y !== 0)) {
                socket.emit('move_cursor', { 
                    x: movementBuffer.x, 
                    y: movementBuffer.y 
                });
                movementBuffer.x = 0;
                movementBuffer.y = 0;
                lastSendTime = now;
            }
            
            if (isMoving) {
                requestAnimationFrame(sendMovement);
            }
        }

        // TOUCHPAD MANTIĞI
        var touchpad = document.getElementById('touchpad');
        
        touchpad.addEventListener('touchstart', function(e) {
            e.preventDefault();
            var touch = e.touches[0];
            
            touchStartTime = Date.now();
            touchStartX = touch.clientX;
            touchStartY = touch.clientY;
            lastTouchX = touch.clientX;
            lastTouchY = touch.clientY;
            hasMoved = false;
            
            // İki parmak kontrolü
            if (e.touches.length === 2) {
                twoFingerScrolling = true;
                var dx = e.touches[1].clientX - e.touches[0].clientX;
                var dy = e.touches[1].clientY - e.touches[0].clientY;
                lastTwoFingerDist = Math.sqrt(dx * dx + dy * dy);
                lastScrollY = (e.touches[0].clientY + e.touches[1].clientY) / 2;
            } else {
                twoFingerScrolling = false;
                isMoving = true;
                requestAnimationFrame(sendMovement);
                
                // Uzun basma zamanlayıcısı (500ms)
                longPressTimer = setTimeout(function() {
                    if (!hasMoved && e.touches.length === 1) {
                        // Sağ tık
                        socket.emit('click_mouse', { type: 'right' });
                        navigator.vibrate([50, 30, 50]); // Özel vibrasyon
                        longPressTimer = null;
                    }
                }, 500);
            }
        });

        touchpad.addEventListener('touchmove', function(e) {
            e.preventDefault();
            
            // İki parmak scroll
            if (e.touches.length === 2 && twoFingerScrolling) {
                var centerY = (e.touches[0].clientY + e.touches[1].clientY) / 2;
                var diff = centerY - lastScrollY; // Yön düzeltildi - natural scroll
                
                if (Math.abs(diff) > 3) {
                    socket.emit('scroll', { amount: diff * 2 }); // Hassasiyet: 2x
                    lastScrollY = centerY;
                }
                return;
            }
            
            // Tek parmak hareket
            if (e.touches.length === 1 && !twoFingerScrolling) {
                if (lastTouchX === null || lastTouchY === null) return;

                var touch = e.touches[0];
                var deltaX = touch.clientX - lastTouchX;
                var deltaY = touch.clientY - lastTouchY;
                
                // Hareket algılandı
                var moveDistance = Math.sqrt(deltaX * deltaX + deltaY * deltaY);
                if (moveDistance > 5) {
                    hasMoved = true;
                    
                    // Uzun basma iptal
                    if (longPressTimer) {
                        clearTimeout(longPressTimer);
                        longPressTimer = null;
                    }
                }

                // Buffer'a ekle (biriktirilmiş hareket)
                movementBuffer.x += deltaX;
                movementBuffer.y += deltaY;

                // Pozisyonu güncelle
                lastTouchX = touch.clientX;
                lastTouchY = touch.clientY;
            }
        });

        touchpad.addEventListener('touchend', function(e) {
            e.preventDefault();
            isMoving = false;
            twoFingerScrolling = false;
            
            // Uzun basma iptal
            if (longPressTimer) {
                clearTimeout(longPressTimer);
                longPressTimer = null;
            }
            
            // Kalan hareketi gönder
            if (movementBuffer.x !== 0 || movementBuffer.y !== 0) {
                socket.emit('move_cursor', { 
                    x: movementBuffer.x, 
                    y: movementBuffer.y 
                });
                movementBuffer.x = 0;
                movementBuffer.y = 0;
            }
            
            // TAP GESTİCİ (tek dokunma = sol tık)
            var touchDuration = Date.now() - touchStartTime;
            var touchDistance = Math.sqrt(
                Math.pow(touchStartX - lastTouchX, 2) + 
                Math.pow(touchStartY - lastTouchY, 2)
            );
            
            // Hızlı dokunma ve hareket etmedi ise
            if (touchDuration < 200 && touchDistance < 10 && !hasMoved) {
                var now = Date.now();
                
                // Çift dokunma kontrolü (300ms içinde)
                if (now - lastTapTime < 300) {
                    socket.emit('double_click');
                    navigator.vibrate(20);
                    lastTapTime = 0; // Reset
                } else {
                    // Tek dokunma = Sol tık
                    socket.emit('click_mouse', { type: 'left' });
                    navigator.vibrate(20);
                    lastTapTime = now;
                }
            }
            
            lastTouchX = null;
            lastTouchY = null;
        });

        function clickMouse(type) {
            socket.emit('click_mouse', { type: type });
            navigator.vibrate(30);
        }

        // MOD DEĞİŞTİRME
        function switchMode(mode) {
            var mouseMode = document.querySelector('.mouse-mode');
            var presMode = document.querySelector('.presentation-mode');
            var mediaMode = document.querySelector('.media-mode');
            var keyboardMode = document.querySelector('.keyboard-mode');
            var gamepadMode = document.querySelector('.gamepad-mode');
            var buttons = document.querySelectorAll('.mode-btn');
            
            // Tüm modları gizle
            mouseMode.classList.remove('hidden');
            presMode.classList.remove('active');
            mediaMode.classList.remove('active');
            keyboardMode.classList.remove('active');
            gamepadMode.classList.remove('active');
            buttons.forEach(btn => btn.classList.remove('active'));
            
            if (mode === 'mouse') {
                mouseMode.classList.remove('hidden');
                buttons[0].classList.add('active');
            } else if (mode === 'presentation') {
                mouseMode.classList.add('hidden');
                presMode.classList.add('active');
                buttons[1].classList.add('active');
            } else if (mode === 'media') {
                mouseMode.classList.add('hidden');
                mediaMode.classList.add('active');
                buttons[2].classList.add('active');
            } else if (mode === 'keyboard') {
                mouseMode.classList.add('hidden');
                keyboardMode.classList.add('active');
                buttons[3].classList.add('active');
                setTimeout(() => {
                    document.getElementById('keyboard-input').focus();
                }, 100);
            } else if (mode === 'gamepad') {
                mouseMode.classList.add('hidden');
                gamepadMode.classList.add('active');
                buttons[4].classList.add('active');
            }
            
            navigator.vibrate(20);
        }

        // KLAVYE GİRDİSİ (Canlı Yazım)
        document.getElementById('keyboard-input').addEventListener('input', function(e) {
            // Son karakteri al
            var val = this.value;
            if (val.length > 0) {
                var char = val.slice(-1); // Son eklenen harf
                socket.emit('keyboard_input', { type: 'text', key: char });
            }
            // Input'u temiz tutmayalım ki silme çalışsın (opsiyonel)
            // Ancak mobilde her tuşta silmek daha güvenli:
            this.value = ""; 
        });

        // ÖZEL TUŞLAR
        function sendSpecialKey(key) {
            socket.emit('keyboard_input', { type: 'special', key: key });
            navigator.vibrate(20);
        }

        // PRESENTATION MODE TUŞLARI
        function presentationKey(direction) {
            socket.emit('presentation_key', { direction: direction });
            navigator.vibrate([30, 20, 30]); // Çift vibrasyon
        }

        // GAMEPAD KONTROL
        var pressedKeys = {};
        var joystickKeyMode = 'wasd'; // 'wasd' veya 'arrows'
        var joystickActive = false;
        var joystickInterval = null;
        var currentJoystickData = { x: 0, y: 0, intensity: 0 };
        
        function setKeyMode(mode) {
            joystickKeyMode = mode;
            document.getElementById('keys-wasd').classList.toggle('active', mode === 'wasd');
            document.getElementById('keys-arrows').classList.toggle('active', mode === 'arrows');
            
            // Görsel geçiş: Joystick ve D-Pad arasında değiştir
            var joystick = document.getElementById('joystick-container');
            var dpad = document.getElementById('dpad-container');
            
            if (mode === 'wasd') {
                // Analog joystick göster
                joystick.style.display = 'flex';
                dpad.style.display = 'none';
            } else {
                // D-Pad göster
                joystick.style.display = 'none';
                dpad.style.display = 'block';
            }
            
            navigator.vibrate(15);
        }
        
        function gamepadKey(key, pressed, event) {
            if (event) {
                event.preventDefault();
                event.stopPropagation();
            }
            
            // Aynı tuş durumu değişmediyse gönderme
            if (pressedKeys[key] === pressed) return;
            pressedKeys[key] = pressed;
            
            socket.emit('gamepad_key', { key: key, pressed: pressed });
            
            if (pressed) {
                navigator.vibrate(15); // Kısa feedback
            }
        }
        
        // ANALOG JOYSTICK KONTROLU
        (function() {
            var container = document.getElementById('joystick-container');
            var knob = document.getElementById('joystick-knob');
            var dirDisplay = document.getElementById('joystick-dir');
            var intensityDisplay = document.getElementById('joystick-intensity');
            
            if (!container || !knob) return;
            
            var containerRect;
            var centerX, centerY;
            var maxDistance = 50; // Maksimum joystick hareketi (px)
            var isDragging = false;
            
            function updateContainerRect() {
                containerRect = container.getBoundingClientRect();
                centerX = containerRect.left + containerRect.width / 2;
                centerY = containerRect.top + containerRect.height / 2;
            }
            
            function moveKnob(clientX, clientY) {
                var deltaX = clientX - centerX;
                var deltaY = clientY - centerY;
                var distance = Math.sqrt(deltaX * deltaX + deltaY * deltaY);
                
                // Maksimum mesafeyi sınırla
                if (distance > maxDistance) {
                    deltaX = (deltaX / distance) * maxDistance;
                    deltaY = (deltaY / distance) * maxDistance;
                    distance = maxDistance;
                }
                
                // Knob'u hareket ettir
                knob.style.transform = 'translate(' + deltaX + 'px, ' + deltaY + 'px)';
                
                // İvme hesapla (0-100%)
                var intensity = Math.round((distance / maxDistance) * 100);
                
                // Yön hesapla
                var angle = Math.atan2(deltaY, deltaX) * (180 / Math.PI);
                var direction = getDirection(angle, intensity);
                
                // Göstergeleri güncelle
                dirDisplay.textContent = direction || '-';
                intensityDisplay.textContent = intensity + '%';
                
                // Normalize edilmiş değerler (-1 ile 1 arası)
                var normX = deltaX / maxDistance;
                var normY = deltaY / maxDistance;
                
                currentJoystickData = {
                    x: normX,
                    y: normY,
                    intensity: intensity / 100,
                    direction: direction
                };
                
                return { x: normX, y: normY, intensity: intensity / 100, direction: direction };
            }
            
            function getDirection(angle, intensity) {
                if (intensity < 10) return '';
                
                // 8 yönlü kontrol
                if (angle >= -22.5 && angle < 22.5) return '➡';
                if (angle >= 22.5 && angle < 67.5) return '↘';
                if (angle >= 67.5 && angle < 112.5) return '⬇';
                if (angle >= 112.5 && angle < 157.5) return '↙';
                if (angle >= 157.5 || angle < -157.5) return '⬅';
                if (angle >= -157.5 && angle < -112.5) return '↖';
                if (angle >= -112.5 && angle < -67.5) return '⬆';
                if (angle >= -67.5 && angle < -22.5) return '↗';
                return '';
            }
            
            function resetKnob() {
                knob.style.transform = 'translate(0, 0)';
                knob.classList.remove('active');
                dirDisplay.textContent = '-';
                intensityDisplay.textContent = '0%';
                currentJoystickData = { x: 0, y: 0, intensity: 0 };
                
                // Tüm tuşları bırak
                socket.emit('analog_joystick', { x: 0, y: 0, intensity: 0, keyMode: joystickKeyMode, release: true });
            }
            
            function sendJoystickData() {
                if (currentJoystickData.intensity > 0.05) {
                    socket.emit('analog_joystick', {
                        x: currentJoystickData.x,
                        y: currentJoystickData.y,
                        intensity: currentJoystickData.intensity,
                        keyMode: joystickKeyMode
                    });
                }
            }
            
            // Touch Events
            knob.addEventListener('touchstart', function(e) {
                e.preventDefault();
                isDragging = true;
                knob.classList.add('active');
                updateContainerRect();
                navigator.vibrate(10);
                
                // Sürekli data gönderimi başlat (30 FPS)
                if (joystickInterval) clearInterval(joystickInterval);
                joystickInterval = setInterval(sendJoystickData, 33);
            });
            
            document.addEventListener('touchmove', function(e) {
                if (!isDragging) return;
                e.preventDefault();
                
                var touch = e.touches[0];
                moveKnob(touch.clientX, touch.clientY);
            }, { passive: false });
            
            document.addEventListener('touchend', function(e) {
                if (!isDragging) return;
                isDragging = false;
                
                if (joystickInterval) {
                    clearInterval(joystickInterval);
                    joystickInterval = null;
                }
                
                resetKnob();
            });
            
            // Mouse Events (Test için)
            knob.addEventListener('mousedown', function(e) {
                e.preventDefault();
                isDragging = true;
                knob.classList.add('active');
                updateContainerRect();
                
                if (joystickInterval) clearInterval(joystickInterval);
                joystickInterval = setInterval(sendJoystickData, 33);
            });
            
            document.addEventListener('mousemove', function(e) {
                if (!isDragging) return;
                moveKnob(e.clientX, e.clientY);
            });
            
            document.addEventListener('mouseup', function(e) {
                if (!isDragging) return;
                isDragging = false;
                
                if (joystickInterval) {
                    clearInterval(joystickInterval);
                    joystickInterval = null;
                }
                
                resetKnob();
            });
        })();

        // MEDIA KONTROL - Debounce ile
        var lastMediaAction = null;
        var lastMediaTime = 0;
        var mediaDebounceDelay = 300; // 300ms debounce (hızlı tepki için)
        
        function mediaControl(action, event) {
            // Event preventDefault
            if (event) {
                event.preventDefault();
                event.stopPropagation();
            }
            
            var now = Date.now();
            
            // Debug için log
            console.log('mediaControl called:', action, 'Time since last:', now - lastMediaTime, 'ms');
            
            // Herhangi bir medya komutu çok hızlı tekrarlanıyorsa engelle
            if ((now - lastMediaTime) < mediaDebounceDelay) {
                console.log('BLOCKED - Too fast!');
                return; // Çok hızlı, engelle
            }
            
            console.log('SENDING command:', action);
            
            // Komutu gönder
            socket.emit('media_control', { action: action });
            navigator.vibrate([40, 20]); // Medya feedback
            
            // Son aksiyon ve zamanı kaydet
            lastMediaAction = action;
            lastMediaTime = now;
        }

        // SCROLL MANTIĞI - Optimize edildi (yedek buton için)
        var scrollBuffer = 0;
        var lastScrollSendTime = 0;
        var scrollThrottleDelay = 50; // Scroll için 50ms
        
        function startScroll(e) { 
            e.preventDefault();
            lastScrollY = e.touches[0].clientY; 
        }
        
        function moveScroll(e) {
            e.preventDefault();
            var currentY = e.touches[0].clientY;
            var diff = currentY - lastScrollY; // Natural scroll
            
            scrollBuffer += diff;
            lastScrollY = currentY;
            
            var now = Date.now();
            if (now - lastScrollSendTime >= scrollThrottleDelay && Math.abs(scrollBuffer) > 5) {
                socket.emit('scroll', { amount: scrollBuffer * 2 }); // 2x hassasiyet
                scrollBuffer = 0;
                lastScrollSendTime = now;
            }
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    try:
        local_ip = get_local_ip()
        port = app.config.get('SERVER_PORT', 5000)
        url = f"http://{local_ip}:{port}/controller"
        
        # Hotspot aktif mi kontrol et (IP 192.168.137.x ise aktiftir)
        is_hotspot_active = local_ip.startswith("192.168.137.")
        
        qr = qrcode.make(url)
        img_io = io.BytesIO()
        qr.save(img_io, 'PNG')
        img_io.seek(0)
        img_base64 = base64.b64encode(img_io.getvalue()).decode()
        
        # Python değişkenlerini JS'e aktarmak için string içinde kullanıyoruz
        js_bool = 'true' if is_hotspot_active else 'false'
        display_style = 'block' if is_hotspot_active else 'none'
        btn_text = "Hotspot Kapat" if is_hotspot_active else "Hotspot Aç"
        btn_bg = "#ff4757" if is_hotspot_active else "#666"

        return render_template_string(f"""
        <html>
        <head>
            <title>Cep Faresi Sunucu</title>
            <script src="/static/socket.io.min.js"></script>
            <style>
                body {{ font-family: 'Segoe UI', sans-serif; background: #222; color: white; margin: 0; height: 100vh; display: flex; align-items: center; justify-content: center; }}
                
                .container {{ 
                    background: #333; 
                    padding: 30px; 
                    border-radius: 20px; 
                    box-shadow: 0 10px 30px rgba(0,0,0,0.5); 
                    max-width: 800px; /* Genişlettik */
                    display: grid;
                    grid-template-columns: 300px 1fr; /* Sol (QR) sabit, Sağ (Bilgi) esnek */
                    gap: 30px;
                    align-items: start;
                }}

                /* SOL KOLON */
                .left-col {{
                    text-align: center;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                    height: 100%;
                }}
                
                /* SAĞ KOLON */
                .right-col {{
                    text-align: left;
                }}

                h1 {{ color: #00ff88; margin: 0 0 15px 0; font-size: 1.8rem; line-height: 1.2; }}
                .link {{ font-size: 0.9rem; color: #ccc; margin-top: 10px; }}
                
                .card {{
                    background: #444; 
                    border-radius: 12px; 
                    padding: 15px; 
                    margin-bottom: 15px;
                    border: 1px solid #555;
                }}
                
                h3 {{ margin: 0 0 10px 0; font-size: 1rem; color: #fff; border-bottom: 1px solid #555; padding-bottom: 5px; }}
                
                .hotspot-btn {{
                    padding: 8px 16px;
                    font-size: 0.9rem;
                    border: none;
                    border-radius: 6px;
                    background: {btn_bg};
                    color: white;
                    cursor: pointer;
                    transition: 0.3s;
                    font-weight: bold;
                    width: 100%;
                    margin-top: 5px;
                }}
                .hotspot-btn:hover {{ opacity: 0.9; }}

                .guide-header {{
                    font-size: 0.9rem; font-weight: bold; cursor: pointer; display: flex; justify-content: space-between;
                    padding: 10px; background: #555; border-radius: 8px;
                }}
                .guide-content {{ display: none; padding: 10px; font-size: 0.85rem; color: #ddd; line-height: 1.4; }}
                .guide-content ol {{ padding-left: 20px; margin: 0; }}
                .guide-content li {{ margin-bottom: 5px; }}

                .info {{ font-size: 0.75rem; color: #888; margin-top: 10px; }}
            </style>
        </head>
        <body>
            <div class="container">
                
                <!-- SOL KOLON: QR ve BAŞLIK -->
                <div class="left-col">
                    <img src="/static/icon.ico" width="48" style="margin-bottom: 10px;">
                    <h1>Cep Faresi<br><span style="font-size:1rem; color:white;">Sunucu Kontrol</span></h1>
                    
                    <img id="qr-img" src="data:image/png;base64,{img_base64}" width="200" style="border-radius:15px; border: 4px solid white;"/>
                    
                    <div class="link">Chrome Arama Çubuğundaki<br><b>Kamera Simgesiyle</b> Okutun</div>
                    <div style="font-family: monospace; color: #00ff88; font-size: 1rem; margin-top: 5px; background:#222; padding:5px 10px; border-radius:5px;">{local_ip}:{port}</div>
                </div>

                <!-- SAĞ KOLON: AYARLAR ve REHBER -->
                <div class="right-col">
                    
                    <!-- HOTSPOT KARTI -->
                    <div class="card">
                        <h3>📡 Bağlantı Ayarı (Hotspot)</h3>
                        <div id="hotspot-details" style="display: {display_style}; margin-bottom:10px; background: rgba(0,255,136,0.1); padding:8px; border-radius:5px;">
                            <div>📡 SSID: <b>CepFaresi</b></div>
                            <div>🔑 Şifre: <b>12345678</b></div>
                        </div>
                        <button id="hotspot-btn" class="hotspot-btn" onclick="toggleHotspot()">{btn_text}</button>
                        <div id="hotspot-msg" style="font-size:0.75rem; color:#aaa; margin-top:5px;"></div>
                    </div>

                    <!-- REHBER KARTI -->
                    <div style="background: #444; border-radius: 12px; border: 1px solid #555; overflow:hidden;">
                        <div class="guide-header" onclick="toggleGuide()">
                            <span>❓ Nasıl Kullanırım?</span>
                            <span id="guide-arrow">▼</span>
                        </div>
                        <div id="guide-content" class="guide-content">
                            <ol>
                                <li>Telefonda <b>Chrome</b>'u açın, arama çubuğundaki <b>Kamera</b> simgesine basıp QR kodu okutun.</li>
                                <li>Açılan ekranda <b>Mouse, Klavye veya Medya</b> modunu seçin.</li>
                                <li>Telefon ekranını touchpad gibi kullanarak PC'yi yönetin.</li>
                                <li>Yazı yazmak için <b>Klavye</b> moduna geçiş yapın.</li>
                            </ol>
                        </div>
                    </div>

                    <div class="info">
                        💡 <b>İpucu:</b> iPhone'da Safari sensör izni isteyebilir. Android sorunsuzdur.
                    </div>

                    <!-- AĞ BİLGİSİ -->
                    <div style="margin-top: 15px; padding: 12px; background: rgba(255, 255, 255, 0.05); border-left: 4px solid #00ff88; border-radius: 6px; font-size: 0.85rem; color: #eee; line-height: 1.5;">
                        <b>⚠️ Bağlantı Bilgisi:</b><br>
                        Bu bilgisayar ile telefonunuz aynı ağa bağlı olmalı. İster aynı modeme bağlanın, isterseniz <b>Hotspotu Aç</b>'a tıklayıp telefonunuzun Wi-Fi'sinden "CepFaresi" ağına bağlanın.
                    </div>
                    
                    <!-- ÇIKIŞ BUTONU -->
                    <button onclick="shutdownServer()" style="
                        margin-top: 15px;
                        background: #ff4757;
                        color: white;
                        border: none;
                        padding: 10px;
                        width: 100%;
                        border-radius: 8px;
                        font-weight: bold;
                        cursor: pointer;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        gap: 8px;
                    ">
                        ⚠️ ÇIKIŞ
                    </button>

                </div>
            </div>


            <script>
                function toggleGuide() {{
                    var content = document.getElementById('guide-content');
                    var arrow = document.getElementById('guide-arrow');
                    if (content.style.display === "block") {{
                        content.style.display = "none";
                        arrow.innerHTML = "▼";
                    }} else {{
                        content.style.display = "block";
                        arrow.innerHTML = "▲";
                    }}
                }}
                
                // Sunucuya "Ben PC'yim" de
                var socket = io();
                socket.on('connect', function() {{
                    socket.emit('register_pc');
                }});

                var isHotspotActive = {js_bool};

                function toggleHotspot() {{
                    var btn = document.getElementById('hotspot-btn');
                    var details = document.getElementById('hotspot-details');
                    var msg = document.getElementById('hotspot-msg');
                    
                    if (!isHotspotActive) {{
                        // START
                        btn.style.opacity = "0.7";
                        btn.innerHTML = "Açılıyor...";
                        
                        fetch('/start_hotspot', {{ method: 'POST' }})
                            .then(res => res.json())
                            .then(data => {{
                                if (data.status === 'success') {{
                                    isHotspotActive = true;
                                    btn.style.background = "#ff4757";
                                    btn.innerHTML = "Hotspot Kapat";
                                    btn.style.opacity = "1";
                                    
                                    details.style.display = 'block';
                                    msg.textContent = "Hotspot aktif! QR kod güncelleniyor...";
                                    msg.style.color = "#00ff88";
                                    
                                    // QR kodu güncelle
                                    setTimeout(updateQR, 2000);
                                    
                                    }} else {{
                                    btn.innerHTML = "Hata oluştu";
                                    msg.textContent = data.message || "Hotspot açılamadı.";
                                    msg.style.color = "#ff4757";
                                    
                                    alert("Hata Detayı:\\n" + (data.message || "Bilinmeyen hata"));

                                    setTimeout(() => {{ 
                                        btn.innerHTML = "Hotspot Aç"; 
                                        btn.style.opacity = "1";
                                    }}, 3000);
                                }}
                            }})
                            .catch(err => {{
                                console.error(err);
                                btn.innerHTML = "Hata";
                                alert("Bağlantı Hatası:\\n" + err); 
                            }});
                    }} else {{
                        // STOP
                        btn.style.opacity = "0.7";
                        btn.innerHTML = "Kapatılıyor...";
                        
                        fetch('/stop_hotspot', {{ method: 'POST' }})
                            .then(res => res.json())
                            .then(data => {{
                                isHotspotActive = false;
                                btn.style.background = "#666";
                                btn.innerHTML = "Hotspot Aç";
                                btn.style.opacity = "1";
                                
                                details.style.display = 'none';
                                msg.textContent = "Hotspot kapandı. QR kod güncelleniyor...";
                                
                                 // QR kodu güncelle
                                setTimeout(updateQR, 1000);
                            }});
                    }}
                }}

                function updateQR() {{
                    fetch('/get_qr_data')
                        .then(res => res.json())
                        .then(data => {{
                            document.getElementById('qr-img').src = "data:image/png;base64," + data.qr_image;
                            document.getElementById('url-txt').innerText = data.url;
                            var msg = document.getElementById('hotspot-msg');
                            if (msg.textContent.includes("güncelleniyor")) {{
                                 msg.textContent = "";
                            }}
                        }});
                }}

                function shutdownServer() {{
                    if(confirm("Sunucuyu kapatmak istediğinize emin misiniz?")) {{
                        fetch('/shutdown', {{ method: 'POST' }});
                        
                        // Arayüzü güncelle
                        document.body.innerHTML = `
                            <div style="display:flex; flex-direction:column; align-items:center; justify-content:center; height:100vh; background:#222; color:white; font-family:'Segoe UI'; text-align:center;">
                                <h1 style="color:#ff4757; font-size:2rem;">Çıkış Yapıldı</h1>
                                <p style="color:#aaa; font-size:1.2rem; margin-top:20px;">
                                    Sunucu ve tüm işlemler kapatıldı.<br>
                                    Yeniden başlatmak için <b>CepFaresi.exe</b> dosyasını tekrar çalıştırın.
                                </p>
                            </div>
                        `;
                    }}
                }}
            </script>
        </body>
        </html>
        """)
    except Exception as e:
        import traceback
        return f"<pre>{traceback.format_exc()}</pre>", 500

@app.route('/start_hotspot', methods=['POST'])
def start_hotspot():
    ssid = "CepFaresi"
    password = "12345678"
    try:
        # Yönetici yetkisi kontrolü - ctypes ile
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        
        if is_admin:
            # Zaten yönetici olarak çalışıyoruz, doğrudan çalıştır
            # 1. Kayıt defteri ayarı
            subprocess.run('reg add "HKLM\\SYSTEM\\CurrentControlSet\\Services\\icssvc\\Settings" /v PeerlessTimeoutEnabled /t REG_DWORD /d 0 /f', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # 2. Hotspot Setup
            cmd_set = f'netsh wlan set hostednetwork mode=allow ssid="{ssid}" key="{password}"'
            proc_set = subprocess.run(cmd_set, shell=True, capture_output=True)
            
            if proc_set.returncode != 0:
                err_msg = proc_set.stderr.decode('cp857', errors='ignore') or proc_set.stdout.decode('cp857', errors='ignore') or 'Bilinmeyen hata'
                raise Exception(f"Kurulum Hatası: {err_msg}")
                
            # 3. Start
            cmd_start = 'netsh wlan start hostednetwork'
            proc_start = subprocess.run(cmd_start, shell=True, capture_output=True)
            
            if proc_start.returncode != 0:
                 err_msg = proc_start.stderr.decode('cp857', errors='ignore') or proc_start.stdout.decode('cp857', errors='ignore') or 'Bilinmeyen hata'
                 raise Exception(f"Başlatma Hatası: {err_msg}")
        else:
            # Yönetici DEĞİLİZ - PowerShell ile elevated olarak çalıştır
            # Geçici bat dosyası oluştur
            temp_bat_path = os.path.join(os.environ.get('TEMP', '.'), 'hotspot_start.bat')
            bat_content = f'''@echo off
reg add "HKLM\\SYSTEM\\CurrentControlSet\\Services\\icssvc\\Settings" /v PeerlessTimeoutEnabled /t REG_DWORD /d 0 /f
netsh wlan set hostednetwork mode=allow ssid="{ssid}" key="{password}"
netsh wlan start hostednetwork
'''
            with open(temp_bat_path, 'w', encoding='utf-8') as f:
                f.write(bat_content)
            
            # PowerShell ile yönetici olarak çalıştır - Kullanıcıdan izin isteyecek
            ps_cmd = f'Start-Process cmd -ArgumentList "/c {temp_bat_path}" -Verb RunAs -Wait'
            result = subprocess.run(['powershell', '-Command', ps_cmd], capture_output=True, timeout=30)
            
            # Temizlik
            try:
                os.remove(temp_bat_path)
            except: pass
            
            if result.returncode != 0:
                raise Exception("Yönetici izni gerekiyor. Lütfen baslat.bat dosyasını yönetici olarak çalıştırın.")
        
        # Hotspot IP'sini kontrol et (Daha uzun süre bekle: 15x0.5 = 7.5sn)
        for _ in range(15):
            if get_local_ip().startswith("192.168.137."):
                break
            time.sleep(0.5)
        
        return jsonify({'status': 'success', 'ssid': ssid, 'password': password})
    except subprocess.TimeoutExpired:
        # Kullanıcı UAC penceresini açık bıraktıysa veya beklediyse
        if get_local_ip().startswith("192.168.137."):
            return jsonify({'status': 'success', 'ssid': ssid, 'password': password})
        return jsonify({'status': 'error', 'message': 'İşlem zaman aşımına uğradı. Yönetici iznini onayladınız mı?'})
    except Exception as e:
        print(f"Hotspot Hata: {str(e)}")
        if get_local_ip().startswith("192.168.137."):
            return jsonify({'status': 'success', 'ssid': ssid, 'password': password})
        
        # Daha kullanıcı dostu hata mesajı
        error_msg = str(e)
        if 'administrator' in error_msg.lower() or 'yönetici' in error_msg.lower() or 'privilege' in error_msg.lower():
            error_msg = "Yönetici yetkisi gerekiyor. baslat.bat dosyasını sağ tık > 'Yönetici olarak çalıştır' ile açın."
        
        return jsonify({'status': 'error', 'message': error_msg})

@app.route('/stop_hotspot', methods=['POST'])
def stop_hotspot():
    try:
        subprocess.run('netsh wlan stop hostednetwork', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return jsonify({'status': 'stopped'})
    except:
        return jsonify({'status': 'error'})

@app.route('/shutdown', methods=['POST'])
def shutdown():
    def kill_server():
        time.sleep(1)
        
        # === CLEANUP: Tüm izleri temizle ===
        try:
            # 1. Hotspot'u kapat
            subprocess.run('netsh wlan stop hostednetwork', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # 2. Firewall kuralını sil
            subprocess.run('netsh advfirewall firewall delete rule name="Cep Faresi Sunucu"', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # 3. Geçici bat dosyasını sil (varsa)
            temp_bat = os.path.join(os.environ.get('TEMP', '.'), 'hotspot_start.bat')
            if os.path.exists(temp_bat):
                os.remove(temp_bat)
                
        except: pass
        
        # Kendini kapat
        os._exit(0)
        
    threading.Thread(target=kill_server).start()
    return jsonify({'status': 'success'})

@app.route('/get_qr_data')
def get_qr_data():
    local_ip = get_local_ip()
    port = app.config.get('SERVER_PORT', 5000)
    url = f"http://{local_ip}:{port}/controller"
    
    qr = qrcode.make(url)
    img_io = io.BytesIO()
    qr.save(img_io, 'PNG')
    img_io.seek(0)
    img_base64 = base64.b64encode(img_io.getvalue()).decode()
    
    return jsonify({
        'qr_image': img_base64,
        'url': url
    })

# PC İstemcilerini Takip Et
pc_clients = set()
shutdown_timer = None

@app.route('/controller')
def controller():
    return render_template_string(HTML_CODE)

def scheduled_shutdown():
    global shutdown_timer
    if len(pc_clients) == 0:
        # === CLEANUP: Tüm izleri temizle ===
        try:
            # 1. Hotspot'u kapat
            subprocess.run('netsh wlan stop hostednetwork', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # 2. Firewall kuralını sil
            subprocess.run('netsh advfirewall firewall delete rule name="Cep Faresi Sunucu"', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # 3. Geçici bat dosyasını sil (varsa)
            temp_bat = os.path.join(os.environ.get('TEMP', '.'), 'hotspot_start.bat')
            if os.path.exists(temp_bat):
                os.remove(temp_bat)
                
        except: pass
        os._exit(0)

@socketio.on('register_pc')
def handle_pc_connect():
    global shutdown_timer
    pc_clients.add(request.sid)
    # Yeni bağlantı geldi, shutdown iptal (eğer varsa)
    if shutdown_timer:
        shutdown_timer.cancel()
        shutdown_timer = None

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in pc_clients:
        pc_clients.remove(request.sid)
        # Eğer son PC istemcisi çıktıysa, 3 saniye sonra kapat (Reload payı)
        if len(pc_clients) == 0:
            global shutdown_timer
            shutdown_timer = threading.Timer(3.0, scheduled_shutdown)
            shutdown_timer.start()



@socketio.on('move_cursor')
def handle_move(data):
    try:
        # Touchpad modundan gelen doğrudan delta değerleri
        x_raw = data['x']
        y_raw = data['y']
        
        # Touchpad için hassasiyet çarpanı (düşürüldü, çünkü artık birikmiş değerler geliyor)
        sensitivity = 2.2
        
        move_x = int(x_raw * sensitivity)
        move_y = int(y_raw * sensitivity)
        
        # Sıfırsa işlem yapma
        if move_x == 0 and move_y == 0:
            return
        
        # Direkt hareket ettir - ctypes ile (cursor görünürlüğü için)
        move_mouse_raw(move_x, move_y)
        # pyautogui.moveRel(move_x, move_y, duration=0)
    except: pass

@socketio.on('click_mouse')
def handle_click(data):
    try:
        pyautogui.click(button=data['type'])
    except: pass

@socketio.on('keyboard_input')
def handle_keyboard(data):
    try:
        type = data.get('type')
        key = data.get('key')
        
        if type == 'text':
            # Harf yazma
            pyautogui.write(key) 
        elif type == 'special':
            # Özel tuşlar (enter, backspace)
            pyautogui.press(key)
    except: pass

@socketio.on('double_click')
def handle_double_click():
    try:
        pyautogui.doubleClick()
    except: pass

@socketio.on('scroll')
def handle_scroll(data):
    try:
        # Scroll miktarı - normalize edilmiş
        amount = int(data['amount'])
        
        # Scroll direction'a göre hareket (yukarı pozitif, aşağı negatif)
        pyautogui.scroll(amount)
    except: pass

@socketio.on('presentation_key')
def handle_presentation_key(data):
    try:
        direction = data['direction']
        if direction == 'next':
            # İleri: Sağ ok tuşu (PowerPoint/PDF için standart)
            pyautogui.press('right')
        elif direction == 'prev':
            # Geri: Sol ok tuşu
            pyautogui.press('left')
    except: pass

@socketio.on('media_control')
def handle_media_control(data):
    try:
        action = data['action']
        
        # Basit pyautogui ile medya tuşları
        if action == 'playpause':
            pyautogui.press('playpause')
        elif action == 'next':
            pyautogui.press('nexttrack')
        elif action == 'previous':
            pyautogui.press('prevtrack')
        elif action == 'volumeup':
            pyautogui.press('volumeup')
        elif action == 'volumedown':
            pyautogui.press('volumedown')
        elif action == 'mute':
            pyautogui.press('volumemute')
    except Exception as e:
        print(f"Medya kontrol hatası: {e}")

@socketio.on('gamepad_key')
def handle_gamepad_key(data):
    """Gamepad tuşlarını işle - bas/bırak mantığı ile"""
    try:
        key = data.get('key')
        pressed = data.get('pressed', False)
        
        # Tuş mapping (gamepad key -> pyautogui key)
        key_map = {
            'w': 'w',
            'a': 'a',
            's': 's',
            'd': 'd',
            'space': 'space',
            'shift': 'shift',
            'ctrl': 'ctrl',
            'e': 'e',
            'r': 'r',
            'tab': 'tab',
            'esc': 'escape'
        }
        
        actual_key = key_map.get(key, key)
        
        if pressed:
            # Tuşa bas (bırakma - keyDown)
            pyautogui.keyDown(actual_key)
        else:
            # Tuşu bırak (keyUp)
            pyautogui.keyUp(actual_key)
            
    except Exception as e:
        print(f"Gamepad hatası: {e}")

# Analog joystick için aktif tuşları takip et
analog_active_keys = set()

@socketio.on('analog_joystick')
def handle_analog_joystick(data):
    """Analog joystick verilerini işle - ivme bazlı tuş kontrolü"""
    global analog_active_keys
    
    try:
        x = data.get('x', 0)  # -1 ile 1 arası
        y = data.get('y', 0)  # -1 ile 1 arası
        intensity = data.get('intensity', 0)  # 0 ile 1 arası
        key_mode = data.get('keyMode', 'wasd')
        release = data.get('release', False)
        
        # Tuş mapping
        if key_mode == 'wasd':
            keys = {'up': 'w', 'down': 's', 'left': 'a', 'right': 'd'}
        else:  # arrows
            keys = {'up': 'up', 'down': 'down', 'left': 'left', 'right': 'right'}
        
        # Bırakma sinyali geldi - tüm tuşları bırak
        if release:
            for key in analog_active_keys.copy():
                try:
                    pyautogui.keyUp(key)
                except: pass
            analog_active_keys.clear()
            return
        
        # Minimum eşik (çok küçük hareketleri yoksay)
        threshold = 0.15
        
        # Hangi tuşlar basılı olmalı?
        new_keys = set()
        
        # Yatay hareket
        if x > threshold:
            new_keys.add(keys['right'])
        elif x < -threshold:
            new_keys.add(keys['left'])
        
        # Dikey hareket
        if y > threshold:
            new_keys.add(keys['down'])
        elif y < -threshold:
            new_keys.add(keys['up'])
        
        # Yeni basılması gereken tuşlar
        keys_to_press = new_keys - analog_active_keys
        # Bırakılması gereken tuşlar
        keys_to_release = analog_active_keys - new_keys
        
        # Tuşları bırak
        for key in keys_to_release:
            try:
                pyautogui.keyUp(key)
            except: pass
        
        # Yeni tuşlara bas
        for key in keys_to_press:
            try:
                pyautogui.keyDown(key)
            except: pass
        
        # Aktif tuşları güncelle
        analog_active_keys = new_keys
        
    except Exception as e:
        print(f"Analog joystick hatası: {e}")

def open_browser(port):
    time.sleep(2)
    webbrowser.open(f'http://127.0.0.1:{port}')

if __name__ == '__main__':

    # PORT SEÇİMİ (Otomatik bul)
    try:
        PORT = find_available_port(5000)
        app.config['SERVER_PORT'] = PORT
        print(f"Sunucu {PORT} portunda başlatılıyor...")
    except Exception as e:
        print(f"Port hatası: {e}")
        PORT = 5000

    # 2. SİSTEM AYARLARI (Firewall & Registry)
    try:
        # Firewall izni (Sessizce)
        subprocess.run('netsh advfirewall firewall delete rule name="Cep Faresi Sunucu"', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(f'netsh advfirewall firewall add rule name="Cep Faresi Sunucu" dir=in action=allow protocol=TCP localport={PORT} profile=any', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Hotspot Timeout Fix (Sessizce)
        subprocess.run('reg add "HKLM\\SYSTEM\\CurrentControlSet\\Services\\icssvc\\Settings" /v PeerlessTimeoutEnabled /t REG_DWORD /d 0 /f', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        pass

    # SPLASH SCREEN KAPATMA
    try:
        import pyi_splash
        # Biraz bekle ki kullanıcı görsün (opsiyonel)
        # pyi_splash.update_text("Sunucu Başlatılıyor...") 
        pyi_splash.close()
    except:
        pass

    threading.Thread(target=open_browser, args=(PORT,)).start()
    
    # Konsol yoksa print hatasını önle
    if getattr(sys, 'frozen', False):
        sys.stdout = open(os.devnull, 'w')
        sys.stderr = open(os.devnull, 'w')

    try:
        # allow_unsafe_werkzeug=True: EXE içinde çalışırken prod uyarısını geçmek için
        socketio.run(app, host='0.0.0.0', port=PORT, debug=False, allow_unsafe_werkzeug=True)
    except Exception as e:
        if not getattr(sys, 'frozen', False):
            import traceback
            traceback.print_exc()
            input("Hata oluştu. Kapatmak için Enter...")
        pass
