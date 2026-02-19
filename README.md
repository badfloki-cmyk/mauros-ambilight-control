# Mauro DX-Light Ambilight Control

Ein performantes Ambilight-Tool für den **DX-Light LED-Strip** (Robobloq USB HID).

## Features
- 🚀 **Performance**: Schneller Screen-Capture via `mss` mit optimiertem Numpy Edge-Slicing — CPU-schonend.
- 🎨 **Diverse Modi**:
  - **Ambilight**: Echtzeit-Bildschirmsynchronisation (manuell konfigurierbar).
  - **🎮 Gaming**: Reaktiv & schnell (niedriges Smoothing, hoher FPS-Target).
  - **🎬 Film**: Sanft & atmosphärisch (hohes Smoothing, breiter Rand).
  - **Statisch**: Wähle eine feste Farbe über den Color-Picker.
  - **Effekte**: Rainbow, Breathing, Color Cycle.
- 📺 **Aspekt-Ratio Support**: Automatischer Crop für 21:9, 16:9, Kino-Formate usw.
- ⚙️ **System-Integration**:
  - **Autostart**: Startet optional mit Windows.
  - **Persistenz**: Speichert alle Einstellungen in einer JSON-Datei.
  - **Auto-Start Mode**: Geht beim Öffnen direkt in den letzten Modus.

## Hardware-Anforderungen
- DX-Light LED-Strip (USB HID VID: 0x1A86, PID: 0xFE07).
- Windows 10/11.

## Installation (Python)
1. Repository klonen.
2. Abhängigkeiten installieren: `pip install -r requirements.txt`.
3. Starten: `python ambilight.py`.

## Standalone EXE
Die vorkompilierte EXE kann direkt gestartet werden und benötigt keine Python-Installation.

---
*Entwickelt von Mauro*
