"""Optional Japanese→English translation. Loads only when the user turns it on."""

from __future__ import annotations

import re
from pathlib import Path

from mooread.config import ROOT

JP_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
MODEL_DIR = ROOT / "engine" / "translate" / "ja-en"


class JaEnTranslator:
    def __init__(self) -> None:
        self.enabled = False
        self._session = None
        self._tok = None
        self.error = ""

    def available(self) -> bool:
        return MODEL_DIR.exists() and any(MODEL_DIR.glob("*.onnx"))

    def _load(self) -> None:
        if self._session is not None or self.error:
            return
        if not self.available():
            self.error = "JA→EN model not installed under engine/translate/ja-en"
            return
        try:
            import onnxruntime as ort

            onnx = next(MODEL_DIR.glob("*.onnx"))
            self._session = ort.InferenceSession(str(onnx), providers=["CPUExecutionProvider"])
        except Exception as exc:
            self.error = str(exc)

    def translate(self, text: str) -> str:
        if not self.enabled or not text.strip():
            return text
        if not JP_RE.search(text):
            return text
        self._load()
        if self._session is None:
            return text
        # Encoder-decoder Marian graphs need a tokenizer; if only a single
        # encoder onnx is present we keep original text rather than garbage.
        try:
            from transformers import AutoTokenizer

            if self._tok is None:
                self._tok = AutoTokenizer.from_pretrained(str(MODEL_DIR), local_files_only=True)
            chunks = [text[i : i + 400] for i in range(0, len(text), 400)]
            out = []
            for chunk in chunks:
                ids = self._tok(chunk, return_tensors="np", truncation=True, max_length=128)
                # Best-effort: many exported graphs expose "input_ids"
                feeds = {}
                for inp in self._session.get_inputs():
                    if inp.name in ids:
                        feeds[inp.name] = ids[inp.name]
                if not feeds:
                    return text
                pred = self._session.run(None, feeds)[0]
                out.append(self._tok.decode(pred[0], skip_special_tokens=True))
            return "\n".join(out) or text
        except Exception:
            return text
