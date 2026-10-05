"""Inside tools/shell-test.sh's private session bus: start a headless GNOME Shell with the wallrice
extension, apply wallpapers with wallrice, and take screenshots (bar styles, transitions)."""
import os
import random
import subprocess
import sys
import time
from pathlib import Path

REPO, OUT = Path(sys.argv[1]), Path(sys.argv[2])
WALLRICE = [sys.executable, str(REPO / "bin" / "wallrice")]
DEST = ["--dest", "org.gnome.Shell", "--object-path", "/io/github/teterw/Wallrice"]


def dconf(key, value):
    subprocess.run(["dconf", "write", key, value], check=True)


def call(method, *args, timeout=10):
    return subprocess.run(["gdbus", "call", "--session", *DEST, "--method", f"io.github.teterw.Wallrice.{method}",
                           *args], capture_output=True, text=True, timeout=timeout)


def shot(name):
    p = OUT / f"{name}.png"
    call("DevScreenshot", f"'{p}'")
    return p


def wait_for(fn, timeout=40, step=0.25):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if fn():
            return True
        time.sleep(step)
    return False


def main():
    walls = Path(os.environ["WALLRICE_WALLS"])
    pics = sorted(p for p in walls.rglob("*") if p.suffix.lower() in (".jpg", ".png", ".webp") and ".git" not in p.parts)
    random.seed(11)
    space = [p for p in pics if p.parts[len(walls.parts)] == "space"] or pics
    picks = random.sample(space, 4) + random.sample(pics, 2)
    dconf("/org/gnome/shell/disable-user-extensions", "false")
    dconf("/org/gnome/shell/enabled-extensions", "['wallrice@teterw.github.io', 'dash-to-dock@micxgx.gmail.com']")
    dconf("/org/gnome/desktop/interface/enable-animations", "true")
    dconf("/org/gnome/shell/welcome-dialog-last-shown-version", "'999'")
    dconf("/org/gnome/desktop/background/picture-uri", f"'{picks[0].as_uri()}'")
    dconf("/org/gnome/desktop/background/picture-uri-dark", f"'{picks[0].as_uri()}'")
    log = open(OUT / "shell.log", "w")
    shell = subprocess.Popen(["gnome-shell", "--headless", "--virtual-monitor", "1920x1080", "--wayland", "--no-x11",
                              "--force-animations"], stdout=log, stderr=subprocess.STDOUT,
                             env={**os.environ, "WALLRICE_DEV": "1"})
    try:
        if not wait_for(lambda: call("Version").returncode == 0):
            print("the extension never came up; see shell.log", file=sys.stderr)
            return 1
        print("extension", call("Version").stdout.strip())
        time.sleep(2)
        env = dict(os.environ)
        sock = next(Path(env["XDG_RUNTIME_DIR"]).glob("wayland-*[0-9]"), None)
        subprocess.run([*WALLRICE, "apply", str(picks[0]), "--effect", "none"], check=True)
        window = None
        if sock:  # a window, so the title island has something to show
            window = subprocess.Popen([sys.executable, "-c", WINDOW], env={**env, "WAYLAND_DISPLAY": sock.name,
                                                                           "GDK_BACKEND": "wayland"})
        time.sleep(3)
        shot("desktop")
        for n in range(1, 10):
            subprocess.run([*WALLRICE, "bar", str(n)], check=True, capture_output=True)
            time.sleep(1.2)
            shot(f"bar-{n}")
        subprocess.run([*WALLRICE, "bar", "1"], check=True, capture_output=True)
        subprocess.run([*WALLRICE, "off", "topbar", "taskbar-icons", "dock"], check=True, capture_output=True)
        time.sleep(1.5)
        shot("parts-off")
        subprocess.run([*WALLRICE, "on", "topbar", "taskbar-icons", "dock"], check=True, capture_output=True)
        time.sleep(1.5)
        shot("parts-on")
        for i, effect in enumerate(("grow", "wipe", "wave", "fade"), 1):
            time.sleep(1.5)
            p = subprocess.Popen([*WALLRICE, "apply", str(picks[i]), "--effect", effect], stdout=subprocess.DEVNULL)
            t0 = time.monotonic()
            k = 0
            while time.monotonic() - t0 < 2.6:
                shot(f"fx-{effect}-{k:02d}")
                k += 1
            p.wait(timeout=20)
        time.sleep(2)
        shot("final")
        picker = subprocess.Popen([*WALLRICE, "pick"], env={**env, "WAYLAND_DISPLAY": sock.name, "GDK_BACKEND": "wayland"}) \
            if sock else None
        if picker:
            time.sleep(0.25)
            shot("picker-opening")
            time.sleep(4)
            shot("picker")
            picker.terminate()
        if window:
            window.terminate()
        return 0
    finally:
        shell.terminate()
        try:
            shell.wait(timeout=10)
        except subprocess.TimeoutExpired:
            shell.kill()


WINDOW = r'''
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib
w = Gtk.Window(title="Ptyxis — ~/projects/wallrice")
w.set_default_size(1100, 640)
w.add(Gtk.Label(label="wallrice test window"))
w.show_all()
GLib.timeout_add_seconds(240, Gtk.main_quit)
Gtk.main()
'''

if __name__ == "__main__":
    sys.exit(main())
