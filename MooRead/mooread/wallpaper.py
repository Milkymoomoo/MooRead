"""Resolve images, GIFs, video, and Wallpaper Engine workshop folders — locally only."""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".avif", ".gif"}
VIDEO_EXTS = {".mp4", ".webm", ".mkv", ".avi", ".mov"}
WE_EXTS = {".pkg", ".mpkg"}


@dataclass
class Wallpaper:
    kind: str  # image | gif | video | we-video | we-preview
    path: Path
    title: str = ""
    muted: bool = True
    fit: str = "cover"  # cover | contain | stretch | center | tile
    opacity: float = 0.35
    note: str = ""


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def unpack_pkg(pkg: Path, dest: Path) -> list[Path]:
    """Best-effort PKGV**** unpacker (Wallpaper Engine scene.pkg)."""
    raw = pkg.read_bytes()
    if raw[:4] != b"PKGV":
        return []
    dest.mkdir(parents=True, exist_ok=True)
    off = 8
    if off + 4 > len(raw):
        return []
    count = struct.unpack_from("<I", raw, off)[0]
    off += 4
    entries: list[tuple[str, int, int]] = []
    try:
        for _ in range(min(count, 20000)):
            n = struct.unpack_from("<I", raw, off)[0]
            off += 4
            name = raw[off : off + n].decode("utf-8", "replace").replace("\\", "/").lstrip("/")
            off += n
            eoff, elen = struct.unpack_from("<II", raw, off)
            off += 8
            entries.append((name, eoff, elen))
    except Exception:
        return []
    data_base = off
    written: list[Path] = []
    for name, eoff, elen in entries:
        if not name or ".." in Path(name).parts:
            continue
        start = data_base + eoff
        if start < 0 or start + elen > len(raw):
            start = eoff
        if start < 0 or start + elen > len(raw):
            continue
        out = dest / name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(raw[start : start + elen])
        written.append(out)
    return written


def _first_media(folder: Path) -> Optional[Path]:
    files = [p for p in folder.rglob("*") if p.is_file()]
    for ext in list(VIDEO_EXTS) + list(IMAGE_EXTS):
        for p in files:
            if p.suffix.lower() == ext:
                return p
    return None


def resolve_wallpaper(path: str | Path, dest_dir: Optional[Path] = None) -> Wallpaper:
    src = Path(path)
    if src.is_file() and src.suffix.lower() in IMAGE_EXTS:
        kind = "gif" if src.suffix.lower() == ".gif" else "image"
        return Wallpaper(kind=kind, path=src, title=src.stem)
    if src.is_file() and src.suffix.lower() in VIDEO_EXTS:
        return Wallpaper(kind="video", path=src, title=src.stem)
    if src.is_file() and src.suffix.lower() in WE_EXTS:
        dest = (dest_dir or src.parent / f"_{src.stem}_unpacked")
        unpack_pkg(src, dest)
        found = _first_media(dest)
        if found:
            kind = "video" if found.suffix.lower() in VIDEO_EXTS else ("gif" if found.suffix.lower() == ".gif" else "image")
            return Wallpaper(kind=kind, path=found, title=src.stem, note="Unpacked Wallpaper Engine package")
        preview = next(dest.rglob("preview.*"), None)
        if preview:
            return Wallpaper(kind="image", path=preview, title=src.stem, note="Scene wallpaper preview (no embedded video)")
        return Wallpaper(kind="image", path=src, title=src.stem, note="Could not unpack scene.pkg")

    folder = src if src.is_dir() else src.parent
    meta = _read_json(folder / "project.json")
    title = str(meta.get("title") or folder.name)
    wtype = str(meta.get("type") or "").lower()
    declared = meta.get("file") or ""
    declared_path = folder / declared if declared else None
    if wtype == "video" and declared_path and declared_path.exists():
        return Wallpaper(kind="video", path=declared_path, title=title, note="Wallpaper Engine video project")
    if declared_path and declared_path.suffix.lower() in VIDEO_EXTS and declared_path.exists():
        return Wallpaper(kind="video", path=declared_path, title=title, note="Wallpaper Engine video project")
    pkg = folder / "scene.pkg"
    if pkg.exists():
        dest = (dest_dir or folder / "_unpacked")
        unpack_pkg(pkg, dest)
        found = _first_media(dest) or _first_media(folder)
        if found:
            kind = "video" if found.suffix.lower() in VIDEO_EXTS else ("gif" if found.suffix.lower() == ".gif" else "image")
            return Wallpaper(kind=kind, path=found, title=title, note="Wallpaper Engine project")
    preview = folder / str(meta.get("preview") or "preview.jpg")
    if preview.exists():
        note = "Scene/web wallpaper preview only (no browser engine)"
        return Wallpaper(kind="image", path=preview, title=title, note=note)
    found = _first_media(folder)
    if found:
        kind = "video" if found.suffix.lower() in VIDEO_EXTS else ("gif" if found.suffix.lower() == ".gif" else "image")
        return Wallpaper(kind=kind, path=found, title=title)
    raise FileNotFoundError(f"No usable wallpaper media in {src}")
