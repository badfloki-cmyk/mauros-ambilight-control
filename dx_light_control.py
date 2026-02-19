"""
DX-Light / Robobloq LED Strip Controller
=========================================
Steuert den DX-Light (Robobloq) Monitor-Backlight-Strip über USB HID.

Protokoll basiert auf dem xsiravia/win_ambilight C++ Projekt:
- VID: 0x1A86, PID: 0xFE07
- 36 LEDs in 3 Gruppen (Links=12, Oben=12, Rechts=12)
- 192-Byte Puffer, gesendet als 3 × 64-Byte HID Output Reports
- Header: [0x53, 0x43, 0x00, 0xB1, counter, 0x80, 0x01]

Verwendung:
  python dx_light_control.py                  # Interaktives Menü
  python dx_light_control.py red              # Alle LEDs rot
  python dx_light_control.py color 255 0 128  # Alle LEDs in Custom-Farbe
  python dx_light_control.py rainbow          # Regenbogen-Effekt
  python dx_light_control.py off              # LEDs aus
  python dx_light_control.py demo             # Demo-Sequenz
"""

import sys
import time
import math
import colorsys
import pywinusb.hid as hid

VID = 0x1A86
PID = 0xFE07

NUM_LEDS_PER_GROUP = 12
NUM_GROUPS = 3
TOTAL_LEDS = NUM_LEDS_PER_GROUP * NUM_GROUPS  # 36

HEADER = bytes([0x53, 0x43, 0x00, 0xB1, 0xBF, 0x80, 0x01])
BUFFER_SIZE = 192


class DXLightController:
    def __init__(self):
        self.device = None
        self.output_report = None
        self.counter = 0
        self.leds = [(0, 0, 0)] * TOTAL_LEDS  # (R, G, B) per LED

    def connect(self):
        """Verbindet sich mit dem DX-Light Strip."""
        devices = hid.HidDeviceFilter(vendor_id=VID, product_id=PID).get_devices()
        if not devices:
            print("FEHLER: Kein DX-Light Gerät gefunden!")
            print("Ist der Lightstrip per USB eingesteckt?")
            return False

        self.device = devices[0]
        self.device.open()

        out_reports = self.device.find_output_reports()
        if not out_reports:
            print("FEHLER: Kein Output Report gefunden!")
            return False

        self.output_report = out_reports[0]
        print(f"Verbunden: {self.device.vendor_name} {self.device.product_name}")
        print(f"  VID:PID = 0x{VID:04X}:0x{PID:04X}")
        print(f"  {TOTAL_LEDS} LEDs ({NUM_GROUPS} Gruppen × {NUM_LEDS_PER_GROUP})")
        return True

    def disconnect(self):
        """Trennt die Verbindung."""
        if self.device:
            try:
                self.device.close()
            except:
                pass
            self.device = None
            print("Getrennt.")

    def _build_buffer(self):
        """Baut den 192-Byte Puffer aus dem aktuellen LED-Zustand.
        
        Das C++ Original legt die 3 LED-Arrays zusammenhängend im Speicher:
          dataLed1[0..11], dataLed2[0..11], dataLed3[0..11]
        und schreibt dann:
          1) dataLed1[0] separat (3 Bytes)
          2) Block ab dataLed1[1] für 12 LEDs (liest in dataLed2 hinein)
          3) Block ab dataLed2[0] für 12 LEDs
          4) Block ab dataLed3[0] für 12 LEDs
        Wir replizieren das, indem wir alle LEDs konkatinieren.
        """
        buf = bytearray(BUFFER_SIZE)

        # Header (7 Bytes)
        buf[0:7] = HEADER
        buf[4] = self.counter & 0xFF
        self.counter = (self.counter + 1) & 0xFF

        # Gruppen aufbauen (wie im C++: left reversed, top normal, right normal)
        left_leds = list(reversed(self.leds[0:12]))
        top_leds = list(self.leds[12:24])
        right_leds = list(self.leds[24:36])

        # Alle zusammenhängend (wie C++ Stack-Layout)
        all_leds = left_leds + top_leds + right_leds  # 36 entries

        ptr = 7

        # Erste LED separat (3 Bytes: R, G, B)
        r, g, b = all_leds[0]
        buf[ptr] = r & 0xFF
        buf[ptr + 1] = g & 0xFF
        buf[ptr + 2] = b & 0xFF
        ptr += 3

        # LED Counter für die Blöcke
        led_counter = 0x01

        # Block-Schreibfunktion: 12 LEDs × 5 Bytes (2 counter + R + G + B)
        def write_block(start_idx):
            nonlocal ptr, led_counter
            for i in range(12):
                buf[ptr] = led_counter & 0xFF
                led_counter += 1
                buf[ptr + 1] = led_counter & 0xFF
                led_counter += 1
                r, g, b = all_leds[start_idx + i]
                buf[ptr + 2] = r & 0xFF
                buf[ptr + 3] = g & 0xFF
                buf[ptr + 4] = b & 0xFF
                ptr += 5

        # Block 1: ab Index 1 (left_leds[1..11] + top_leds[0])
        write_block(1)
        # Block 2: ab Index 12 (top_leds[0..11])
        write_block(12)
        # Block 3: ab Index 24 (right_leds[0..11])
        write_block(24)

        return buf

    def send(self):
        """Sendet den aktuellen LED-Zustand an den Strip."""
        if not self.device:
            return False

        buf = self._build_buffer()

        # Sende 3 × 64-Byte Chunks als HID Output Reports
        try:
            for i in range(3):
                chunk = buf[i * 64:(i + 1) * 64]
                # pywinusb erwartet Report ID als erstes Byte
                report_data = bytes([0x00]) + bytes(chunk)
                self.output_report.set_raw_data(list(report_data))
                self.output_report.send()
            return True
        except Exception as e:
            print(f"Sendefehler: {e}")
            return False

    # ==========================================
    # High-Level Steuerfunktionen
    # ==========================================

    def set_all(self, r, g, b):
        """Setzt alle LEDs auf eine Farbe."""
        self.leds = [(r, g, b)] * TOTAL_LEDS
        self.send()

    def set_led(self, index, r, g, b):
        """Setzt eine einzelne LED."""
        if 0 <= index < TOTAL_LEDS:
            self.leds[index] = (r, g, b)

    def set_group(self, group, r, g, b):
        """Setzt eine ganze Gruppe (0=Links, 1=Oben, 2=Rechts)."""
        start = group * NUM_LEDS_PER_GROUP
        for i in range(NUM_LEDS_PER_GROUP):
            self.leds[start + i] = (r, g, b)

    def off(self):
        """Schaltet alle LEDs aus."""
        self.set_all(0, 0, 0)

    def set_brightness(self, factor):
        """Skaliert alle LEDs um einen Helligkeitsfaktor (0.0 - 1.0)."""
        factor = max(0.0, min(1.0, factor))
        self.leds = [
            (int(r * factor), int(g * factor), int(b * factor))
            for r, g, b in self.leds
        ]
        self.send()

    def rainbow(self, offset=0.0):
        """Setzt einen Regenbogen über alle LEDs."""
        for i in range(TOTAL_LEDS):
            hue = (i / TOTAL_LEDS + offset) % 1.0
            r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
            self.leds[i] = (int(r * 255), int(g * 255), int(b * 255))
        self.send()

    def breathing(self, r, g, b, speed=1.0, duration=5.0):
        """Atmungseffekt in einer bestimmten Farbe."""
        start = time.time()
        while time.time() - start < duration:
            t = (time.time() - start) * speed
            brightness = (math.sin(t * math.pi) + 1) / 2
            self.set_all(
                int(r * brightness),
                int(g * brightness),
                int(b * brightness)
            )
            time.sleep(0.03)

    def color_cycle(self, speed=1.0, duration=10.0):
        """Farbzyklus-Animation."""
        start = time.time()
        while time.time() - start < duration:
            t = (time.time() - start) * speed
            hue = (t * 0.1) % 1.0
            r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
            self.set_all(int(r * 255), int(g * 255), int(b * 255))
            time.sleep(0.03)

    def rainbow_wave(self, speed=1.0, duration=10.0):
        """Regenbogen-Wellen-Animation."""
        start = time.time()
        while time.time() - start < duration:
            offset = (time.time() - start) * speed * 0.2
            self.rainbow(offset)
            time.sleep(0.03)

    def demo(self):
        """Demo-Sequenz mit verschiedenen Effekten."""
        print("\n--- Demo-Sequenz ---")

        print("1/6: Rot")
        self.set_all(255, 0, 0)
        time.sleep(1)

        print("2/6: Grün")
        self.set_all(0, 255, 0)
        time.sleep(1)

        print("3/6: Blau")
        self.set_all(0, 0, 255)
        time.sleep(1)

        print("4/6: Gruppen einzeln (L=Rot, O=Grün, R=Blau)")
        self.set_group(0, 255, 0, 0)
        self.set_group(1, 0, 255, 0)
        self.set_group(2, 0, 0, 255)
        self.send()
        time.sleep(2)

        print("5/6: Regenbogen-Welle (5s)")
        self.rainbow_wave(speed=2.0, duration=5.0)

        print("6/6: Atmung Cyan (5s)")
        self.breathing(0, 255, 255, speed=2.0, duration=5.0)

        print("Demo fertig!")
        self.off()


def parse_color_name(name):
    """Wandelt Farbnamen in RGB um."""
    colors = {
        'red': (255, 0, 0), 'rot': (255, 0, 0),
        'green': (0, 255, 0), 'grün': (0, 255, 0), 'gruen': (0, 255, 0),
        'blue': (0, 0, 255), 'blau': (0, 0, 255),
        'white': (255, 255, 255), 'weiß': (255, 255, 255), 'weiss': (255, 255, 255),
        'yellow': (255, 255, 0), 'gelb': (255, 255, 0),
        'cyan': (0, 255, 255),
        'magenta': (255, 0, 255),
        'orange': (255, 128, 0),
        'purple': (128, 0, 255), 'lila': (128, 0, 255),
        'pink': (255, 0, 128), 'rosa': (255, 0, 128),
        'warm': (255, 180, 100), 'warmweiß': (255, 180, 100),
    }
    return colors.get(name.lower())


def interactive_menu(ctrl):
    """Interaktives Menü."""
    print("\n" + "=" * 50)
    print("  DX-Light Controller — Interaktives Menü")
    print("=" * 50)
    print()
    print("Befehle:")
    print("  color R G B    — Farbe setzen (0-255)")
    print("  rot/grün/blau  — Vordefinierte Farbe")
    print("  rainbow        — Regenbogen")
    print("  wave           — Regenbogen-Welle")
    print("  breathe R G B  — Atmungseffekt")
    print("  cycle          — Farbzyklus")
    print("  group G R G B  — Gruppe setzen (0-2)")
    print("  led I R G B    — Einzelne LED setzen")
    print("  brightness X   — Helligkeit (0-100)")
    print("  demo           — Demo-Sequenz")
    print("  off            — Aus")
    print("  quit           — Beenden")
    print()

    while True:
        try:
            cmd = input("> ").strip().lower().split()
            if not cmd:
                continue

            action = cmd[0]

            if action in ('quit', 'exit', 'q'):
                ctrl.off()
                break
            elif action == 'off':
                ctrl.off()
                print("LEDs aus.")
            elif action == 'on':
                ctrl.set_all(255, 255, 255)
                print("LEDs an (weiß).")
            elif action == 'demo':
                ctrl.demo()
            elif action == 'rainbow':
                ctrl.rainbow()
            elif action == 'wave':
                print("Regenbogen-Welle (Ctrl+C zum Stoppen)")
                try:
                    ctrl.rainbow_wave(speed=2.0, duration=300)
                except KeyboardInterrupt:
                    pass
            elif action == 'cycle':
                print("Farbzyklus (Ctrl+C zum Stoppen)")
                try:
                    ctrl.color_cycle(speed=2.0, duration=300)
                except KeyboardInterrupt:
                    pass
            elif action == 'breathe' and len(cmd) >= 4:
                r, g, b = int(cmd[1]), int(cmd[2]), int(cmd[3])
                print(f"Atmung ({r},{g},{b}) — Ctrl+C zum Stoppen")
                try:
                    ctrl.breathing(r, g, b, speed=2.0, duration=300)
                except KeyboardInterrupt:
                    pass
            elif action == 'color' and len(cmd) >= 4:
                r, g, b = int(cmd[1]), int(cmd[2]), int(cmd[3])
                ctrl.set_all(r, g, b)
                print(f"Farbe: ({r}, {g}, {b})")
            elif action == 'group' and len(cmd) >= 5:
                g_idx = int(cmd[1])
                r, g, b = int(cmd[2]), int(cmd[3]), int(cmd[4])
                ctrl.set_group(g_idx, r, g, b)
                ctrl.send()
                names = ['Links', 'Oben', 'Rechts']
                print(f"Gruppe {names[g_idx]}: ({r}, {g}, {b})")
            elif action == 'led' and len(cmd) >= 5:
                idx = int(cmd[1])
                r, g, b = int(cmd[2]), int(cmd[3]), int(cmd[4])
                ctrl.set_led(idx, r, g, b)
                ctrl.send()
                print(f"LED {idx}: ({r}, {g}, {b})")
            elif action == 'brightness' and len(cmd) >= 2:
                val = float(cmd[1]) / 100.0
                ctrl.set_brightness(val)
                print(f"Helligkeit: {int(val * 100)}%")
            elif parse_color_name(action):
                r, g, b = parse_color_name(action)
                ctrl.set_all(r, g, b)
                print(f"{action}: ({r}, {g}, {b})")
            else:
                print(f"Unbekannter Befehl: {' '.join(cmd)}")

        except KeyboardInterrupt:
            print("\nBeendet.")
            ctrl.off()
            break
        except ValueError as e:
            print(f"Ungültiger Wert: {e}")
        except Exception as e:
            print(f"Fehler: {e}")


def main():
    ctrl = DXLightController()

    if not ctrl.connect():
        sys.exit(1)

    try:
        if len(sys.argv) > 1:
            cmd = sys.argv[1].lower()

            if cmd == 'off':
                ctrl.off()
                print("LEDs aus.")
            elif cmd == 'on':
                ctrl.set_all(255, 255, 255)
                print("LEDs an.")
            elif cmd == 'demo':
                ctrl.demo()
            elif cmd == 'rainbow':
                ctrl.rainbow()
                print("Regenbogen gesetzt.")
            elif cmd == 'wave':
                print("Regenbogen-Welle — Ctrl+C zum Stoppen")
                try:
                    ctrl.rainbow_wave(speed=2.0, duration=300)
                except KeyboardInterrupt:
                    ctrl.off()
            elif cmd == 'color' and len(sys.argv) >= 5:
                r, g, b = int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
                ctrl.set_all(r, g, b)
                print(f"Farbe: ({r}, {g}, {b})")
            elif parse_color_name(cmd):
                r, g, b = parse_color_name(cmd)
                ctrl.set_all(r, g, b)
                print(f"{cmd}: ({r}, {g}, {b})")
            else:
                print(f"Unbekannter Befehl: {cmd}")
                interactive_menu(ctrl)
        else:
            interactive_menu(ctrl)
    finally:
        ctrl.disconnect()


if __name__ == "__main__":
    main()
