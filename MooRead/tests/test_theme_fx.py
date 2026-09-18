import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PIL import Image

from mooread.theme_fx import (
    AGSL_SHADER,
    DMG_PALETTE,
    FX_AMBER,
    FX_DMG,
    FX_PLATINUM,
    apply_image_fx,
    chrome_for,
    draw_vignette,
    normalize_fx,
    quantize_hex_to_dmg,
    shader_modes,
)
from mooread.themes import BUILTINS, THEME_KEYS, apply_theme


class ThemeFxTests(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_fx("amber-crt"), FX_AMBER)
        self.assertEqual(normalize_fx("custom", "gameboy-dmg"), FX_DMG)
        self.assertEqual(normalize_fx("nope"), "none")

    def test_builtins_carry_fx(self):
        ids = {t["id"]: t for t in BUILTINS}
        self.assertEqual(ids["amber-crt"]["theme_fx"], "amber-crt")
        self.assertEqual(ids["mac-platinum"]["theme_fx"], "mac-platinum")
        self.assertEqual(ids["gameboy-dmg"]["theme_fx"], "gameboy-dmg")
        for key in ("theme_id", "theme_fx"):
            self.assertIn(key, THEME_KEYS)

    def test_apply_theme_sets_fx(self):
        out = apply_theme({"app_color": "#111111"}, BUILTINS[0])
        self.assertEqual(out["theme_fx"], "amber-crt")
        self.assertEqual(out["app_color"], "#140c04")

    def test_chrome_packs(self):
        self.assertTrue(chrome_for(FX_AMBER)["flicker"])
        self.assertEqual(chrome_for(FX_PLATINUM)["relief"], "raised")
        self.assertTrue(chrome_for(FX_DMG)["pixel_grid"])
        self.assertEqual(chrome_for("none")["relief"], "flat")

    def test_amber_tints_toward_phosphor(self):
        src = Image.new("RGB", (32, 32), (200, 200, 200))
        out = apply_image_fx(src, FX_AMBER).convert("RGB")
        r, g, b = out.getpixel((16, 16))
        self.assertGreater(r, b)
        self.assertGreater(g, b)
        self.assertLess(b, 80)

    def test_platinum_is_grey(self):
        src = Image.new("RGB", (24, 24), (40, 180, 90))
        out = apply_image_fx(src, FX_PLATINUM).convert("RGB")
        r, g, b = out.getpixel((8, 8))
        self.assertLess(abs(r - g), 24)
        self.assertLess(abs(g - b), 24)

    def test_dmg_uses_official_palette(self):
        src = Image.new("RGB", (48, 48), (255, 255, 255))
        out = apply_image_fx(src, FX_DMG).convert("RGB")
        # Sample cell centers so the LCD grid lines are skipped.
        samples = {out.getpixel((x, y)) for x in (2, 14, 26, 38) for y in (2, 14, 26, 38)}
        allowed = set(DMG_PALETTE)
        self.assertTrue(samples.issubset(allowed), samples)

    def test_dmg_hex_quantize(self):
        self.assertEqual(quantize_hex_to_dmg("#000000"), DMG_PALETTE[0])
        self.assertEqual(quantize_hex_to_dmg("#FFFFFF"), DMG_PALETTE[3])

    def test_vignette_darkens_corners(self):
        src = Image.new("RGB", (64, 64), (200, 200, 200))
        out = draw_vignette(src.convert("RGBA"), 0.8, FX_AMBER).convert("RGB")
        center = sum(out.getpixel((32, 32)))
        corner = sum(out.getpixel((1, 1)))
        self.assertGreater(center, corner)

    def test_shader_source_covers_three_modes(self):
        self.assertIn("uMode", AGSL_SHADER)
        self.assertIn("amber", AGSL_SHADER)
        self.assertIn("mod(fragCoord.x, 3.0)", AGSL_SHADER)
        self.assertEqual(shader_modes()[FX_DMG], 3.0)

    def test_pipeline_has_looping(self):
        src = (ROOT / "mooread" / "voice" / "pipeline.py").read_text(encoding="utf-8")
        self.assertIn("self.looping = False", src)
        self.assertIn("and self.looping and self.chunks", src)

    def test_ui_module_exports_look_helpers(self):
        import ast
        src = (ROOT / "mooread" / "ui_native.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        names = {n.name for n in tree.body if isinstance(n, ast.ClassDef)}
        self.assertIn("MooReadApp", names)
        methods = {n.name for n in tree.body if isinstance(n, ast.ClassDef) for n in n.body if isinstance(n, ast.FunctionDef)}
        for needed in ("_apply_look", "_play", "_stop", "_reset", "run", "_paint_reader"):
            self.assertIn(needed, methods)


if __name__ == "__main__":
    unittest.main()
