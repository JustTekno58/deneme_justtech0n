'''
Donanım Servisleri: Socket haberleşme + reject sistemi + ürün print (Chrome)
- Zebra (koli) yazıcıya IP:9100 üzerinden ZPL gönderme
- Scanner (Cognex telnet benzeri) IP:Port dinleme ve veriyi UI'ya iletme
- Reject (COM) tetikleme (pyserial varsa)
'''
from __future__ import annotations

import os
import socket
import threading
import time
import subprocess
import shutil
import urllib.request

try:
    import winsound
except Exception:
    winsound = None

try:
    import serial
    from serial.tools import list_ports
    SERIAL_AVAILABLE = True
except Exception:
    serial = None
    list_ports = None
    SERIAL_AVAILABLE = False

from araclar import generate_gs1_datamatrix_zpl, format_to_gs1_short

CHROME_PATHS = [
    # Google Chrome
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Users\%USERNAME%\AppData\Local\Google\Chrome\Application\chrome.exe",
    # Microsoft Edge (Chromium)
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Users\%USERNAME%\AppData\Local\Microsoft\Edge\Application\msedge.exe",
]


class RejectSystem:
    """Basit REJECT kontrolü (DTR pulse).
    - pyserial yoksa devre dışı kalır
    - Port listesinde yoksa 'PORT_NOT_FOUND'
    - Açma başarısızsa 'OPEN_FAILED'
    """
    def __init__(self, port: str = 'COM2'):
        self.port_name = port
        self.ser = None
        self.is_active = False
        self.last_error = None  # PYSerialMissing | PORT_NOT_FOUND | OPEN_FAILED
        self.last_exception = None

        if not SERIAL_AVAILABLE or not serial:
            self.last_error = "PYSerialMissing"
            return

        # Port gerçekten var mı?
        ports = self.available_ports()
        if ports and (self.port_name not in ports):
            self.last_error = "PORT_NOT_FOUND"
            self.is_active = False
            return

        try:
            # Test aç/kapa
            self.ser = serial.Serial(self.port_name)
            self.ser.close()
            self.is_active = True
        except Exception as ex:
            self.last_error = "OPEN_FAILED"
            self.last_exception = ex
            self.is_active = False

    @staticmethod
    def available_ports() -> list[str]:
        if not SERIAL_AVAILABLE or not list_ports:
            return []
        try:
            return [p.device for p in list_ports.comports()]
        except Exception:
            return []

    def update_port(self, new_port: str) -> bool:
        self.port_name = (new_port or '').strip() or self.port_name
        # Sıfırla
        self.is_active = False
        self.last_error = None
        self.last_exception = None
        if not SERIAL_AVAILABLE or not serial:
            self.last_error = "PYSerialMissing"
            return False

        ports = self.available_ports()
        if ports and (self.port_name not in ports):
            self.last_error = "PORT_NOT_FOUND"
            return False

        try:
            if self.ser and getattr(self.ser, 'is_open', False):
                try:
                    self.ser.close()
                except Exception:
                    pass
            self.ser = serial.Serial(self.port_name)
            self.ser.close()
            self.is_active = True
            return True
        except Exception as ex:
            self.last_error = "OPEN_FAILED"
            self.last_exception = ex
            self.is_active = False
            return False

    def trigger(self, duration: float = 0.5):
        if not SERIAL_AVAILABLE or not serial:
            return
        threading.Thread(target=self._pulse, args=(duration,), daemon=True).start()

    def _pulse(self, duration: float):
        try:
            if not self.ser:
                self.ser = serial.Serial(self.port_name)
            if not self.ser.is_open:
                self.ser.open()
            self.ser.dtr = True
            time.sleep(max(0.05, float(duration)))
            self.ser.dtr = False
        except Exception as ex:
            # çalışırken hata olursa aktifliği düşür + sebebi sakla
            self.is_active = False
            self.last_error = "RUNTIME_ERROR"
            self.last_exception = ex
            try:
                if self.ser and getattr(self.ser, 'is_open', False):
                    self.ser.close()
            except Exception:
                pass
class DonanimServisleri:
    def __init__(self, app):
        self.app = app
        self.stop_threads = False
        self.rejector = None
        self.reject_is_active = False
        self.reject_user_enabled = True  # UI checkbox ile aç/kapat
        # SOCKET ONLY: Windows yazıcı listesi / varsayılan yazıcı ayarlama kullanılmaz.
        # (Müşteri sadece IP:PORT üzerinden Zebra'lara ZPL gönderir.)
        self.installed_printers = []
        # SOCKET ONLY: bwip-js indirimi kapalı
        self.scanner_thread = None

    def init_rejector(self):
        port = self.app.veri.settings.get("reject_port", "COM2")
        self.rejector = RejectSystem(port)
        self.reject_is_active = bool(self.rejector.is_active) if self.rejector else False

    def update_reject_port(self, new_port: str) -> bool:
        if not self.rejector:
            self.rejector = RejectSystem(new_port)
        ok = self.rejector.update_port(new_port) if self.rejector else False
        self.reject_is_active = bool(self.rejector.is_active) if self.rejector else False
        return ok

    def reject_trigger(self, duration: float = 0.5):
        if not getattr(self, 'reject_user_enabled', True):
            return
        if self.rejector:
            self.rejector.trigger(duration)

    def trigger_full_alarm(self):
        s = self.app.veri.settings
        try: duration = float(s.get("reject_duration", 0.5))
        except Exception: duration = 0.5
        try: delay = float(s.get("reject_delay", 0.0))
        except Exception: delay = 0.0

        def _delayed():
            if delay > 0:
                time.sleep(delay)
            self.reject_trigger(duration)

        threading.Thread(target=_delayed, daemon=True).start()
        self.blink_ui(0)

        def _beep():
            if not winsound:
                return
            for _ in range(3):
                winsound.Beep(2000, 150)
                winsound.Beep(1000, 150)

        threading.Thread(target=_beep, daemon=True).start()

    def blink_ui(self, count=0):
        if count >= 6:
            self.app.manual_entry.config(bg="white", fg="black")
            self.app.style.configure("Treeview", fieldbackground="white", background="white", foreground="black")
            self.app.msg_frame.configure(bg="#f8d7da")
            return

        if count % 2 == 0:
            bg = "#ff0000"
            self.app.manual_entry.config(bg=bg, fg="white")
            self.app.style.configure("Treeview", fieldbackground=bg, background=bg, foreground="white")
            self.app.msg_frame.configure(bg=bg)
            self.app.lbl_message.configure(bg=bg, fg="white")
        else:
            self.app.manual_entry.config(bg="white", fg="black")
            self.app.style.configure("Treeview", fieldbackground="white", background="white", foreground="black")
            self.app.msg_frame.configure(bg="#f8d7da")
            self.app.lbl_message.configure(bg="#f8d7da", fg="#842029")

        self.app.root.after(250, lambda: self.blink_ui(count + 1))

    def start_scanner_listener(self):
        if self.scanner_thread and self.scanner_thread.is_alive():
            return
        self.stop_threads = False
        self.scanner_thread = threading.Thread(target=self.listen_to_scanner, daemon=True)
        self.scanner_thread.start()

    def listen_to_scanner(self):
        while not self.stop_threads:
            try:
                self.app.root.after(0, lambda: getattr(self.app, 'set_device_state', lambda *a, **k: None)('scanner','searching'))
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                if hasattr(socket, 'SIO_KEEPALIVE_VALS'):
                    s.ioctl(socket.SIO_KEEPALIVE_VALS, (1, 1000, 1000))
                s.settimeout(10)

                ip = self.app.veri.settings.get("scanner_ip", "192.168.1.12")
                port = int(self.app.veri.settings.get("scanner_port", 23))
                s.connect((ip, port))
                self.app.root.after(0, lambda: getattr(self.app, 'set_device_state', lambda *a, **k: None)('scanner','connected'))

                while True:
                    try:
                        data = s.recv(4096)
                        if not data:
                            break
                        clean = data.replace(b'\x1d', b'')
                        text = clean.decode('latin-1').strip()
                        final_text = "".join([c for c in text if ord(c) >= 32])
                        if final_text:
                            self.app.root.after(0, self._on_scan, final_text)
                    except socket.timeout:
                        continue
                    except Exception:
                        break
                s.close()
            except Exception:
                self.app.root.after(0, lambda: getattr(self.app, 'set_device_state', lambda *a, **k: None)('scanner','disconnected'))
                time.sleep(3)

    def _on_scan(self, code: str):
        if int(self.app.var_short_code.get()) == 1:
            code = format_to_gs1_short(code)
        self.app.process_barcode(code)

    def print_label(self, text: str, ptype: str, target_printer: str | None = None):
        """Etiket basar (SADECE SOCKET).
        ptype: Etiket layout tipi
            - "box"  : Koli etiketi ayarları (ZD230 varsayılan)
            - "prod" : Ürün etiketi ayarları (ZT411 varsayılan)
        target_printer:
            - None    -> ptype ile aynı cihaza gönderir
            - "box"  -> BOX yazıcı IP/Port
            - "prod" -> ÜRÜN yazıcı IP/Port
            - "prod2"-> ÜRÜN-2 (yedek) yazıcı IP/Port
        """
        if not text or text == "-" or "LİSTE" in str(text):
            return

        s = self.app.veri.settings

        device = (target_printer or ptype).strip().lower()
        dev_map = {
            "box": ("box_ip", "box_port", "BOX (ZD230)"),
            "prod": ("prod_ip", "prod_port", "ÜRÜN (ZT411)"),
            "prod2": ("prod2_ip", "prod2_port", "ÜRÜN-2 (ZT411-2)"),
        }
        ip_key, port_key, dev_name = dev_map.get(device, ("prod_ip", "prod_port", "ÜRÜN (ZT411)"))

        ip = (s.get(ip_key) or "").strip()
        try:
            port = int(s.get(port_key, 9100))
        except Exception:
            port = 9100

        if not ip:
            try:
                from tkinter import messagebox
                messagebox.showwarning(
                    "Yazıcı Ayarı",
                    f"{dev_name} için IP tanımlı değil. Yönetici Paneli > Cihaz/IP-PORT bölümünden IP/Port giriniz.",
                )
            except Exception:
                pass
            return

        try:
            dpi = int(s.get("printer_dpi", 203) or 203)
        except Exception:
            dpi = 203

        if ptype == "box":
            try:
                copies = int(s.get("box_copies", 1))
            except Exception:
                copies = 1

            zpl = generate_gs1_datamatrix_zpl(
                text,
                darkness=s.get("box_darkness", 20),
                width_mm=s.get("box_w", 50),
                height_mm=s.get("box_h", 50),
                x_mm=s.get("box_x", 0),
                y_mm=s.get("box_y", 0),
                dpi=dpi,
                module_size=s.get("box_module", 6),
            )
            for _ in range(max(1, copies)):
                threading.Thread(target=self.send_zpl_via_socket, args=(ip, port, zpl), daemon=True).start()
                time.sleep(0.15)
            return

        # varsayılan: prod
        zpl = generate_gs1_datamatrix_zpl(
            text,
            darkness=s.get("prod_darkness", 20),
            width_mm=s.get("prod_w", 50),
            height_mm=s.get("prod_h", 30),
            x_mm=s.get("prod_x", 0),
            y_mm=s.get("prod_y", 0),
            dpi=dpi,
            module_size=s.get("prod_module", 6),
        )
        threading.Thread(target=self.send_zpl_via_socket, args=(ip, port, zpl), daemon=True).start()

    def send_zpl_via_socket(self, ip: str, port: int, data: str):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2)
                s.connect((ip, port))
                s.sendall(data.encode("utf-8"))
        except Exception as e:
            print(f"Zebra Hatası ({ip}:{port}): {e}")


# --- Backward compat: eski kod modül fonksiyonunu çağırırsa ---

def print_label(app_or_donanim, text: str, ptype: str, target_printer: str | None = None):
    """Eski çağrılar için uyumluluk sarmalayıcısı."""
    try:
        # app_or_donanim DonanimServisleri ise
        if hasattr(app_or_donanim, "print_label"):
            return app_or_donanim.print_label(text, ptype, target_printer=target_printer)
    except Exception:
        pass
    return None
