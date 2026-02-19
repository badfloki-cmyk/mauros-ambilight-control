"""
Mauros DX-Light Ambilight Control
==================================
Ambilight + Static/Rainbow/Breathing/Cycle Modes, Windows-Autostart,
persistente Einstellungen.
"""

import sys, os, time, threading, colorsys, math, json
import tkinter as tk
from tkinter import ttk, colorchooser
import numpy as np
import pywinusb.hid as hid

import mss

# === Hardware ===
VID, PID = 0x1A86, 0xFE07
HEADER = bytes([0x53, 0x43, 0x00, 0xB1, 0x00, 0x80, 0x01])
N = 12

ASPECT_RATIOS = {
    "Vollbild (Monitor)": None,
    "16:9":   (16, 9),
    "16:10":  (16, 10),
    "21:9":   (21, 9),
    "32:9":   (32, 9),
    "4:3":    (4, 3),
    "2.35:1 (Kino)": (2.35, 1),
    "2.39:1 (Kino)": (2.39, 1),
    "1:1":    (1, 1),
}

MODES = ["Ambilight", "🎮 Gaming", "🎬 Film", "Statisch", "Rainbow", "Breathing", "Color Cycle"]

# Presets: (smoothing%, fps, edge%)
MODE_PRESETS = {
    "🎮 Gaming": (10, 144, 4),   # Reaktiv, schnell, schmaler Rand
    "🎬 Film":   (50, 60, 10),   # Sanft, cinematisch, breiter Rand
}

# === Theme ===
BG        = "#0d1117"
BG_CARD   = "#161b22"
BG_INPUT  = "#21262d"
FG        = "#e6edf3"
FG_DIM    = "#7d8590"
ACCENT    = "#58a6ff"
ACCENT2   = "#3fb950"
RED       = "#f85149"
BORDER    = "#30363d"


# =============================================================================
# Config Persistence
# =============================================================================

def get_config_path():
    """Config neben der EXE/Script speichern."""
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "dxlight_config.json")

DEFAULT_CONFIG = {
    "mode": "Ambilight",
    "brightness": 80,
    "smooth": 25,
    "fps": 90,
    "edge": 6,
    "speed": 50,
    "mirror": False,
    "aspect": "Vollbild (Monitor)",
    "color": [255, 0, 80],
    "autostart_windows": False,
    "autostart_mode": False,   # Auto-Start beim Öffnen
}

def load_config():
    path = get_config_path()
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                saved = json.load(f)
            cfg.update(saved)
        except: pass
    return cfg

def save_config(cfg):
    try:
        with open(get_config_path(), "w") as f:
            json.dump(cfg, f, indent=2)
    except: pass


# =============================================================================
# Tooltip
# =============================================================================

class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, event=None):
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        self.tip.attributes("-topmost", True)
        frame = tk.Frame(self.tip, bg="#1c2128", bd=1, relief="solid",
                         highlightbackground=BORDER, highlightthickness=1)
        frame.pack()
        tk.Label(frame, text=self.text, bg="#1c2128", fg=FG,
                 font=("Segoe UI", 8), padx=8, pady=4,
                 wraplength=280, justify="left").pack()

    def _hide(self, event=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


# =============================================================================
# Autostart
# =============================================================================

def get_startup_folder():
    return os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows",
                        "Start Menu", "Programs", "Startup")

def get_exe_path():
    if getattr(sys, 'frozen', False):
        return sys.executable
    return os.path.abspath(__file__)

def is_autostart_enabled():
    bat = os.path.join(get_startup_folder(), "DX-Light-Ambilight.bat")
    lnk = os.path.join(get_startup_folder(), "DX-Light-Ambilight.lnk")
    return os.path.exists(bat) or os.path.exists(lnk)

def set_autostart(enable):
    startup = get_startup_folder()
    bat_path = os.path.join(startup, "DX-Light-Ambilight.bat")
    lnk_path = os.path.join(startup, "DX-Light-Ambilight.lnk")
    for p in (bat_path, lnk_path):
        if os.path.exists(p):
            try: os.remove(p)
            except: pass
    if enable:
        exe = get_exe_path()
        if exe.endswith(".exe"):
            with open(bat_path, "w") as f:
                f.write(f'@echo off\nstart "" /min "{exe}"\n')
        else:
            pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
            if not os.path.exists(pythonw): pythonw = sys.executable
            with open(bat_path, "w") as f:
                f.write(f'@echo off\nstart "" /min "{pythonw}" "{exe}"\n')


# =============================================================================
# USB
# =============================================================================

def find_device():
    devs = hid.HidDeviceFilter(vendor_id=VID, product_id=PID).get_devices()
    return devs[0] if devs else None


def build_and_send(out, leds, cnt, mirror=False):
    buf = bytearray(192)
    buf[0:7] = HEADER
    buf[4] = cnt & 0xFF
    if mirror:
        left_src  = leds[24:36][::-1]
        right_src = leds[0:12][::-1]
        top_src   = list(reversed(leds[12:24]))
    else:
        left_src  = leds[0:12]
        right_src = leds[24:36]
        top_src   = list(leds[12:24])
    left = [left_src[11-i] for i in range(N)]
    a = left + top_src + list(right_src)
    buf[7], buf[8], buf[9] = a[0]
    p, c = 10, 1
    for s in (1, 12, 24):
        for i in range(12):
            buf[p] = c & 0xFF; c += 1
            buf[p+1] = c & 0xFF; c += 1
            buf[p+2], buf[p+3], buf[p+4] = a[s+i]
            p += 5
    for i in range(3):
        out.set_raw_data([0x00] + list(buf[i*64:(i+1)*64]))
        out.send()


def calc_region(mon_w, mon_h, aspect):
    if aspect is None:
        return (0.0, 0.0, 0.0, 0.0)
    aw, ah = aspect
    target_ratio = aw / ah
    mon_ratio = mon_w / mon_h
    if abs(target_ratio - mon_ratio) < 0.01:
        return (0.0, 0.0, 0.0, 0.0)
    if target_ratio < mon_ratio:
        content_w = mon_h * target_ratio
        pct = (mon_w - content_w) / 2 / mon_w
        return (pct, 0.0, pct, 0.0)
    else:
        content_h = mon_w / target_ratio
        pct = (mon_h - content_h) / 2 / mon_h
        return (0.0, pct, 0.0, pct)


# =============================================================================
# Engine
# =============================================================================

class LedEngine:
    def __init__(self):
        self.running = False
        self.thread = None
        self.device = None
        self.out = None
        self.cnt = 0
        self.mode = "Ambilight"
        self.static_color = (255, 0, 80)
        self.effect_speed = 50
        self.brightness = 0.8
        self.smooth = 0.25
        self.target_fps = 90
        self.edge_pct = 0.06
        self.mirror = False
        self.crop = (0.0, 0.0, 0.0, 0.0)
        self.monitor_idx = 1
        self.actual_fps = 0.0
        self.current_leds = [(0,0,0)] * 36
        self.connected = False

    def connect(self):
        d = find_device()
        if not d: return False
        d.open()
        self.device = d
        self.out = d.find_output_reports()[0]
        self.connected = True
        return True

    def disconnect(self):
        if self.device:
            try:
                build_and_send(self.out, [(0,0,0)]*36, self.cnt)
                self.device.close()
            except: pass
            self.device = None; self.out = None; self.connected = False

    def start(self):
        if self.running: return
        if not self.connected and not self.connect(): return
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread: self.thread.join(timeout=2); self.thread = None
        if self.connected:
            try: build_and_send(self.out, [(0,0,0)]*36, self.cnt)
            except: pass

    def _gen_static(self):
        r, g, b = self.static_color
        bri = self.brightness
        return [(int(r*bri), int(g*bri), int(b*bri))] * 36

    def _gen_rainbow(self, t):
        speed = self.effect_speed / 50.0
        bri = self.brightness
        leds = []
        for i in range(36):
            hue = (t * speed * 0.3 + i / 36.0) % 1.0
            r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
            leds.append((int(r*255*bri), int(g*255*bri), int(b*255*bri)))
        return leds

    def _gen_breathing(self, t):
        speed = self.effect_speed / 50.0
        bri = self.brightness
        pulse = (math.sin(t * speed * 1.5) + 1.0) / 2.0
        r, g, b = self.static_color
        v = pulse * bri
        return [(int(r*v), int(g*v), int(b*v))] * 36

    def _gen_cycle(self, t):
        speed = self.effect_speed / 50.0
        bri = self.brightness
        hue = (t * speed * 0.1) % 1.0
        r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
        return [(int(r*255*bri), int(g*255*bri), int(b*255*bri))] * 36

    def _sample_from_frame(self, frame, bri):
        """Vectorized: downsample → edge-slice → reshape+mean in 3 numpy ops."""
        h, w = frame.shape[:2]
        cl, ct, cr_, cb = self.crop
        x0 = int(w * cl)
        y0 = int(h * ct)
        x1 = max(x0+1, int(w * (1.0 - cr_)))
        y1 = max(y0+1, int(h * (1.0 - cb)))

        # Downsample auf ~360p für schnellere Verarbeitung - keine float-Konvertierung mehr
        scale = max(1, min(x1-x0, y1-y0) // 360)
        region = frame[y0:y1:scale, x0:x1:scale]
        # Nur einmal am Ende konvertieren oder direkt mit uint8 rechnen
        rh, rw = region.shape[:2]
        edge = max(1, int(min(rw, rh) * self.edge_pct))

        leds = [None] * 36

        # Links (unten→oben) — vectorized
        left = region[:, :edge]
        lh = left.shape[0]
        zone_h = lh // N
        if zone_h > 0:
            # Reshape zu (N, zone_h, edge, 3) → mean über (1,2)
            # Erst hier in float wandeln für präzisen Mean
            means = left[:zone_h*N].reshape(N, zone_h, edge, 3).mean(axis=(1,2))
            for i in range(N):
                idx = N - 1 - i  # unten→oben
                leds[i] = (min(255,int(means[idx,0]*bri)),
                           min(255,int(means[idx,1]*bri)),
                           min(255,int(means[idx,2]*bri)))
        else:
            a = left.mean(axis=(0,1))
            c = (min(255,int(a[0]*bri)), min(255,int(a[1]*bri)), min(255,int(a[2]*bri)))
            for i in range(N): leds[i] = c

        # Oben (links→rechts) — vectorized
        top = region[:edge, :]
        tw = top.shape[1]
        zone_w = tw // N
        if zone_w > 0:
            # Transpose um Spalten-Zonen zu machen: (W', edge, 3) → reshape
            # Erst hier in float wandeln für präzisen Mean
            means = top[:, :zone_w*N].transpose(1,0,2).reshape(N, zone_w, edge, 3).mean(axis=(1,2))
            for i in range(N):
                leds[12+i] = (min(255,int(means[i,0]*bri)),
                              min(255,int(means[i,1]*bri)),
                              min(255,int(means[i,2]*bri)))
        else:
            a = top.mean(axis=(0,1))
            c = (min(255,int(a[0]*bri)), min(255,int(a[1]*bri)), min(255,int(a[2]*bri)))
            for i in range(N): leds[12+i] = c

        # Rechts (oben→unten) — vectorized
        right = region[:, max(0,rw-edge):]
        rh2 = right.shape[0]
        zone_h2 = rh2 // N
        if zone_h2 > 0:
            # Erst hier in float wandeln für präzisen Mean
            means = right[:zone_h2*N].reshape(N, zone_h2, right.shape[1], 3).mean(axis=(1,2))
            for i in range(N):
                leds[24+i] = (min(255,int(means[i,0]*bri)),
                              min(255,int(means[i,1]*bri)),
                              min(255,int(means[i,2]*bri)))
        else:
            a = right.mean(axis=(0,1))
            c = (min(255,int(a[0]*bri)), min(255,int(a[1]*bri)), min(255,int(a[2]*bri)))
            for i in range(N): leds[24+i] = c

        return leds

    def _loop(self):
        cur = [(0,0,0)] * 36
        fps_t = []
        t_start = time.perf_counter()
        sct = None

        while self.running:
            t0 = time.perf_counter()
            t_elapsed = t0 - t_start
            mode = self.mode
            bri = self.brightness
            alpha = self.smooth
            mirror = self.mirror
            ft = 1.0 / max(1, self.target_fps)

            if mode in ("Ambilight", "🎮 Gaming", "🎬 Film"):
                frame = None
                if sct is None: sct = mss.mss()
                try:
                    mon = sct.monitors[self.monitor_idx]
                    raw = sct.grab(mon)
                    frame = np.array(raw)[:,:,:3]
                    frame = frame[:,:,::-1]  # BGR→RGB
                except: frame = None

                if frame is not None:
                    leds = self._sample_from_frame(frame, bri)
                else:
                    leds = cur
            elif mode == "Statisch":
                leds = self._gen_static()
            elif mode == "Rainbow":
                leds = self._gen_rainbow(t_elapsed)
            elif mode == "Breathing":
                leds = self._gen_breathing(t_elapsed)
            elif mode == "Color Cycle":
                leds = self._gen_cycle(t_elapsed)
            else:
                leds = [(0,0,0)] * 36

            f = 1.0 - alpha
            cur = [(int(c1+(t1-c1)*f), int(c2+(t2-c2)*f), int(c3+(t3-c3)*f))
                   for (c1,c2,c3),(t1,t2,t3) in zip(cur, leds)]

            try:
                build_and_send(self.out, cur, self.cnt, mirror)
                self.cnt = (self.cnt + 1) & 0xFF
            except:
                self.running = False; break

            self.current_leds = list(cur)
            elapsed = time.perf_counter() - t0
            fps_t.append(elapsed)
            if len(fps_t) > 30: fps_t.pop(0)
            self.actual_fps = 1.0 / max(0.001, sum(fps_t)/len(fps_t))
            wait = ft - elapsed
            if wait > 0: time.sleep(wait)

        # Cleanup
        if sct:
            try: sct.close()
            except: pass


# =============================================================================
# GUI
# =============================================================================

class AmbilightGUI:
    def __init__(self):
        self.engine = LedEngine()
        self.cfg = load_config()
        self.root = tk.Tk()
        self.root.title("Mauros DX-Light Ambilight Control")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        with mss.mss() as sct:
            mon = sct.monitors[1]
            self.mon_w, self.mon_h = mon["width"], mon["height"]
        self._build_ui()
        self._apply_config()
        self._update_loop()

        # Auto-Start beim Öffnen
        if self.cfg.get("autostart_mode", False):
            self.root.after(500, self._auto_start)

    def _auto_start(self):
        """Automatisch starten wenn konfiguriert."""
        if not self.engine.running:
            self._toggle()

    def _apply_config(self):
        """Config-Werte in die GUI laden."""
        cfg = self.cfg
        self.mode_var.set(cfg.get("mode", "Ambilight"))
        self.bri_var.set(cfg.get("brightness", 80))
        self.smooth_var.set(cfg.get("smooth", 25))
        self.fps_var.set(cfg.get("fps", 90))
        self.edge_var.set(cfg.get("edge", 6))
        self.speed_var.set(cfg.get("speed", 50))
        self.mirror_var.set(cfg.get("mirror", False))
        self.aspect_var.set(cfg.get("aspect", "Vollbild (Monitor)"))
        self.autostart_win_var.set(cfg.get("autostart_windows", False))
        self.autostart_mode_var.set(cfg.get("autostart_mode", False))
        col = cfg.get("color", [255, 0, 80])
        self.engine.static_color = tuple(col)
        hexc = f"#{col[0]:02x}{col[1]:02x}{col[2]:02x}"
        self.color_btn.configure(bg=hexc)
        self.color_hex_label.configure(text=hexc.upper())
        self._on_mode_change()
        self._on_aspect_change()

    def _gather_config(self):
        """Aktuelle GUI-Werte als Config-Dict sammeln."""
        r, g, b = self.engine.static_color
        return {
            "mode": self.mode_var.get(),
            "brightness": self.bri_var.get(),
            "smooth": self.smooth_var.get(),
            "fps": self.fps_var.get(),
            "edge": self.edge_var.get(),
            "speed": self.speed_var.get(),
            "mirror": self.mirror_var.get(),
            "aspect": self.aspect_var.get(),
            "color": [r, g, b],
            "autostart_windows": self.autostart_win_var.get(),
            "autostart_mode": self.autostart_mode_var.get(),
        }

    def _card(self, parent, title, icon=""):
        frame = tk.Frame(parent, bg=BG_CARD, bd=0, highlightbackground=BORDER,
                         highlightthickness=1, padx=12, pady=8)
        frame.pack(fill="x", pady=(0,5))
        if title:
            tk.Label(frame, text=f"{icon}  {title}" if icon else title,
                     bg=BG_CARD, fg=ACCENT, font=("Segoe UI", 9, "bold"),
                     anchor="w").pack(fill="x", pady=(0,4))
        return frame

    def _slider(self, parent, label, var, from_, to, suffix, tooltip_text):
        row = tk.Frame(parent, bg=BG_CARD)
        row.pack(fill="x", pady=1)
        lbl = tk.Label(row, text=label, bg=BG_CARD, fg=FG,
                       font=("Segoe UI", 9), width=11, anchor="w")
        lbl.pack(side="left")
        Tooltip(lbl, tooltip_text)
        scale = ttk.Scale(row, from_=from_, to=to, variable=var,
                          orient="horizontal", length=165)
        scale.pack(side="left", padx=(0,4))
        Tooltip(scale, tooltip_text)
        val_lbl = tk.Label(row, text=f"{var.get()}{suffix}", bg=BG_CARD, fg=FG_DIM,
                           font=("Segoe UI Semibold", 9), width=5, anchor="e")
        val_lbl.pack(side="left")
        var._label = val_lbl
        var._suffix = suffix

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TScale", background=BG_CARD, troughcolor=BG_INPUT)
        style.configure("TCombobox", fieldbackground=BG_INPUT, background=BG_INPUT,
                         foreground=FG, selectbackground=ACCENT, selectforeground="#fff",
                         arrowcolor=FG, font=("Segoe UI", 9))
        style.map("TCombobox",
                  fieldbackground=[("readonly", BG_INPUT)],
                  foreground=[("readonly", FG)],
                  selectbackground=[("readonly", ACCENT)],
                  selectforeground=[("readonly", "#fff")])
        self.root.option_add("*TCombobox*Listbox.background", BG_INPUT)
        self.root.option_add("*TCombobox*Listbox.foreground", FG)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#fff")
        self.root.option_add("*TCombobox*Listbox.font", ("Segoe UI", 9))
        style.configure("TCheckbutton", background=BG_CARD, foreground=FG,
                         font=("Segoe UI", 9))
        style.map("TCheckbutton", background=[("active", BG_CARD)])

        main = tk.Frame(self.root, bg=BG, padx=10, pady=8)
        main.pack(fill="both", expand=True)

        # ---- Header ----
        hdr = tk.Frame(main, bg=BG)
        hdr.pack(fill="x", pady=(0, 4))
        title_frame = tk.Frame(hdr, bg=BG)
        title_frame.pack(side="left")
        tk.Label(title_frame, text="⚡", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 16)).pack(side="left")
        tk.Label(title_frame, text="Mauro DX-Light Ambilight", bg=BG, fg=FG,
                 font=("Segoe UI", 14, "bold")).pack(side="left", padx=(4,0))
        self.fps_label = tk.Label(hdr, text="— FPS", bg=BG, fg=FG_DIM,
                                  font=("Segoe UI Semibold", 11))
        self.fps_label.pack(side="right")

        self.status_label = tk.Label(main, text="● Nicht verbunden", bg=BG, fg=RED,
                                      font=("Segoe UI", 9))
        self.status_label.pack(anchor="w", pady=(0,4))

        # ---- Modus Card ----
        card_mode = self._card(main, "Modus", "🎨")

        mode_row = tk.Frame(card_mode, bg=BG_CARD)
        mode_row.pack(fill="x")
        lbl = tk.Label(mode_row, text="LED-Modus", bg=BG_CARD, fg=FG,
                       font=("Segoe UI", 9))
        lbl.pack(side="left")
        Tooltip(lbl, "Wähle den LED-Betriebsmodus.\n"
                     "Ambilight = Bildschirmfarben (manuell)\n"
                     "🎮 Gaming = Reaktiv, hohe FPS\n"
                     "🎬 Film = Sanft, cinematisch\n"
                     "Statisch = Feste Farbe\n"
                     "Rainbow = Regenbogen-Animation\n"
                     "Breathing = Pulsierender Effekt\n"
                     "Color Cycle = Langsamer Farbwechsel")

        self.mode_var = tk.StringVar(value="Ambilight")
        mode_combo = ttk.Combobox(mode_row, textvariable=self.mode_var,
                                   values=MODES, state="readonly", width=17)
        mode_combo.pack(side="left", padx=8)
        mode_combo.bind("<<ComboboxSelected>>", self._on_mode_change)

        self.color_btn = tk.Button(mode_row, text="  ", bg="#ff0050", width=3,
                                    relief="flat", bd=0, cursor="hand2",
                                    command=self._pick_color)
        self.color_btn.pack(side="left", padx=(8,4))
        Tooltip(self.color_btn, "Klicke um die LED-Farbe zu wählen.\n"
                                 "Wird bei Statisch und Breathing verwendet.")

        self.color_hex_label = tk.Label(mode_row, text="#FF0050", bg=BG_CARD, fg=FG_DIM,
                                         font=("Segoe UI", 8))
        self.color_hex_label.pack(side="left")

        self.speed_var = tk.IntVar(value=50)
        self._slider(card_mode, "Speed", self.speed_var, 5, 100, "%",
                     "Geschwindigkeit der Animation.\n"
                     "Betrifft Rainbow, Breathing, Color Cycle.")

        # ---- Ambilight Card ----
        self.ambi_card = self._card(main, "Ambilight", "📺")
        fmt_row = tk.Frame(self.ambi_card, bg=BG_CARD)
        fmt_row.pack(fill="x")
        tk.Label(fmt_row, text="Seitenverhältnis", bg=BG_CARD, fg=FG,
                 font=("Segoe UI", 9)).pack(side="left")
        self.aspect_var = tk.StringVar(value="Vollbild (Monitor)")
        combo = ttk.Combobox(fmt_row, textvariable=self.aspect_var,
                             values=list(ASPECT_RATIOS.keys()),
                             state="readonly", width=20)
        combo.pack(side="left", padx=8)
        combo.bind("<<ComboboxSelected>>", self._on_aspect_change)
        Tooltip(combo, "Seitenverhältnis des Videos.\n"
                       "Schneidet schwarze Balken automatisch ab.")
        self.crop_label = tk.Label(fmt_row, text="", bg=BG_CARD, fg=FG_DIM,
                                   font=("Segoe UI", 8))
        self.crop_label.pack(side="left", padx=4)
        tk.Label(self.ambi_card, text=f"Monitor: {self.mon_w} × {self.mon_h}",
                 bg=BG_CARD, fg=FG_DIM, font=("Segoe UI", 8)).pack(anchor="w", pady=(2,0))

        # ---- Einstellungen Card ----
        card_settings = self._card(main, "Einstellungen", "🎛️")
        self.mirror_var = tk.BooleanVar(value=False)
        mirror_cb = ttk.Checkbutton(card_settings, text="Links ↔ Rechts tauschen",
                                     variable=self.mirror_var)
        mirror_cb.pack(anchor="w", pady=(0,2))
        Tooltip(mirror_cb, "Spiegelt die LED-Zuordnung wenn der\n"
                           "Strip andersrum montiert ist.")

        self.bri_var = tk.IntVar(value=80)
        self._slider(card_settings, "Helligkeit", self.bri_var, 0, 100, "%",
                     "Gesamthelligkeit der LEDs (0-100%).")
        self.smooth_var = tk.IntVar(value=25)
        self._slider(card_settings, "Smoothing", self.smooth_var, 0, 90, "%",
                     "Glättung der Farbübergänge.\n0% = sofort, 50% = sanft, 90% = langsam.")
        self.fps_var = tk.IntVar(value=90)
        self._slider(card_settings, "Ziel-FPS", self.fps_var, 15, 144, "",
                     "LED-Updates pro Sekunde.\n60 = Filme, 90-144 = Gaming.")
        self.edge_var = tk.IntVar(value=6)
        self._slider(card_settings, "Randtiefe", self.edge_var, 2, 20, "%",
                     "Wie tief am Bildschirmrand gemessen wird.\nNur relevant im Ambilight-Modus.")

        # ---- System Card ----
        card_sys = self._card(main, "System", "⚙️")

        self.autostart_mode_var = tk.BooleanVar(value=False)
        auto_mode_cb = ttk.Checkbutton(card_sys, text="Beim Öffnen automatisch starten",
                                        variable=self.autostart_mode_var)
        auto_mode_cb.pack(anchor="w")
        Tooltip(auto_mode_cb, "Startet den ausgewählten Modus\n"
                               "automatisch wenn das Programm öffnet.\n"
                               "Alle Einstellungen werden gespeichert.")

        self.autostart_win_var = tk.BooleanVar(value=False)
        auto_win_cb = ttk.Checkbutton(card_sys, text="Mit Windows starten",
                                       variable=self.autostart_win_var,
                                       command=self._toggle_autostart)
        auto_win_cb.pack(anchor="w")
        Tooltip(auto_win_cb, "Startet das Programm automatisch\n"
                              "beim Windows-Login.\n"
                              "Kombiniere mit 'Beim Öffnen starten'\n"
                              "für volles Auto-Ambilight.")

        # ---- LED Vorschau ----
        tk.Label(main, text="LED Vorschau", bg=BG, fg=FG_DIM,
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(3,0))
        self.canvas = tk.Canvas(main, bg="#010409", height=55,
                                highlightthickness=1, highlightbackground=BORDER)
        self.canvas.pack(fill="x", pady=(2,6))

        # ---- Start Button ----
        self.start_btn = tk.Button(
            main, text="▶  S T A R T", command=self._toggle,
            bg=ACCENT2, fg="#ffffff", activebackground="#2ea043",
            activeforeground="#ffffff", font=("Segoe UI", 12, "bold"),
            bd=0, padx=20, pady=6, cursor="hand2", relief="flat"
        )
        self.start_btn.pack(fill="x", ipady=3)
        Tooltip(self.start_btn, "Startet oder stoppt die LEDs.\n"
                                 "Einstellungen werden beim Schließen gespeichert.")

    # ---- Callbacks ----

    def _on_mode_change(self, event=None):
        mode = self.mode_var.get()
        self.engine.mode = mode

        # Presets anwenden
        if mode in MODE_PRESETS:
            smooth_p, fps_p, edge_p = MODE_PRESETS[mode]
            self.smooth_var.set(smooth_p)
            self.fps_var.set(fps_p)
            self.edge_var.set(edge_p)

        # Ambilight-Karte bei allen Capture-Modi zeigen
        if mode in ("Ambilight", "🎮 Gaming", "🎬 Film"):
            self.ambi_card.pack(fill="x", pady=(0,5))
            try:
                children = self.ambi_card.master.winfo_children()
                mode_card_idx = 2  # After header area + status + mode card
                self.ambi_card.pack_configure(after=children[mode_card_idx])
            except: pass
        else:
            self.ambi_card.pack_forget()

    def _pick_color(self):
        r, g, b = self.engine.static_color
        initial = f"#{r:02x}{g:02x}{b:02x}"
        result = colorchooser.askcolor(color=initial, title="LED-Farbe wählen")
        if result and result[0]:
            rgb = tuple(int(c) for c in result[0])
            self.engine.static_color = rgb
            hexc = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
            self.color_btn.configure(bg=hexc)
            self.color_hex_label.configure(text=hexc.upper())

    def _on_aspect_change(self, event=None):
        name = self.aspect_var.get()
        aspect = ASPECT_RATIOS.get(name)
        crop = calc_region(self.mon_w, self.mon_h, aspect)
        self.engine.crop = crop
        if aspect is None:
            self.crop_label.configure(text="→ Gesamter Bildschirm")
        else:
            lr_px = int(self.mon_w * crop[0])
            tb_px = int(self.mon_h * crop[1])
            if lr_px > 0:
                self.crop_label.configure(text=f"→ je {lr_px}px links/rechts")
            elif tb_px > 0:
                self.crop_label.configure(text=f"→ je {tb_px}px oben/unten")
            else:
                self.crop_label.configure(text="→ passt bereits")

    def _toggle(self):
        if self.engine.running:
            self.engine.stop()
            self.start_btn.configure(text="▶  S T A R T", bg=ACCENT2)
            self.status_label.configure(text="● Gestoppt", fg=RED)
        else:
            if not self.engine.connected:
                if not self.engine.connect():
                    self.status_label.configure(text="● Kein Gerät gefunden!", fg=RED)
                    return
            self.engine.start()
            self.start_btn.configure(text="⏹  S T O P", bg="#da3633")
            self.status_label.configure(text=f"● {self.mode_var.get()}", fg=ACCENT2)

    def _toggle_autostart(self):
        set_autostart(self.autostart_win_var.get())

    def _update_loop(self):
        self.engine.brightness = self.bri_var.get() / 100.0
        self.engine.smooth = self.smooth_var.get() / 100.0
        self.engine.target_fps = self.fps_var.get()
        self.engine.edge_pct = self.edge_var.get() / 100.0
        self.engine.mirror = self.mirror_var.get()
        self.engine.mode = self.mode_var.get()
        self.engine.effect_speed = self.speed_var.get()

        for var in (self.bri_var, self.smooth_var, self.fps_var, self.edge_var, self.speed_var):
            if hasattr(var, '_label'):
                var._label.configure(text=f"{var.get()}{var._suffix}")

        if self.engine.running:
            self.fps_label.configure(text=f"{self.engine.actual_fps:.0f} FPS", fg=ACCENT)
        else:
            self.fps_label.configure(text="— FPS", fg=FG_DIM)

        self._draw_preview()

        if not self.engine.running and "STOP" in self.start_btn.cget("text"):
            self.start_btn.configure(text="▶  S T A R T", bg=ACCENT2)
            self.status_label.configure(text="● Verbindung verloren", fg=RED)

        self.root.after(50, self._update_loop)

    def _draw_preview(self):
        c = self.canvas
        c.delete("all")
        w = c.winfo_width() or 400
        h = c.winfo_height() or 55
        leds = self.engine.current_leds
        pad, lw = 3, 12
        for i in range(N):
            y0 = pad + int((h-2*pad)*i/N)
            y1 = pad + int((h-2*pad)*(i+1)/N) - 1
            r, g, b = leds[11-i]
            c.create_rectangle(pad, y0, pad+lw, y1,
                               fill=f"#{r:02x}{g:02x}{b:02x}", outline="")
        tx0, tx1 = pad+lw+2, w-pad-lw-2
        tw = tx1-tx0
        for i in range(N):
            x0 = tx0 + int(tw*i/N)
            x1 = tx0 + int(tw*(i+1)/N) - 1
            r, g, b = leds[12+i]
            c.create_rectangle(x0, pad, x1, pad+lw,
                               fill=f"#{r:02x}{g:02x}{b:02x}", outline="")
        rx = w-pad-lw
        for i in range(N):
            y0 = pad + int((h-2*pad)*i/N)
            y1 = pad + int((h-2*pad)*(i+1)/N) - 1
            r, g, b = leds[24+i]
            c.create_rectangle(rx, y0, rx+lw, y1,
                               fill=f"#{r:02x}{g:02x}{b:02x}", outline="")

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        # Einstellungen speichern
        save_config(self._gather_config())
        self.engine.stop()
        self.engine.disconnect()
        self.root.destroy()


if __name__ == "__main__":
    app = AmbilightGUI()
    app.run()
