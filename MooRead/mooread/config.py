from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _default_data_dir() -> Path:
    if sys.platform == "win32":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    path = root / "MooRead"
    path.mkdir(parents=True, exist_ok=True)
    return path


if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    ROOT = Path(sys._MEIPASS)
else:
    ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = _default_data_dir()
CACHE_DIR = DATA_DIR / "cache"
AUDIO_CACHE = CACHE_DIR / "audio"
OCR_CACHE = CACHE_DIR / "ocr"
LIBRARY_DIR = DATA_DIR / "library"
PROFILES_DIR = DATA_DIR / "voices"
FONTS_DIR = DATA_DIR / "fonts"
SETTINGS_PATH = DATA_DIR / "settings.json"
BUNDLED_VOICES = ROOT / "assets" / "voices"

THEMES_DIR = DATA_DIR / "themes"

for _p in (CACHE_DIR, AUDIO_CACHE, OCR_CACHE, LIBRARY_DIR, PROFILES_DIR, FONTS_DIR, THEMES_DIR):
    _p.mkdir(parents=True, exist_ok=True)

PIPELINE_HOT_SLOTS = 1
PIPELINE_WARM_SLOTS = 1
PIPELINE_COOL_SLOTS = 1

TARGET_CHUNK_CHARS = 720
MIN_CHUNK_CHARS = 220
MAX_CHUNK_CHARS = 1400

HOST = "127.0.0.1"
PORT = 8741

FIRST_RUN_MESSAGE = (
    "For your sanity this application defaults to darkmode and 3% volume on first run, "
    "however on subsequent runs it will retain your settings unless you press reset."
)

DEFAULTS = {
    "theme": "ink",
    "font_family": "Georgia, 'Times New Roman', serif",
    "font_size": 20,
    "line_height": 1.55,
    "reader_width": 720,
    "rate": 1.0,
    "pitch": 1.0,
    "volume": 0.03,
    "voice_profile": "storyteller",
    "auto_ocr_images": True,
    "auto_ocr_scanned_pdf": True,
    "highlight_spoken": True,
    "sleep_timer_min": 0,
    "first_run_done": False,
    "app_color": "#121417",
    "button_text_color": "#f3f7ef",
    "reader_text_color": "#e8edf2",
    "text_outline_color": "#000000",
    "wallpaper_path": "",
    "wallpaper_kind": "",
    "wallpaper_fit": "cover",
    "wallpaper_opacity": 0.35,
    "wallpaper_muted": True,
    "wallpaper_tilt": False,
    "wallpaper_tilt_agg": 0.45,
    "font_file": "",
    "kokoro_voice": "af_heart",
    "theme_id": "",
    "theme_fx": "",
}


def load_settings() -> dict:
    settings = dict(DEFAULTS)
    if SETTINGS_PATH.exists():
        try:
            stored = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            settings.update(stored)
        except (OSError, json.JSONDecodeError):
            pass
    return settings


def save_settings(settings: dict) -> None:
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def reset_settings() -> dict:
    settings = dict(DEFAULTS)
    settings["first_run_done"] = True
    save_settings(settings)
    return settings
