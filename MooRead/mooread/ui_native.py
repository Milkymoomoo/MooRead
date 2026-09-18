"""Native Tk UI — no WebView, no Edge, no browser control."""

from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser, filedialog, font as tkfont, ttk
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageSequence, ImageTk

from mooread import APP_NAME
from mooread.config import FIRST_RUN_MESSAGE, ROOT, load_settings, reset_settings, save_settings
from mooread.documents import load_document
from mooread.voice.engine import KOKORO_LABELS
from mooread.voice.profiles import ProfileStore
from mooread.translate import JaEnTranslator
from mooread.themes import apply_theme, delete_themes, list_themes, save_theme
from mooread.theme_fx import apply_image_fx, chrome_for, draw_vignette, normalize_fx, restyle_widget_tree
from mooread.wallpaper import resolve_wallpaper
from mooread.voice.player import play_wav
from threading import Event
import threading
import time

MASCOT_L = ROOT / "assets" / "mascots" / "mascot_left.png"
MASCOT_R = ROOT / "assets" / "mascots" / "mascot_right.png"
SPLASH_BG = ROOT / "assets" / "mascots" / "splash_fox.png"


def _hex(c: str, fallback: str) -> str:
    c = (c or fallback).strip()
    if not c.startswith("#"):
        c = "#" + c
    return c if len(c) == 7 else fallback


def _stroke_text(base: Image.Image, text: str, xy, fill, stroke, font) -> None:
    d = ImageDraw.Draw(base)
    d.text(xy, text, font=font, fill=fill, stroke_width=3, stroke_fill=stroke, anchor="mm")


class MooReadApp:
    def __init__(self, state) -> None:
        self.state = state
        self.settings = dict(state.settings)
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.geometry("1280x860")
        self.root.minsize(900, 640)
        self.photos: list[ImageTk.PhotoImage] = []
        self.gif_frames: list[ImageTk.PhotoImage] = []
        self.gif_index = 0
        self.wallpaper_im: Optional[Image.Image] = None
        self.doc_text = ""
        self.looping = False
        self.ltr = True
        self.translator = JaEnTranslator()
        self.source_doc = None
        self._theme_snapshot = {}
        self._fx_tick_job = None
        self._fx_phase = 0.0
        self._chrome_widgets: list = []
        self._wp_cache_key = None
        self._wp_photo = None
        self._voice_run = False
        self._stop_audio = Event()
        self._voice_thread = None
        self._build()
        self._apply_look()
        if not self.settings.get("first_run_done"):
            self.root.after(200, self._splash)

    def _thumb(self, path: Path, size: tuple[int, int]) -> Optional[ImageTk.PhotoImage]:
        if not path.exists():
            return None
        im = Image.open(path).convert("RGBA")
        im.thumbnail(size, Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(im)
        self.photos.append(photo)
        return photo

    def _build(self) -> None:
        bg = _hex(self.settings.get("app_color"), "#121417")
        ink = _hex(self.settings.get("reader_text_color"), "#e8edf2")
        btn = _hex(self.settings.get("button_text_color"), "#f3f7ef")
        outline = _hex(self.settings.get("text_outline_color"), "#000000")
        self.root.configure(bg=bg)
        left = self._thumb(MASCOT_L, (56, 56))
        right = self._thumb(MASCOT_R, (56, 56))
        self.brand = tk.Frame(self.root, bg=bg)
        brand = self.brand
        brand.pack(fill="x", pady=(8, 0))
        if left:
            tk.Label(brand, image=left, bg=bg).pack(side="left", padx=(24, 6))
        self.brand_label = tk.Label(brand, text="MOOREAD", fg=ink, bg=bg, font=("Segoe UI", 22, "bold"))
        self.brand_label.pack(side="left")
        if right:
            tk.Label(brand, image=right, bg=bg).pack(side="left", padx=(6, 8))

        self.top = tk.Frame(self.root, bg=bg, height=56)
        top = self.top
        top.pack(fill="x")
        self.ltr_btn = tk.Button(
            top,
            text="LTR / Left-hand",
            command=self._toggle_ltr,
            fg=btn,
            bg="#3d8b4a",
            relief="flat",
        )
        self.ltr_btn.pack(side="left", padx=(20, 10), pady=8)
        self.cam_btn = tk.Button(top, text="Take picture", command=self._take_picture, fg=btn, bg="#2a3138", relief="flat")
        self.cam_btn.pack(side="left", padx=(0, 8), pady=8)
        menu_btn = tk.Button(top, text="Menu ▾", fg=btn, bg="#2a3138", relief="flat", command=self._menu)
        menu_btn.pack(side="right", padx=16)

        self.reader_frame = tk.Frame(self.root, bg=bg)
        self.reader_frame.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(self.reader_frame, bg=bg, highlightthickness=0)
        self.scroll = tk.Scrollbar(self.reader_frame, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self._paint_reader())

        self.player = tk.Frame(self.root, bg="#0b0d10")
        player = self.player
        player.pack(fill="x")
        self.status = tk.StringVar(value="Idle — open a file")
        tk.Label(player, textvariable=self.status, fg="#c5d6c4", bg="#0b0d10").pack(anchor="w", padx=12)
        row = tk.Frame(player, bg="#0b0d10")
        row.pack(fill="x", padx=8, pady=6)
        for label, cmd in (("Prev", self._prev), ("Play", self._play), ("Stop", self._stop), ("Next", self._next)):
            tk.Button(row, text=label, command=cmd, fg=btn, bg="#2f6b3a", relief="flat", width=8).pack(side="left", padx=3)
        self.loop_btn = tk.Button(row, text="Loop", command=self._toggle_loop, fg=btn, bg="#333", relief="flat", width=8)
        self.loop_btn.pack(side="left", padx=3)
        tk.Label(row, text="Vol", fg=btn, bg="#0b0d10").pack(side="right")
        self.vol = tk.Scale(row, from_=0, to=200, orient="horizontal", length=140, bg="#0b0d10", fg=btn,
                            highlightthickness=0, command=self._vol)
        self.vol.set(int(float(self.settings.get("volume", 0.03)) * 100))
        self.vol.pack(side="right")
        self._chrome_widgets = [self.root, self.brand, self.top, self.reader_frame, self.player]

    def _menu(self) -> None:
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label="Open file…", command=self._open_file)
        m.add_command(label="Open folder…", command=self._open_folder)
        m.add_separator()
        m.add_command(label="Take picture / import photo…", command=self._take_picture)
        m.add_command(label="Open manga folder…", command=self._open_manga)
        m.add_separator()
        label = "Translate JA→EN: ON" if self.translator.enabled else "Translate JA→EN: OFF"
        m.add_command(label=label, command=self._toggle_translate)
        m.add_separator()
        bg = tk.Menu(m, tearoff=0)
        bg.add_command(label="Choose image or video…", command=self._browse_wallpaper)
        bg.add_command(label="Import Wallpaper Engine file / folder…", command=self._browse_wallpaper)
        bg.add_command(label="Wallpaper engine (gyro / mute / tilt)…", command=self._wallpaper_engine)
        bg.add_command(label="Translucency…", command=self._opacity_dialog)
        fit = tk.Menu(bg, tearoff=0)
        for mode in ("cover", "contain", "stretch", "center", "tile"):
            fit.add_command(label=mode, command=lambda n=mode: self._set_fit(n))
        bg.add_cascade(label="Fit", menu=fit)
        bg.add_command(label="Mute wallpaper audio", command=lambda: self._set_wp_mute(True))
        bg.add_command(label="Unmute wallpaper audio", command=lambda: self._set_wp_mute(False))
        m.add_cascade(label="Background", menu=bg)
        m.add_separator()
        m.add_command(label="Themes…", command=self._themes_gallery)
        m.add_command(label="Color theming…", command=self._theme_dialog)
        m.add_command(label="Browse font…", command=self._browse_font)
        m.add_separator()
        m.add_command(label="Reset settings", command=self._reset)
        m.add_command(label="Exit MooRead", command=self.root.destroy)
        try:
            m.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())
        finally:
            m.grab_release()

    def _open_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Open",
            filetypes=[
                ("Documents", "*.epub *.pdf *.txt *.rtf *.docx *.md *.html *.png *.jpg *.jpeg *.webp *.bmp *.gif"),
                ("All", "*.*"),
            ],
        )
        if path:
            self._load(path)

    def _toggle_ltr(self) -> None:
        self.ltr = not self.ltr
        self.settings["ltr_mode"] = self.ltr
        save_settings(self.settings)
        if self.ltr:
            self.ltr_btn.configure(text="LTR / Left-hand ON", bg="#3d8b4a")
            self.scroll.pack_forget()
            self.canvas.pack_forget()
            self.scroll.pack(side="left", fill="y", padx=(16, 0))
            self.canvas.pack(side="left", fill="both", expand=True)
        else:
            self.ltr_btn.configure(text="RTL manga", bg="#333")
            self.scroll.pack_forget()
            self.canvas.pack_forget()
            self.canvas.pack(side="left", fill="both", expand=True)
            self.scroll.pack(side="right", fill="y")
        self._reload_voice_order()
        self._paint_reader()

    def _toggle_translate(self) -> None:
        self.translator.enabled = not self.translator.enabled
        self.settings["translate_ja_en"] = self.translator.enabled
        save_settings(self.settings)
        if self.translator.enabled and self.doc_text:
            self.status.set("Translating Japanese…")
            self.doc_text = self.translator.translate(self.doc_text)
            if self.translator.error:
                self.status.set(self.translator.error)
        self._paint_reader()

    def _take_picture(self) -> None:
        path = filedialog.askopenfilename(
            title="Photo for OCR",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff *.gif"), ("All", "*.*")],
        )
        if path:
            self._load(path)

    def _reload_voice_order(self) -> None:
        doc = self.source_doc or self.state.document
        if not doc and self.doc_text.strip():
            try:
                self.state.open_text(self.doc_text, title="Reader", kind="text")
                self.source_doc = self.state.document
                doc = self.source_doc
            except Exception as exc:
                self.status.set(str(exc))
                return
        if not doc:
            return
        blocks = list(doc.blocks)
        if not self.ltr:
            blocks = list(reversed(blocks))
        from mooread.documents import DocumentBlock, LoadedDocument
        ordered = LoadedDocument(
            path=doc.path,
            title=doc.title,
            kind=doc.kind,
            text="\n\n".join(b.text for b in blocks) or doc.text,
            blocks=[
                DocumentBlock(index=i, text=b.text, kind=b.kind, source=b.source, page=b.page)
                for i, b in enumerate(blocks)
            ],
            ocr_used=doc.ocr_used,
        )
        profile = self.state.profiles.load(self.settings.get("voice_profile", "storyteller"))
        self.state.document = ordered
        self.state.pipeline.load(
            ordered,
            profile,
            rate=float(self.settings.get("rate", 1.0)),
            pitch=float(self.settings.get("pitch", 1.0)),
            volume=float(self.settings.get("volume", 1.0)),
        )
        self.state.pipeline.looping = self.looping
        self.doc_text = ordered.text
        mode = "LTR" if self.ltr else "RTL / manga"
        self.status.set(f"{mode} — {len(ordered.blocks)} spoken blocks; loop follows this order")

    def _open_manga(self) -> None:
        folder = filedialog.askdirectory(title="Manga folder")
        if not folder:
            return
        pages = sorted(
            p for p in Path(folder).iterdir()
            if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
        )
        texts = []
        for page in pages:
            try:
                texts.append(self.state.ocr.recognize_file(page, lang="jpn+eng"))
            except Exception:
                continue
        body = "\n\n".join(t for t in texts if t)
        if self.translator.enabled:
            body = self.translator.translate(body)
        self.doc_text = body or f"{len(pages)} manga pages (no OCR text)"
        try:
            self.state.open_text(self.doc_text, title=Path(folder).name, kind="manga")
            self.source_doc = self.state.document
        except Exception as exc:
            self.status.set(str(exc))
            return
        self.status.set(f"Manga — {len(pages)} pages ready to play")
        self._reload_voice_order()
        self._paint_reader()

    def _open_folder(self) -> None:
        folder = filedialog.askdirectory(title="Open folder")
        if not folder:
            return
        for p in sorted(Path(folder).rglob("*")):
            if p.suffix.lower() in {".epub", ".pdf", ".txt", ".rtf", ".docx"}:
                self._load(str(p))
                return

    def _load(self, path: str) -> None:
        self.status.set(f"Opening {Path(path).name}…")
        self.root.update_idletasks()
        try:
            doc = self.state.open_path(path)
            self.source_doc = doc
            self.doc_text = doc.text
            if self.translator.enabled:
                self.doc_text = self.translator.translate(self.doc_text)
            self.status.set(f"Ready — {len(doc.blocks)} blocks")
            self._reload_voice_order()
            self._paint_reader()
        except Exception as exc:
            self.status.set(str(exc))

    def _browse_wallpaper(self) -> None:
        path = filedialog.askopenfilename(
            title="Wallpaper",
            filetypes=[
                ("Media", "*.png *.jpg *.jpeg *.bmp *.gif *.webp *.avif *.mp4 *.webm *.pkg *.mpkg"),
                ("Wallpaper Engine", "*.json *.pkg"),
                ("All", "*.*"),
            ],
        )
        if not path:
            folder = filedialog.askdirectory(title="Wallpaper Engine project folder")
            if not folder:
                return
            path = folder
        try:
            wall = resolve_wallpaper(path)
        except Exception as exc:
            self.status.set(str(exc))
            return
        self.settings["wallpaper_path"] = str(wall.path)
        self.settings["wallpaper_kind"] = wall.kind
        save_settings(self.settings)
        self._load_wallpaper_image(wall.path)
        self.status.set(wall.note or f"Wallpaper: {wall.title}")
        self._paint_reader()

    def _load_wallpaper_image(self, path: Path) -> None:
        self.gif_frames = []
        video_exts = {".mp4", ".webm", ".mkv", ".avi", ".mov"}
        if path.suffix.lower() in video_exts:
            self._load_video_wallpaper(path)
            return
        try:
            im = Image.open(path)
        except Exception:
            self.wallpaper_im = None
            return
        if path.suffix.lower() == ".gif" and getattr(im, "n_frames", 1) > 1:
            frames = []
            for frame in ImageSequence.Iterator(im):
                frames.append(frame.convert("RGBA"))
            self.gif_frames = frames
            self.wallpaper_im = frames[0]
            self.root.after(80, self._tick_gif)
        else:
            self.wallpaper_im = im.convert("RGBA")

    def _load_video_wallpaper(self, path: Path) -> None:
        """Decode a looping still-frame strip. Reader Loop is unrelated."""
        import shutil
        import subprocess
        import tempfile
        self.gif_frames = []
        out = Path(tempfile.gettempdir()) / "mooread-wp-loop"
        if out.exists():
            shutil.rmtree(out, ignore_errors=True)
        out.mkdir(parents=True, exist_ok=True)
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            try:
                subprocess.run(
                    [ffmpeg, "-y", "-stream_loop", "-1", "-t", "12", "-i", str(path),
                     "-vf", "fps=8,scale=640:-2", str(out / "%04d.png")],
                    check=False, capture_output=True, timeout=40,
                )
            except Exception:
                pass
        frames = []
        for png in sorted(out.glob("*.png")):
            try:
                frames.append(Image.open(png).convert("RGBA"))
            except Exception:
                continue
        if frames:
            self.gif_frames = frames
            self.wallpaper_im = frames[0]
            self.status.set("Video wallpaper looping")
            self.root.after(80, self._tick_gif)
            return
        self.wallpaper_im = None
        self.status.set("Video wallpaper needs ffmpeg on PATH to loop frames")

    def _wallpaper_engine(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("Wallpaper engine")
        tk.Label(win, text="Video wallpapers loop by themselves. The player Loop button only repeats the book.").pack(padx=12, pady=8)
        mute = tk.BooleanVar(value=bool(self.settings.get("wallpaper_muted", True)))
        def apply_mute():
            self._set_wp_mute(bool(mute.get()))
        tk.Checkbutton(win, text="Mute wallpaper audio", variable=mute, command=apply_mute).pack(anchor="w", padx=12)
        tk.Label(win, text="Gyro tilt is an Android sensor. Aggressiveness is stored for the APK.").pack(anchor="w", padx=12, pady=(8, 0))
        agg = tk.DoubleVar(value=float(self.settings.get("wallpaper_tilt_agg", 0.45)))
        def apply_agg(_=None):
            self.settings["wallpaper_tilt_agg"] = float(agg.get())
            save_settings(self.settings)
        tk.Scale(win, from_=0.0, to=1.0, resolution=0.01, orient="horizontal", variable=agg, command=apply_agg, length=280, label="Tilt aggressiveness").pack(padx=12, pady=8)
        val = tk.DoubleVar(value=float(self.settings.get("wallpaper_opacity", 0.35)))
        def apply_op(_=None):
            self.settings["wallpaper_opacity"] = val.get()
            save_settings(self.settings)
            self._paint_reader()
        tk.Scale(win, from_=0.05, to=1.0, resolution=0.01, orient="horizontal", variable=val, command=apply_op, length=280, label="Translucency").pack(padx=12, pady=8)

    def _tick_gif(self) -> None:
        if not self.gif_frames:
            return
        self.gif_index = (self.gif_index + 1) % len(self.gif_frames)
        self.wallpaper_im = self.gif_frames[self.gif_index]
        self._paint_reader()
        self.root.after(80, self._tick_gif)

    def _set_fit(self, mode: str) -> None:
        self.settings["wallpaper_fit"] = mode
        save_settings(self.settings)
        self._paint_reader()

    def _set_wp_mute(self, muted: bool) -> None:
        self.settings["wallpaper_muted"] = muted
        save_settings(self.settings)
        self.status.set("Wallpaper muted" if muted else "Wallpaper unmuted")

    def _opacity_dialog(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("Background translucency")
        alpha = float(self.settings.get("wallpaper_opacity", 0.35))
        trans = tk.DoubleVar(value=round((1.0 - alpha) * 100.0, 1))
        label = tk.Label(win, text="")
        def apply(_=None):
            t = max(0.0, min(95.0, float(trans.get())))
            trans.set(t)
            self.settings["wallpaper_opacity"] = 1.0 - (t / 100.0)
            save_settings(self.settings)
            label.configure(text="0% = fully opaque. 95% = almost see-through. Now %s%% translucent." % int(t))
            self._paint_reader()
        tk.Label(win, text="Translucency (0% opaque → 95% translucent)").pack(padx=12, pady=(12, 0))
        tk.Scale(win, from_=0.0, to=95.0, resolution=1, orient="horizontal", variable=trans, command=apply, length=300).pack(padx=16, pady=8)
        label.pack(padx=12, pady=(0, 12))
        apply()

    def _browse_font(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Fonts", "*.ttf *.otf *.woff *.woff2 *.ttc"), ("All", "*.*")])
        if path:
            self.settings["font_file"] = path
            save_settings(self.settings)
            self._paint_reader()

    def _theme_dialog(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("Color theming")
        snap = {k: self.settings.get(k) for k in (
            "app_color", "button_text_color", "reader_text_color", "text_outline_color",
            "theme_id", "theme_fx",
        )}
        keys = [
            ("app_color", "App UI"),
            ("button_text_color", "Button / UI text"),
            ("reader_text_color", "Book text"),
            ("text_outline_color", "Text outline (isolation)"),
        ]
        preview = tk.Canvas(win, width=420, height=90, bg=_hex(self.settings.get("app_color"), "#121417"))
        preview.pack(fill="x", padx=8, pady=8)
        def paint():
            preview.delete("all")
            preview.configure(bg=_hex(self.settings.get("app_color"), "#121417"))
            preview.create_text(210, 46, text="The rain kept a soft count on the roof.",
                                fill=_hex(self.settings.get("text_outline_color"), "#000000"),
                                font=("Georgia", 14))
            preview.create_text(210, 45, text="The rain kept a soft count on the roof.",
                                fill=_hex(self.settings.get("reader_text_color"), "#e8edf2"),
                                font=("Georgia", 14))
        paint()
        for key, label in keys:
            row = tk.Frame(win)
            row.pack(fill="x", padx=8, pady=4)
            tk.Label(row, text=label, width=24, anchor="w").pack(side="left")
            var = tk.StringVar(value=self.settings.get(key, "#ffffff"))
            def pick(k=key, v=var):
                c = colorchooser.askcolor(v.get())[1]
                if c:
                    v.set(c)
                    self.settings[k] = c
                    paint()
                    self._paint_reader()
            tk.Entry(row, textvariable=var, width=10).pack(side="left")
            tk.Button(row, text="Wheel", command=pick).pack(side="left", padx=4)
            def bind_var(k=key, v=var):
                def on_change(*_):
                    self.settings[k] = _hex(v.get(), snap.get(k) or "#ffffff")
                    paint()
                    self._paint_reader()
                v.trace_add("write", on_change)
            bind_var()
        def apply():
            save_settings(self.settings)
            self._apply_look()
            win.destroy()
        def cancel():
            for k, v in snap.items():
                if v is not None:
                    self.settings[k] = v
            self._paint_reader()
            self._apply_look()
            win.destroy()
        btns = tk.Frame(win)
        btns.pack(pady=10)
        tk.Button(btns, text="Apply", command=apply).pack(side="left", padx=8)
        tk.Button(btns, text="Cancel", command=cancel).pack(side="left", padx=8)

    def _themes_gallery(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("Themes")
        win.geometry("720x520")
        win.configure(bg="#0e1014")
        tk.Label(
            win,
            text="Themes",
            fg="#f3f7ef",
            bg="#0e1014",
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w", padx=16, pady=(12, 4))
        tk.Label(
            win,
            text="Built-ins stay locked. Custom looks can be saved, loaded, or deleted.",
            fg="#9aa7b2",
            bg="#0e1014",
        ).pack(anchor="w", padx=16, pady=(0, 8))
        canvas = tk.Canvas(win, bg="#0e1014", highlightthickness=0)
        scroll = tk.Scrollbar(win, command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        grid = tk.Frame(canvas, bg="#0e1014")
        canvas.create_window((0, 0), window=grid, anchor="nw")
        picks: dict[str, tk.BooleanVar] = {}

        def refresh():
            for child in grid.winfo_children():
                child.destroy()
            picks.clear()
            themes = list_themes()
            for i, theme in enumerate(themes):
                card = tk.Frame(grid, bg="#1a1f26", bd=0, highlightthickness=1, highlightbackground="#3a424c")
                r, c = divmod(i, 3)
                card.grid(row=r, column=c, padx=10, pady=10, sticky="n")
                preview = tk.Canvas(card, width=200, height=92, highlightthickness=0)
                preview.pack(padx=8, pady=(8, 4))
                bg = _hex(theme.get("app_color"), "#121417")
                ink = _hex(theme.get("reader_text_color"), "#e8edf2")
                btn = _hex(theme.get("button_text_color"), "#f3f7ef")
                outline = _hex(theme.get("text_outline_color"), "#000000")
                preview.create_rectangle(0, 0, 200, 92, fill=bg, outline=bg)
                preview.create_rectangle(10, 10, 190, 28, fill="#000000", outline="")
                preview.create_text(18, 19, text="MOOREAD", fill=btn, anchor="w", font=("Segoe UI", 9, "bold"))
                preview.create_text(101, 54, text="Aa  雨  本文", fill=outline, font=("Georgia", 13))
                preview.create_text(100, 53, text="Aa  雨  本文", fill=ink, font=("Georgia", 13))
                preview.create_rectangle(12, 72, 70, 84, fill="#2a3138", outline="")
                preview.create_text(41, 78, text="Play", fill=btn, font=("Segoe UI", 8))
                fx = theme.get("theme_fx") or theme.get("id")
                if fx == "amber-crt":
                    for y in range(0, 92, 2):
                        preview.create_line(0, y, 200, y, fill="#000000")
                elif fx == "gameboy-dmg":
                    for y in range(0, 92, 4):
                        preview.create_line(0, y, 200, y, fill="#0F380F")
                    for x in range(0, 200, 4):
                        preview.create_line(x, 0, x, 92, fill="#0F380F")
                elif fx == "mac-platinum":
                    preview.create_rectangle(0, 0, 200, 92, outline="#FFFFFF")
                    preview.create_rectangle(1, 1, 199, 91, outline="#808080")
                tk.Label(card, text=theme.get("name", theme["id"]), fg="#f3f7ef", bg="#1a1f26", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=8)
                tk.Label(card, text=theme.get("blurb", "Custom"), fg="#9aa7b2", bg="#1a1f26", wraplength=190, justify="left").pack(anchor="w", padx=8)
                lock = "Locked built-in" if theme.get("locked") else "Custom"
                tk.Label(card, text=lock, fg="#7d8a94", bg="#1a1f26").pack(anchor="w", padx=8, pady=(0, 4))
                tk.Button(card, text="Load", command=lambda t=theme: apply_card(t), relief="flat", bg="#2f6b3a", fg="#f3f7ef").pack(fill="x", padx=8, pady=(0, 6))
                if not theme.get("locked"):
                    var = tk.BooleanVar(value=False)
                    picks[theme["id"]] = var
                    tk.Checkbutton(card, text="Select", variable=var, bg="#1a1f26", fg="#d7e0e8", selectcolor="#2a3138", activebackground="#1a1f26").pack(anchor="w", padx=8, pady=(0, 8))
            grid.update_idletasks()
            canvas.configure(scrollregion=canvas.bbox("all"))

        def apply_card(theme: dict):
            self.settings = apply_theme(self.settings, theme)
            self.state.settings = self.settings
            save_settings(self.settings)
            self._apply_look()
            self._paint_reader()
            self.status.set(f"Loaded theme: {theme.get('name')}")

        def do_save():
            dlg = tk.Toplevel(win)
            dlg.title("Save theme")
            tk.Label(dlg, text="Name this look").pack(padx=12, pady=8)
            name = tk.Entry(dlg, width=28)
            name.pack(padx=12)
            name.focus_set()
            def ok():
                try:
                    save_theme(self.settings, name.get().strip())
                    dlg.destroy()
                    refresh()
                    self.status.set("Theme saved")
                except Exception as exc:
                    self.status.set(str(exc))
            tk.Button(dlg, text="Save", command=ok).pack(pady=10)

        def do_delete():
            ids = [tid for tid, var in picks.items() if var.get()]
            if not ids:
                self.status.set("Select one or more custom themes first")
                return
            n = delete_themes(ids)
            refresh()
            self.status.set(f"Deleted {n} custom theme(s)")

        bar = tk.Frame(win, bg="#0e1014")
        bar.pack(fill="x", padx=16, pady=8)
        tk.Button(bar, text="Save current look…", command=do_save, relief="flat", bg="#2f6b3a", fg="#f3f7ef").pack(side="left", padx=(0, 8))
        tk.Button(bar, text="Delete selected", command=do_delete, relief="flat", bg="#6b2f2f", fg="#f3f7ef").pack(side="left")
        tk.Button(bar, text="Unload theme — default look", command=lambda: (self._unload_theme(), win.destroy()), relief="flat", bg="#2a3138", fg="#f3f7ef").pack(side="left", padx=(8, 0))
        refresh()

    def _fit_image(self, im: Image.Image, w: int, h: int) -> Image.Image:
        mode = self.settings.get("wallpaper_fit", "cover")
        if mode == "stretch":
            return im.resize((max(1, w), max(1, h)), Image.Resampling.LANCZOS)
        if mode == "contain":
            fitted = ImageOps.contain(im, (w, h))
            canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            canvas.paste(fitted, ((w - fitted.width) // 2, (h - fitted.height) // 2), fitted)
            return canvas
        if mode == "center":
            canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            canvas.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
            return canvas
        if mode == "tile":
            canvas = Image.new("RGBA", (w, h))
            for y in range(0, h, im.height):
                for x in range(0, w, im.width):
                    canvas.paste(im, (x, y))
            return canvas
        return ImageOps.fit(im, (w, h), Image.Resampling.LANCZOS)

    def _paint_reader(self) -> None:
        c = self.canvas
        c.delete("all")
        w = max(c.winfo_width(), 200)
        h = max(c.winfo_height(), 200)
        bg = _hex(self.settings.get("app_color"), "#121417")
        ink = _hex(self.settings.get("reader_text_color"), "#e8edf2")
        outline = _hex(self.settings.get("text_outline_color"), "#000000")
        opacity = float(self.settings.get("wallpaper_opacity", 0.35))
        fx = normalize_fx(self.settings.get("theme_id"), self.settings.get("theme_fx"))
        chrome = chrome_for(fx)
        cache_key = (id(self.wallpaper_im), w, h, fx, opacity, bg, self.settings.get("wallpaper_fit"), self.gif_index)
        if self.wallpaper_im:
            if cache_key != self._wp_cache_key or self._wp_photo is None:
                fitted = self._fit_image(self.wallpaper_im, w, h)
                overlay = Image.new("RGBA", fitted.size, (int(bg[1:3], 16), int(bg[3:5], 16), int(bg[5:7], 16), int((1 - opacity) * 255)))
                blended = Image.alpha_composite(fitted.convert("RGBA"), overlay)
                blended = apply_image_fx(blended, fx, strength=0.85)
                if chrome["vignette"]:
                    blended = draw_vignette(blended, chrome["vignette"], fx)
                self._wp_photo = ImageTk.PhotoImage(blended)
                self._wp_cache_key = cache_key
                self.photos.append(self._wp_photo)
            c.create_image(0, 0, anchor="nw", image=self._wp_photo)
        elif fx != "none":
            if cache_key != self._wp_cache_key or self._wp_photo is None:
                plate = Image.new("RGBA", (w, h), (int(bg[1:3], 16), int(bg[3:5], 16), int(bg[5:7], 16), 255))
                plate = apply_image_fx(plate, fx, strength=0.55)
                if chrome["vignette"]:
                    plate = draw_vignette(plate, chrome["vignette"], fx)
                self._wp_photo = ImageTk.PhotoImage(plate)
                self._wp_cache_key = cache_key
                self.photos.append(self._wp_photo)
            c.create_image(0, 0, anchor="nw", image=self._wp_photo)
        text = self.doc_text or "Open an EPUB, PDF, TXT, RTF, or image."
        pad = 28
        font_spec = chrome["font_reader"]
        size = int(self.settings.get("font_size", 20))
        try:
            if self.settings.get("font_file") and Path(self.settings["font_file"]).exists():
                tkfont.Font(file=self.settings["font_file"], size=size)
        except Exception:
            pass
        reader_font = (font_spec[0], size) + font_spec[2:]
        y = pad
        anchor = "nw" if self.ltr else "ne"
        x = pad if self.ltr else w - pad
        flicker = 1.0
        if chrome["flicker"]:
            import math
            flicker = 0.92 + 0.08 * math.sin(self._fx_phase * 6.2)
        for para in text.split("\n"):
            c.create_text(x + 1, y + 1, text=para, width=w - pad * 2, fill=outline, font=reader_font, anchor=anchor, justify="left" if self.ltr else "right")
            c.create_text(x, y, text=para, width=w - pad * 2, fill=ink, font=reader_font, anchor=anchor, justify="left" if self.ltr else "right")
            y += size + 18
            if y > 20000:
                break
        spacing = int(chrome["scanline_spacing"] or 0)
        if spacing:
            roll = int(self._fx_phase * 18) % spacing if chrome["flicker"] else 0
            for sy in range(-roll, h + 4, spacing):
                c.create_line(0, sy, w, sy, fill="#000000")
            if chrome["pixel_grid"]:
                for sx in range(0, w, spacing):
                    c.create_line(sx, 0, sx, max(h, y), fill="#0F380F")
        if chrome["flicker"] and flicker < 0.97:
            c.create_rectangle(0, 0, w, max(h, y), fill="#140C04", stipple="gray25", outline="")
        c.configure(scrollregion=(0, 0, w, y + pad))
        if len(self.photos) > 20:
            self.photos = self.photos[-8:]

    def _current_fx(self) -> str:
        return normalize_fx(self.settings.get("theme_id"), self.settings.get("theme_fx"))

    def _apply_look(self) -> None:
        fx = self._current_fx()
        chrome = chrome_for(fx)
        colors = {
            "app_color": _hex(self.settings.get("app_color"), chrome["panel_bg"]),
            "reader_text_color": _hex(self.settings.get("reader_text_color"), "#e8edf2"),
            "button_text_color": _hex(self.settings.get("button_text_color"), "#f3f7ef"),
        }
        restyle_widget_tree(self.root, fx, colors)
        try:
            self.brand_label.configure(font=chrome["font_title"])
        except Exception:
            pass
        try:
            self.player.configure(bg=chrome["player_bg"])
        except Exception:
            pass
        self._start_fx_tick()

    def _start_fx_tick(self) -> None:
        if self._fx_tick_job:
            try:
                self.root.after_cancel(self._fx_tick_job)
            except Exception:
                pass
            self._fx_tick_job = None
        if chrome_for(self._current_fx())["flicker"]:
            self._tick_fx()

    def _tick_fx(self) -> None:
        self._fx_phase += 0.05
        # Only refresh scanline roll / flicker — cheap enough for CRT authenticity.
        if chrome_for(self._current_fx())["flicker"]:
            self._paint_reader()
            self._fx_tick_job = self.root.after(90, self._tick_fx)

    def _splash(self) -> None:
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.geometry("720x480+200+120")
        canvas = tk.Canvas(win, width=720, height=480, highlightthickness=0)
        canvas.pack()
        if SPLASH_BG.exists():
            im = Image.open(SPLASH_BG).convert("RGBA").resize((720, 480), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(im)
            self.photos.append(photo)
            canvas.create_image(0, 0, anchor="nw", image=photo)
        canvas.create_text(361, 201, text="MooRead", fill="white", font=("Segoe UI", 32, "bold"))
        canvas.create_text(360, 200, text="MooRead", fill="black", font=("Segoe UI", 32, "bold"))
        from mooread.config import FIRST_RUN_MESSAGE
        canvas.create_text(361, 321, text=FIRST_RUN_MESSAGE, fill="white", width=640, font=("Segoe UI", 12))
        canvas.create_text(360, 320, text=FIRST_RUN_MESSAGE, fill="black", width=640, font=("Segoe UI", 12))
        self.settings["first_run_done"] = True
        save_settings(self.settings)
        win.after(2400, win.destroy)

    def _ensure_doc(self) -> bool:
        if self.state.document:
            return True
        if self.doc_text.strip():
            try:
                self.state.open_text(self.doc_text, title="Reader", kind="text")
                self.source_doc = self.state.document
                return True
            except Exception as exc:
                self.status.set(str(exc))
                return False
        self.status.set("Open a file or take a picture first")
        return False

    def _play(self) -> None:
        if self._voice_run:
            self._halt_voice()
            self.state.pipeline.pause()
            self.status.set("Paused")
            return
        if not self._ensure_doc():
            return
        pipe = self.state.pipeline
        pipe.volume = float(self.settings.get("volume", 0.03))
        pipe.looping = self.looping
        try:
            if not pipe.chunks:
                self._reload_voice_order()
            pipe.start()
        except Exception as exc:
            self.status.set(str(exc))
            return
        self._stop_audio.clear()
        self._voice_run = True
        self._voice_thread = threading.Thread(target=self._voice_loop, name="mooread-speaker", daemon=True)
        self._voice_thread.start()
        self.status.set("Playing — preparing first block")

    def _halt_voice(self) -> None:
        self._voice_run = False
        self._stop_audio.set()

    def _voice_loop(self) -> None:
        pipe = self.state.pipeline
        while self._voice_run:
            st = pipe.status()
            cur = st.get("current")
            if not cur:
                if pipe.looping and pipe.chunks:
                    pipe.seek(0)
                    continue
                self._voice_run = False
                self.root.after(0, lambda: self.status.set("Finished"))
                break
            if cur.get("state") == "done" or cur.get("error") == "no speakable text":
                pipe.mark_played(cur["id"])
                continue
            waited = 0
            while self._voice_run:
                wav = pipe.chunk_wav(cur["id"])
                st = pipe.status()
                cur = st.get("current") or cur
                if wav or cur.get("state") == "error":
                    break
                if waited % 20 == 0:
                    ready = len(st.get("warm") or []) + len(st.get("hot") or [])
                    self.root.after(
                        0,
                        lambda i=cur["index"], t=st.get("total", 0), r=ready: self.status.set(
                            f"Preparing block {i + 1}/{t} — {r} prepped"
                        ),
                    )
                time.sleep(0.05)
                waited += 1
                if waited > 1200:
                    break
            if not self._voice_run:
                break
            wav = pipe.chunk_wav(cur["id"])
            if wav is None:
                pipe.mark_played(cur["id"])
                continue
            total = st.get("total", 0)
            ready = len(st.get("warm") or []) + 1
            self.root.after(
                0,
                lambda i=cur["index"], t=total, r=ready: self.status.set(
                    f"Speaking {i + 1}/{t} — {r} prepped"
                ),
            )
            play_wav(wav, self._stop_audio)
            if self._voice_run:
                pipe.mark_played(cur["id"])

    def _stop(self) -> None:
        self._halt_voice()
        self.state.pipeline.stop()
        self.status.set("Stopped")

    def _next(self) -> None:
        pipe = self.state.pipeline
        if pipe.chunks:
            self._stop_audio.set()
            pipe.seek(pipe.cursor + 1)
            self._stop_audio.clear()
            self.status.set(f"Block {pipe.cursor + 1}/{len(pipe.chunks)}")

    def _prev(self) -> None:
        pipe = self.state.pipeline
        if pipe.chunks:
            self._stop_audio.set()
            pipe.seek(max(0, pipe.cursor - 1))
            self._stop_audio.clear()
            self.status.set(f"Block {pipe.cursor + 1}/{len(pipe.chunks)}")

    def _toggle_loop(self) -> None:
        self.looping = not self.looping
        self.state.pipeline.looping = self.looping
        self.loop_btn.configure(text="Loop ON" if self.looping else "Loop", bg="#2f6b3a" if self.looping else "#333")
        self.status.set("Loop on — will replay the whole file" if self.looping else "Loop off")

    def _vol(self, value) -> None:
        vol = max(0.0, min(2.0, float(value) / 100.0))
        self.settings["volume"] = vol
        self.state.pipeline.volume = vol
        save_settings(self.settings)

    def _unload_theme(self) -> None:
        from mooread.config import DEFAULTS, save_settings
        self.settings["theme_id"] = ""
        self.settings["theme_fx"] = "none"
        self.settings["app_color"] = DEFAULTS["app_color"]
        self.settings["button_text_color"] = DEFAULTS["button_text_color"]
        self.settings["reader_text_color"] = DEFAULTS["reader_text_color"]
        self.settings["text_outline_color"] = DEFAULTS["text_outline_color"]
        save_settings(self.settings)
        self._wp_cache_key = None
        self._wp_photo = None
        self._apply_look()
        self._paint_reader()
        self.status.set("Back to normal (no shader)")

    def _reset(self) -> None:
        from mooread.config import reset_settings
        self.settings = reset_settings()
        self.state.settings = self.settings
        self.ltr = True
        self.looping = False
        self.translator.enabled = False
        self.vol.set(int(float(self.settings.get("volume", 0.03)) * 100))
        self._wp_cache_key = None
        self._wp_photo = None
        self._apply_look()
        self._paint_reader()
        self.status.set("Reset to dark mode defaults (no shader)")

    def run(self) -> None:
        self.root.mainloop()
