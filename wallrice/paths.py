"""Where wallrice keeps things, per the XDG base directory spec. Everything is per user; nothing
needs root. Each call reads the environment, so tests (and sudo-less timers) can point it elsewhere.

  config  $XDG_CONFIG_HOME/wallrice   state.json, review.json, collections.conf (optional override)
  cache   $XDG_CACHE_HOME/wallrice    thumbnails, palettes, generated shell stylesheet
  data    $XDG_DATA_HOME/wallrice     the installed program, backups
  walls   $(xdg-user-dir PICTURES)/walls   (or $WALLRICE_WALLS)
"""
import functools
import os
import subprocess
from pathlib import Path

APP = "wallrice"
SRC = Path(__file__).resolve().parent.parent  # the repo, or ~/.local/share/wallrice when installed


def home():
    return Path(os.environ.get("HOME") or Path.home())


def _xdg(var, default):
    v = os.environ.get(var)
    return Path(v) if v and os.path.isabs(v) else home() / default


def config_home():
    return _xdg("XDG_CONFIG_HOME", ".config")


def cache_home():
    return _xdg("XDG_CACHE_HOME", ".cache")


def data_home():
    return _xdg("XDG_DATA_HOME", ".local/share")


def config():
    return config_home() / APP


def cache():
    return cache_home() / APP


def data():
    return data_home() / APP


def runtime():
    v = os.environ.get("XDG_RUNTIME_DIR")
    return Path(v) / APP if v else cache() / "run"


def state_file():
    return config() / "state.json"


def review_file():
    return config() / "review.json"


def backups():
    return data() / "backup"


@functools.lru_cache(maxsize=None)
def _pictures(home_dir):
    try:
        out = subprocess.run(["xdg-user-dir", "PICTURES"], capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        out = ""
    return Path(out) if out and out != home_dir else Path(home_dir) / "Pictures"


def walls():
    override = os.environ.get("WALLRICE_WALLS")
    if override:
        return Path(override)
    return _pictures(str(home())) / "walls"


def resource(*parts):
    """A file shipped with wallrice (data/, gnome-extension/, …)."""
    return SRC.joinpath(*parts)
