"""Named visual themes. Built-ins are locked."""

from __future__ import annotations

import json
import re
from pathlib import Path

from mooread.config import THEMES_DIR

THEME_KEYS = (
    "app_color",
    "button_text_color",
    "reader_text_color",
    "text_outline_color",
    "wallpaper_opacity",
    "wallpaper_fit",
    "theme_id",
    "theme_fx",
)

# Amber P3 phosphor CRTs sold for Apple II / early Mac-compatible monitors.
# Game Boy greens are the DMG-01 LCD quartet. Greyscale is Mac Platinum.
BUILTINS = [
    {
        "id": "normal",
        "name": "Normal",
        "locked": True,
        "blurb": "Default dark UI · no shader",
        "theme_id": "",
        "theme_fx": "none",
        "app_color": "#121417",
        "button_text_color": "#f3f7ef",
        "reader_text_color": "#e8edf2",
        "text_outline_color": "#000000",
        "wallpaper_opacity": 0.35,
        "wallpaper_fit": "cover",
    },
    {
        "id": "amber-crt",
        "name": "Amber CRT",
        "locked": True,
        "blurb": "P3 amber phosphor · scanlines, bloom, flicker",
        "theme_id": "amber-crt",
        "theme_fx": "amber-crt",
        "app_color": "#140c04",
        "button_text_color": "#FFC14A",
        "reader_text_color": "#FFB000",
        "text_outline_color": "#4A2200",
        "wallpaper_opacity": 0.22,
        "wallpaper_fit": "cover",
    },
    {
        "id": "mac-platinum",
        "name": "Macintosh Platinum",
        "locked": True,
        "blurb": "System 7 greyscale · platinum chrome bevels, silver desktop",
        "theme_id": "mac-platinum",
        "theme_fx": "mac-platinum",
        "app_color": "#C0C0C0",
        "button_text_color": "#000000",
        "reader_text_color": "#111111",
        "text_outline_color": "#FFFFFF",
        "wallpaper_opacity": 0.18,
        "wallpaper_fit": "contain",
    },
    {
        "id": "gameboy-dmg",
        "name": "Game Boy DMG",
        "locked": True,
        "blurb": "DMG-01 olive LCD · 4-color palette, pixel grid, ghosting",
        "theme_id": "gameboy-dmg",
        "theme_fx": "gameboy-dmg",
        "app_color": "#0F380F",
        "button_text_color": "#9BBC0F",
        "reader_text_color": "#8BAC0F",
        "text_outline_color": "#306230",
        "wallpaper_opacity": 0.28,
        "wallpaper_fit": "cover",
    },
]


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "theme"


def list_themes() -> list[dict]:
    out = [dict(t) for t in BUILTINS]
    seen = {t["id"] for t in out}
    if THEMES_DIR.exists():
        for path in sorted(THEMES_DIR.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            tid = str(data.get("id") or path.stem)
            if tid in seen:
                continue
            data["id"] = tid
            data["locked"] = False
            data["path"] = str(path)
            out.append(data)
            seen.add(tid)
    return out


def snapshot(settings: dict, name: str) -> dict:
    pack = {k: settings.get(k) for k in THEME_KEYS}
    pack["id"] = _slug(name)
    pack["name"] = name.strip() or pack["id"]
    pack["locked"] = False
    pack["blurb"] = "Custom saved look"
    return pack


def save_theme(settings: dict, name: str) -> dict:
    locked_ids = {t["id"] for t in BUILTINS}
    locked_names = {t["name"].lower() for t in BUILTINS}
    if _slug(name) in locked_ids or name.strip().lower() in locked_names:
        raise ValueError("Built-in themes cannot be overwritten")
    pack = snapshot(settings, name)
    THEMES_DIR.mkdir(parents=True, exist_ok=True)
    path = THEMES_DIR / f"{pack['id']}.json"
    path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
    pack["path"] = str(path)
    return pack


def delete_themes(ids: list[str]) -> int:
    locked = {t["id"] for t in BUILTINS}
    removed = 0
    for tid in ids:
        if tid in locked:
            continue
        path = THEMES_DIR / f"{tid}.json"
        if path.exists():
            path.unlink()
            removed += 1
    return removed


def apply_theme(settings: dict, theme: dict) -> dict:
    out = dict(settings)
    for key in THEME_KEYS:
        if key in theme and theme[key] is not None:
            out[key] = theme[key]
    tid = str(theme.get("id") or theme.get("theme_id") or "")
    fx = str(theme.get("theme_fx") or "")
    if tid and "theme_id" not in theme:
        out["theme_id"] = tid
    if not fx and tid in {"amber-crt", "mac-platinum", "gameboy-dmg"}:
        out["theme_fx"] = tid
        out["theme_id"] = tid
    return out
