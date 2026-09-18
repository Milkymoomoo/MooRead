"""Whole-app visual effects for built-in themes.

Colors alone cannot sell Amber CRT, Macintosh Platinum, or Game Boy DMG.
This module is the CPU/PIL counterpart of the Android AGSL shader:
same look targets, applied to wallpapers, reader canvases, and widget chrome.
"""

from __future__ import annotations

from typing import Iterable, Optional

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

FX_NONE = "none"
FX_AMBER = "amber-crt"
FX_PLATINUM = "mac-platinum"
FX_DMG = "gameboy-dmg"

# DMG-01 LCD quartet (darkest → lightest).
DMG_PALETTE = (
    (15, 56, 15),
    (48, 98, 48),
    (139, 172, 15),
    (155, 188, 15),
)

AMBER = (255, 176, 0)
AMBER_DARK = (20, 12, 4)
PLATINUM = (192, 192, 192)
PLATINUM_HI = (232, 232, 232)
PLATINUM_LO = (128, 128, 128)


def normalize_fx(theme_id: Optional[str], explicit: Optional[str] = None) -> str:
    raw = (explicit or theme_id or "").strip().lower()
    if raw in {FX_AMBER, FX_PLATINUM, FX_DMG}:
        return raw
    return FX_NONE


def _luma_pixel(r: int, g: int, b: int) -> float:
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0


def apply_image_fx(im: Image.Image, fx: str, strength: float = 1.0) -> Image.Image:
    """Filter a wallpaper / preview so the theme is visible behind text."""
    fx = normalize_fx(fx)
    if fx == FX_NONE or strength <= 0:
        return im
    src = im.convert("RGBA")
    if fx == FX_AMBER:
        return _amber_crt(src, strength)
    if fx == FX_PLATINUM:
        return _platinum(src, strength)
    if fx == FX_DMG:
        return _dmg_lcd(src, strength)
    return src


def _amber_crt(src: Image.Image, strength: float) -> Image.Image:
    grey = ImageOps.grayscale(src)
    amber = ImageOps.colorize(grey, black="#140C04", white="#FFB000")
    glow = amber.filter(ImageFilter.GaussianBlur(radius=max(1, int(3 * strength))))
    amber = Image.blend(amber, glow, 0.28 * strength)
    amber = ImageEnhance.Contrast(amber).enhance(1.0 + 0.35 * strength)
    rgba = amber.convert("RGBA")
    if src.mode == "RGBA":
        rgba.putalpha(src.getchannel("A"))
    return _scanlines(rgba, spacing=2, dark=int(70 * strength), phosphor=True)


def _platinum(src: Image.Image, strength: float) -> Image.Image:
    grey = ImageOps.grayscale(src)
    # System 7 platinum is a cool mid-grey with a slight silver lift, not pure B&W.
    toned = ImageOps.colorize(grey, black="#2A2A2E", white="#F0F0F2")
    toned = ImageEnhance.Contrast(toned).enhance(1.0 + 0.15 * strength)
    rgba = toned.convert("RGBA")
    if src.mode == "RGBA":
        rgba.putalpha(src.getchannel("A"))
    # Fine horizontal hairline like a CRT-less greyscale monitor, very light.
    return _scanlines(rgba, spacing=3, dark=int(18 * strength), phosphor=False)


def _dmg_lcd(src: Image.Image, strength: float) -> Image.Image:
    small = src
    # Soft chunky LCD: downscale then nearest-neighbor back.
    w, h = src.size
    nw = max(1, w // max(1, int(2 + strength)))
    nh = max(1, h // max(1, int(2 + strength)))
    small = src.convert("RGB").resize((nw, nh), Image.Resampling.BILINEAR)
    quantized = _quantize_dmg(small)
    lcd = quantized.resize((w, h), Image.Resampling.NEAREST).convert("RGBA")
    if src.mode == "RGBA":
        lcd.putalpha(src.getchannel("A"))
    return _lcd_grid(lcd, pitch=3, dark=int(40 * strength))


def _quantize_dmg(im: Image.Image) -> Image.Image:
    pal = Image.new("P", (1, 1))
    table = []
    for color in DMG_PALETTE:
        table.extend(color)
    table.extend([0, 0, 0] * (256 - 4))
    pal.putpalette(table)
    return im.convert("RGB").quantize(palette=pal, dither=Image.Dither.FLOYDSTEINBERG).convert("RGB")


def _scanlines(im: Image.Image, spacing: int = 2, dark: int = 50, phosphor: bool = False) -> Image.Image:
    overlay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    w, h = im.size
    alpha = max(0, min(180, dark))
    for y in range(0, h, max(1, spacing)):
        draw.line((0, y, w, y), fill=(0, 0, 0, alpha))
    if phosphor:
        for y in range(1, h, max(2, spacing * 2)):
            draw.line((0, y, w, y), fill=(255, 176, 0, 12))
    return Image.alpha_composite(im.convert("RGBA"), overlay)


def _lcd_grid(im: Image.Image, pitch: int = 3, dark: int = 40) -> Image.Image:
    overlay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    w, h = im.size
    a = max(0, min(160, dark))
    for y in range(0, h, max(1, pitch)):
        draw.line((0, y, w, y), fill=(15, 56, 15, a))
    for x in range(0, w, max(1, pitch)):
        draw.line((x, 0, x, h), fill=(15, 56, 15, int(a * 0.55)))
    return Image.alpha_composite(im.convert("RGBA"), overlay)


def draw_vignette(im: Image.Image, amount: float = 0.45, fx: str = FX_AMBER) -> Image.Image:
    if amount <= 0:
        return im
    w, h = im.size
    vignette = Image.new("L", (w, h), 0)
    g = ImageDraw.Draw(vignette)
    pad_x, pad_y = int(w * 0.06), int(h * 0.08)
    g.ellipse((-pad_x, -pad_y, w + pad_x, h + pad_y), fill=int(255 * (1.0 - amount * 0.15)))
    vignette = vignette.filter(ImageFilter.GaussianBlur(radius=max(w, h) // 8 or 8))
    tint = AMBER_DARK if fx == FX_AMBER else ((8, 20, 8) if fx == FX_DMG else (40, 40, 44))
    layer = Image.new("RGBA", (w, h), tint + (0,))
    # Darken edges using inverted vignette as alpha.
    inv = ImageOps.invert(vignette)
    layer.putalpha(inv.point(lambda p: int(p * amount)))
    return Image.alpha_composite(im.convert("RGBA"), layer)


def chrome_for(fx: str) -> dict:
    """Widget metrics + palette used by the Tk restyler and tests."""
    fx = normalize_fx(fx)
    if fx == FX_AMBER:
        return {
            "fx": fx,
            "relief": "sunken",
            "border": 2,
            "font_ui": ("Courier", 11, "bold"),
            "font_title": ("Courier", 20, "bold"),
            "font_reader": ("Courier", 18),
            "button_bg": "#2A1604",
            "button_active": "#4A2200",
            "panel_bg": "#0E0802",
            "player_bg": "#0A0602",
            "accent": "#FFB000",
            "meadow": "#B36A00",
            "scanline_spacing": 2,
            "flicker": True,
            "pixel_grid": False,
            "vignette": 0.42,
        }
    if fx == FX_PLATINUM:
        return {
            "fx": fx,
            "relief": "raised",
            "border": 2,
            "font_ui": ("Geneva", 11),
            "font_title": ("Geneva", 20, "bold"),
            "font_reader": ("Geneva", 16),
            "button_bg": "#DDDDDD",
            "button_active": "#C0C0C0",
            "panel_bg": "#C0C0C0",
            "player_bg": "#A8A8A8",
            "accent": "#000000",
            "meadow": "#888888",
            "scanline_spacing": 0,
            "flicker": False,
            "pixel_grid": False,
            "vignette": 0.08,
        }
    if fx == FX_DMG:
        return {
            "fx": fx,
            "relief": "ridge",
            "border": 3,
            "font_ui": ("Courier", 10, "bold"),
            "font_title": ("Courier", 18, "bold"),
            "font_reader": ("Courier", 16, "bold"),
            "button_bg": "#306230",
            "button_active": "#8BAC0F",
            "panel_bg": "#0F380F",
            "player_bg": "#0B2A0B",
            "accent": "#9BBC0F",
            "meadow": "#306230",
            "scanline_spacing": 3,
            "flicker": False,
            "pixel_grid": True,
            "vignette": 0.28,
        }
    return {
        "fx": FX_NONE,
        "relief": "flat",
        "border": 0,
        "font_ui": ("Segoe UI", 10),
        "font_title": ("Segoe UI", 22, "bold"),
        "font_reader": ("Yu Gothic UI", 18),
        "button_bg": "#2a3138",
        "button_active": "#3d8b4a",
        "panel_bg": "#121417",
        "player_bg": "#0b0d10",
        "accent": "#f3f7ef",
        "meadow": "#3d8b4a",
        "scanline_spacing": 0,
        "flicker": False,
        "pixel_grid": False,
        "vignette": 0.0,
    }


def restyle_widget_tree(root, fx: str, colors: dict) -> int:
    """Walk a Tk tree and apply chrome. Returns widgets touched."""
    chrome = chrome_for(fx)
    bg = colors.get("app_color") or chrome["panel_bg"]
    ink = colors.get("reader_text_color") or chrome["accent"]
    btn = colors.get("button_text_color") or chrome["accent"]
    touched = 0

    def walk(w) -> None:
        nonlocal touched
        cls = w.winfo_class()
        try:
            if cls in {"Frame", "Toplevel", "Labelframe"}:
                w.configure(bg=bg)
            elif cls == "Label":
                w.configure(bg=bg, fg=ink)
            elif cls == "Canvas":
                w.configure(bg=bg, highlightthickness=0)
            elif cls == "Text":
                w.configure(bg=bg, fg=ink, insertbackground=ink)
            elif cls == "Scale":
                w.configure(bg=chrome["player_bg"], fg=btn, highlightthickness=0, troughcolor=chrome["button_bg"])
            elif cls == "Button":
                w.configure(
                    bg=chrome["button_bg"],
                    fg=btn,
                    activebackground=chrome["button_active"],
                    activeforeground=btn,
                    relief=chrome["relief"],
                    bd=chrome["border"],
                    highlightthickness=0,
                )
            elif cls == "Scrollbar":
                w.configure(bg=chrome["button_bg"], troughcolor=chrome["panel_bg"], highlightthickness=0)
            touched += 1
        except Exception:
            pass
        for child in w.winfo_children():
            walk(child)

    walk(root)
    return touched


def quantize_hex_to_dmg(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return DMG_PALETTE[2]
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    y = _luma_pixel(r, g, b)
    if y < 0.22:
        return DMG_PALETTE[0]
    if y < 0.45:
        return DMG_PALETTE[1]
    if y < 0.72:
        return DMG_PALETTE[2]
    return DMG_PALETTE[3]


# AGSL source kept next to the Python filter so both platforms share one recipe.
# Android loads the copy in ThemeFx.kt / assets/shaders/theme_fx.agsl.
AGSL_SHADER = r"""
uniform shader input;
uniform float2 iResolution;
uniform float uTime;
uniform float uMode; // 0 none, 1 amber CRT, 2 platinum, 3 DMG

half4 main(float2 fragCoord) {
    float2 uv = fragCoord / iResolution;
    float2 centered = uv * 2.0 - 1.0;
    float mode = uMode;
    float2 px = fragCoord;
    px.x = clamp(px.x, 0.5, iResolution.x - 0.5);
    px.y = clamp(px.y, 0.5, iResolution.y - 0.5);
    half4 color = input.eval(px);
    float lum = dot(color.rgb, half3(0.299, 0.587, 0.114));

    if (mode > 0.5 && mode < 1.5) {
        half3 amber = half3(1.0, 0.690, 0.0);
        half3 phosphor = half3(lum) * amber;
        phosphor += amber * 0.12 * pow(lum, 1.6);
        float scan = 0.72 + 0.28 * sin(fragCoord.y * 3.14159);
        float flicker = 0.96 + 0.04 * sin(uTime * 37.0);
        float roll = 0.04 * smoothstep(0.0, 0.08, abs(fract(uv.y + uTime * 0.07) - 0.5));
        float vig = 1.0 - 0.45 * dot(centered, centered);
        phosphor *= scan * flicker * vig + roll;
        color = half4(phosphor, color.a);
    } else if (mode > 1.5 && mode < 2.5) {
        float lifted = clamp(lum * 1.05 + 0.04, 0.0, 1.0);
        half3 silver = half3(lifted * 0.92, lifted * 0.92, lifted * 0.95);
        float bevel = 0.04 * (1.0 - uv.y);
        silver += half3(bevel);
        color = half4(silver, color.a);
    } else if (mode > 2.5) {
        float stepped;
        if (lum < 0.22) stepped = 0.08;
        else if (lum < 0.45) stepped = 0.28;
        else if (lum < 0.72) stepped = 0.62;
        else stepped = 0.78;
        half3 dark = half3(0.059, 0.220, 0.059);
        half3 mid = half3(0.188, 0.384, 0.188);
        half3 lite = half3(0.545, 0.675, 0.059);
        half3 lite2 = half3(0.608, 0.737, 0.059);
        half3 lcd = dark;
        if (lum >= 0.22 && lum < 0.45) lcd = mid;
        else if (lum >= 0.45 && lum < 0.72) lcd = lite;
        else if (lum >= 0.72) lcd = lite2;
        float grid = 1.0;
        if (mod(fragCoord.x, 3.0) < 0.7 || mod(fragCoord.y, 3.0) < 0.7) {
            grid = 0.78;
        }
        float ghost = 0.08 * input.eval(px + float2(1.5, 0.0)).r;
        lcd *= grid;
        lcd += half3(ghost * 0.2, ghost * 0.35, ghost * 0.05);
        float vig = 1.0 - 0.28 * dot(centered, centered);
        color = half4(lcd * vig, color.a);
    }
    return color;
}
"""


def shader_modes() -> dict[str, float]:
    return {FX_NONE: 0.0, FX_AMBER: 1.0, FX_PLATINUM: 2.0, FX_DMG: 3.0}
