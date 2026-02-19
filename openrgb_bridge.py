"""
DX-Light ↔ OpenRGB Bridge
==========================
Verbindet den DX-Light Lumtang LED-Strip mit OpenRGB.
Liest Farben von einem OpenRGB-Gerät und spiegelt sie auf den Strip.

Voraussetzung:
 1. OpenRGB muss laufen mit aktiviertem SDK Server (Einstellungen → SDK Server → Port 6742)
 2. Mindestens ein RGB-Gerät muss in OpenRGB erkannt sein.

Nutzung:
 python openrgb_bridge.py              # Automatisch erstes Gerät mit ≥36 LEDs
 python openrgb_bridge.py --list       # Alle Geräte auflisten
 python openrgb_bridge.py --device 0   # Bestimmtes Gerät nach Index
"""

import sys, os, time, argparse, threading

# DX-Light Controller importieren
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dx_light_control import DXLightController

try:
    from openrgb import OpenRGBClient
    from openrgb.utils import RGBColor
except ImportError:
    print("❌ openrgb-python nicht installiert!")
    print("   pip install openrgb-python")
    sys.exit(1)


def list_devices(client):
    """Alle OpenRGB-Geräte auflisten."""
    print("\n📋 OpenRGB Geräte:")
    print("-" * 60)
    for i, dev in enumerate(client.devices):
        n_leds = len(dev.leds)
        print(f"  [{i}] {dev.name} — {n_leds} LEDs ({dev.type})")
    print()


def find_best_device(client, preferred_idx=None):
    """Bestes Gerät auswählen (≥36 LEDs oder Index)."""
    devices = client.devices
    if not devices:
        print("❌ Keine Geräte in OpenRGB gefunden!")
        return None

    if preferred_idx is not None:
        if 0 <= preferred_idx < len(devices):
            return devices[preferred_idx]
        print(f"❌ Gerät [{preferred_idx}] nicht gefunden (nur {len(devices)} vorhanden)")
        return None

    # Erstes Gerät mit ≥36 LEDs bevorzugen
    for dev in devices:
        if len(dev.leds) >= 36:
            return dev
    # Sonst erstes Gerät
    return devices[0]


def sample_device_colors(device, n_leds=36):
    """Farben vom OpenRGB-Gerät auf 36 LEDs mappen."""
    colors = device.colors
    n_src = len(colors)

    if n_src == 0:
        return [(0, 0, 0)] * n_leds

    leds = []
    for i in range(n_leds):
        # Gleichmäßig über die Quell-LEDs verteilen
        src_idx = int(i * n_src / n_leds) % n_src
        c = colors[src_idx]
        leds.append((c.red, c.green, c.blue))

    return leds


def run_bridge(client, device, fps=30):
    """Hauptloop: OpenRGB → DX-Light."""
    ctrl = DXLightController()

    if not ctrl.connect():
        print("❌ DX-Light Strip nicht gefunden!")
        print("   Stelle sicher, dass der Strip per USB angeschlossen ist.")
        return

    ft = 1.0 / fps
    print(f"\n🔗 Bridge aktiv: '{device.name}' → DX-Light Strip")
    print(f"   {len(device.leds)} LEDs → 36 LEDs @ {fps} FPS")
    print(f"   Drücke Ctrl+C zum Beenden.\n")

    try:
        while True:
            t0 = time.perf_counter()

            # Farben vom OpenRGB-Gerät lesen
            try:
                device.update()
            except:
                pass

            leds = sample_device_colors(device)
            ctrl.leds = leds

            try:
                ctrl.send()
            except Exception as e:
                print(f"⚠️  USB-Fehler: {e}")
                break

            elapsed = time.perf_counter() - t0
            wait = ft - elapsed
            if wait > 0:
                time.sleep(wait)

    except KeyboardInterrupt:
        print("\n\n🛑 Bridge gestoppt.")
    finally:
        ctrl.off()
        ctrl.send()
        ctrl.disconnect()
        print("   DX-Light getrennt. Auf Wiedersehen! 👋")


def main():
    parser = argparse.ArgumentParser(
        description="DX-Light ↔ OpenRGB Bridge",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Voraussetzung: OpenRGB mit aktiviertem SDK Server (Port 6742)"
    )
    parser.add_argument("--list", action="store_true",
                        help="Alle OpenRGB-Geräte auflisten")
    parser.add_argument("--device", "-d", type=int, default=None,
                        help="Geräte-Index (siehe --list)")
    parser.add_argument("--fps", type=int, default=30,
                        help="Updates pro Sekunde (Standard: 30)")
    parser.add_argument("--host", default="127.0.0.1",
                        help="OpenRGB SDK Host (Standard: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=6742,
                        help="OpenRGB SDK Port (Standard: 6742)")
    args = parser.parse_args()

    # OpenRGB verbinden
    print("🔌 Verbinde mit OpenRGB SDK Server...")
    try:
        client = OpenRGBClient(args.host, args.port, name="DX-Light Bridge")
    except ConnectionRefusedError:
        print(f"❌ Kann nicht mit OpenRGB verbinden ({args.host}:{args.port})")
        print("   1. Öffne OpenRGB")
        print("   2. Gehe zu Einstellungen → SDK Server")
        print("   3. Aktiviere 'Start Server' auf Port 6742")
        sys.exit(1)

    print(f"✅ Verbunden! {len(client.devices)} Gerät(e) gefunden.")

    if args.list:
        list_devices(client)
        return

    device = find_best_device(client, args.device)
    if device is None:
        list_devices(client)
        return

    run_bridge(client, device, args.fps)


if __name__ == "__main__":
    main()
