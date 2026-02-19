"""
DX-Light HID Probe — Liest Geräteinformationen und HID-Daten aus.
Nutzt pywinusb (nativ auf Windows, keine extra DLLs nötig).
"""

import pywinusb.hid as hid
import time
import sys

VID = 0x1A86
PID = 0xFE07

received_reports = []

def report_handler(data):
    """Callback für eingehende HID Reports."""
    hex_str = ' '.join(f'{b:02X}' for b in data)
    print(f"  << IN Report: {hex_str}")
    received_reports.append(list(data))

def main():
    print("=" * 60)
    print("  DX-Light HID Probe (pywinusb)")
    print(f"  Suche: VID=0x{VID:04X} PID=0x{PID:04X}")
    print("=" * 60)
    print()
    
    # Alle HID-Geräte mit passender VID/PID finden
    devices = hid.HidDeviceFilter(vendor_id=VID, product_id=PID).get_devices()
    
    if not devices:
        print("KEIN DX-Light Gerät gefunden!")
        print("Ist der Lightstrip per USB eingesteckt?")
        print("\nVersuche alle Geräte mit VID 0x1A86:")
        all_devs = hid.HidDeviceFilter(vendor_id=VID).get_devices()
        for d in all_devs:
            print(f"  PID:0x{d.product_id:04X} - {d.product_name}")
        return
    
    print(f"Gefunden: {len(devices)} Gerät(e)\n")
    
    for i, device in enumerate(devices):
        print(f"--- Gerät {i} ---")
        print(f"  VID:PID       = 0x{device.vendor_id:04X}:0x{device.product_id:04X}")
        print(f"  Produkt       = {device.product_name}")
        print(f"  Hersteller    = {device.vendor_name}")
        print(f"  Version       = {device.version_number}")
        print(f"  Path          = {device.device_path}")
        print()
        
        # Gerät öffnen
        try:
            device.open()
            print("  [VERBUNDEN]")
            
            # Report Descriptor Info
            print("\n  HID Reports:")
            print(f"  Input Reports:   {len(device.find_input_reports())}")
            print(f"  Output Reports:  {len(device.find_output_reports())}")
            print(f"  Feature Reports: {len(device.find_feature_reports())}")
            
            # Input Reports Details
            for rep in device.find_input_reports():
                print(f"\n  Input Report ID {rep.report_id}:")
                for item_key, item_value in rep.items():
                    print(f"    {item_key}: {item_value}")
            
            # Output Reports Details
            for rep in device.find_output_reports():
                print(f"\n  Output Report ID {rep.report_id}:")
                for item_key, item_value in rep.items():
                    print(f"    {item_key}: {item_value}")
            
            # Feature Reports lesen
            for rep in device.find_feature_reports():
                print(f"\n  Feature Report ID {rep.report_id}:")
                try:
                    rep.get()
                    hex_str = ' '.join(f'{b:02X}' for b in rep.get_raw_data())
                    print(f"    Daten: {hex_str}")
                except Exception as e:
                    print(f"    Fehler beim Lesen: {e}")
            
            # Handler setzen und eingehende Daten lesen
            device.set_raw_data_handler(report_handler)
            
            print("\n  Lese eingehende Reports (5 Sekunden)...")
            start = time.time()
            while time.time() - start < 5:
                time.sleep(0.05)
            
            if not received_reports:
                print("  (Keine eingehenden Reports empfangen)")
            
            device.close()
            print("\n  [GETRENNT]")
            
        except Exception as e:
            print(f"  Fehler: {e}")
            try:
                device.close()
            except:
                pass

if __name__ == "__main__":
    main()
