from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Optional

from PIL import Image

from mooread.config import OCR_CACHE


class LocalOcrEngine:
    """On-device text detection using Tesseract when present.

    Designed to fail soft: missing binaries never crash the reader.
    Results are cached by file fingerprint so repeated opens stay cheap.
    """

    def __init__(self) -> None:
        self.available = False
        self._reason = "not initialized"
        try:
            import pytesseract

            self._tess = pytesseract
            # Probe once; cheap.
            pytesseract.get_tesseract_version()
            self.available = True
            self._reason = "tesseract ready"
        except Exception as exc:
            self._tess = None
            self._reason = str(exc)

    @property
    def status(self) -> str:
        return self._reason

    def recognize_file(self, path: str | Path, lang: str = "jpn+eng") -> str:
        path = Path(path)
        key = self._cache_key(path, extra=lang)
        cached = OCR_CACHE / f"{key}.txt"
        if cached.exists():
            return cached.read_text(encoding="utf-8")
        if not self.available:
            return ""
        with Image.open(path) as img:
            text = self._recognize_image(img, lang)
        cached.write_text(text, encoding="utf-8")
        return text

    def recognize_image_bytes(self, data: bytes, lang: str = "jpn+eng") -> str:
        if not self.available:
            return ""
        with Image.open(io.BytesIO(data)) as img:
            return self._recognize_image(img, lang)

    def recognize_pdf_page(self, path: str | Path, page_index: int, lang: str = "jpn+eng") -> str:
        path = Path(path)
        key = self._cache_key(path, extra=f"{page_index}:{lang}")
        cached = OCR_CACHE / f"{key}.txt"
        if cached.exists():
            return cached.read_text(encoding="utf-8")
        if not self.available:
            return ""
        try:
            import pypdfium2 as pdfium
        except ImportError:
            return ""
        doc = pdfium.PdfDocument(str(path))
        try:
            page = doc[page_index]
            # 2x scale is enough for body text and much cheaper than 4x.
            bitmap = page.render(scale=2).to_pil()
            text = self._recognize_image(bitmap, lang)
        finally:
            doc.close()
        cached.write_text(text, encoding="utf-8")
        return text

    def _recognize_image(self, img: Image.Image, lang: str) -> str:
        # Lightweight preprocess: grayscale + modest contrast.
        work = img.convert("L")
        if max(work.size) > 2200:
            work.thumbnail((2200, 2200), Image.Resampling.LANCZOS)
        config = "--oem 1 --psm 6"
        try:
            text = self._tess.image_to_string(work, lang=lang, config=config)
        except Exception:
            text = ""
        return (text or "").strip()

    @staticmethod
    def _cache_key(path: Path, extra: str = "") -> str:
        st = path.stat()
        raw = f"{path.resolve()}|{st.st_size}|{int(st.st_mtime)}|{extra}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()
