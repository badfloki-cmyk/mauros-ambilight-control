"""
USB Device Monitor — Erkennt neue USB-Geräte beim Einstecken.
Starte dieses Script, dann stecke deinen DX-Light Lightstrip ein.
Das Script zeigt dir die VID/PID und alle Details des neuen Geräts.

Keine externen Dependencies nötig — nutzt PowerShell/WMI.
"""

import subprocess
import time
import json
import sys
import os

def run_ps(ps_cmd, timeout=30):
    """Führt PowerShell-Befehl mit UTF-8 Encoding aus."""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        result = subprocess.run(
            ["powershell", "-Command", f"[Console]::OutputEncoding = [Text.Encoding]::UTF8; {ps_cmd}"],
            capture_output=True, timeout=timeout,
            encoding="utf-8", errors="replace"
        )
        return result.stdout
    except Exception as e:
        print(f"Fehler: {e}")
        return None

def get_usb_devices_detailed():
    """Holt USB VID/PID Details via PowerShell."""
    ps_cmd = """
    Get-WmiObject Win32_USBControllerDevice | ForEach-Object {
        $dep = [wmi]($_.Dependent)
        [PSCustomObject]@{
            DeviceID = $dep.DeviceID
            Name = $dep.Name
            Description = $dep.Description
            Manufacturer = $dep.Manufacturer
            Status = $dep.Status
        }
    } | ConvertTo-Json -Depth 3
    """
    output = run_ps(ps_cmd)
    if output and output.strip():
        try:
            devices = json.loads(output)
            if isinstance(devices, dict):
                devices = [devices]
            return {d.get("DeviceID", ""): d for d in devices if d.get("DeviceID")}
        except json.JSONDecodeError as e:
            print(f"JSON Parse Fehler: {e}")
    return {}

def format_device(dev):
    """Formatiert ein Gerät für die Anzeige."""
    device_id = dev.get("DeviceID") or dev.get("InstanceId", "?")
    name = dev.get("Name") or dev.get("FriendlyName", "?")
    desc = dev.get("Description", "?")
    mfg = dev.get("Manufacturer", "?")
    
    # VID/PID extrahieren
    vid = pid = "????"
    did = device_id.upper()
    if "VID_" in did:
        vid = did.split("VID_")[1][:4]
    if "PID_" in did:
        pid = did.split("PID_")[1][:4]
    
    return f"  VID:PID = 0x{vid}:0x{pid}\n  Name: {name}\n  Beschreibung: {desc}\n  Hersteller: {mfg}\n  DeviceID: {device_id}"

def main():
    print("=" * 60)
    print("  USB Device Monitor — DX-Light Lightstrip Erkennung")
    print("=" * 60)
    print()
    print("Lese aktuelle USB-Geräte...")
    
    baseline = get_usb_devices_detailed()
    print(f"Gefunden: {len(baseline)} USB-Geräte bereits verbunden.")
    print()
    
    if "--list" in sys.argv:
        print("Alle aktuell verbundenen USB-Geräte:")
        print("-" * 50)
        for dev_id, dev in sorted(baseline.items()):
            print(format_device(dev))
            print()
        return
    
    print(">>> Stecke jetzt deinen DX-Light Lightstrip per USB ein! <<<")
    print(">>> Drücke Ctrl+C zum Beenden.                           <<<")
    print()
    
    try:
        while True:
            time.sleep(2)
            current = get_usb_devices_detailed()
            
            # Neue Geräte finden
            new_ids = set(current.keys()) - set(baseline.keys())
            if new_ids:
                print("!" * 60)
                print(f"  NEUES USB-GERÄT ERKANNT! ({len(new_ids)} Gerät(e))")
                print("!" * 60)
                for nid in new_ids:
                    dev = current[nid]
                    print()
                    print(format_device(dev))
                    print()
                print("-" * 60)
                
                # Baseline updaten
                baseline = current
            
            # Entfernte Geräte
            removed_ids = set(baseline.keys()) - set(current.keys())
            if removed_ids:
                print(f"[Entfernt: {len(removed_ids)} Gerät(e)]")
                baseline = current
                
    except KeyboardInterrupt:
        print("\nBeendet.")

if __name__ == "__main__":
    main()
