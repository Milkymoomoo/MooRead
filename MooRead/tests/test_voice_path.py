from __future__ import annotations

import tempfile
import wave
from pathlib import Path

from mooread.documents import _hard_wrap, document_from_text, iter_speech_chunks, load_document
from mooread.voice.pipeline import PreparedChunk, ReadAheadPipeline, _speakable


class FakeEngine:
    def synthesize(self, text, dest_wav, profile, hint=None, rate_user=1.0, pitch_user=1.0, volume_user=1.0):
        dest_wav = Path(dest_wav)
        dest_wav.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(dest_wav), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(8000)
            wf.writeframes(b"\x00\x00" * 800)
        return dest_wav


class FakeProfile:
    lexicon = {}
    style = type("S", (), {"rate": 1.0, "volume": 1.0, "pause_sentence_ms": 80})()
    kokoro_voice = "af_heart"
    voice_vector = ""
    style_mix = None
    locale = "en-US"


def test_speakable():
    assert _speakable("Hello there neighbor")
    assert _speakable("こんにちは")
    assert not _speakable("")
    assert not _speakable("[Page 12]")
    assert not _speakable("Page 3")


def test_hard_wrap_cjk():
    blob = "あ" * 3000
    parts = _hard_wrap(blob, 1400)
    assert len(parts) >= 2
    assert "".join(parts) == blob


def test_chunks_english():
    text = "One. Two. Three. " * 80
    parts = list(iter_speech_chunks(text))
    assert parts
    assert all(len(p) <= 1400 for p in parts)


def test_from_text_pipeline():
    doc = document_from_text("The rain kept a soft count on the roof. " * 20, title="t")
    pipe = ReadAheadPipeline(FakeEngine())
    pipe.load(doc, FakeProfile())
    assert pipe.chunks
    pipe.start()
    # allow a tick of the prefetch worker
    import time
    time.sleep(0.4)
    st = pipe.status()
    assert st["total"] >= 1
    pipe.stop()


def test_empty_pdf_pages_become_placeholders(tmp_path: Path | None = None):
    from mooread.documents import DocumentBlock, LoadedDocument

    doc = LoadedDocument(
        path="x.pdf",
        title="scan",
        kind="pdf",
        text="",
        blocks=[
            DocumentBlock(index=0, text="", kind="page-scan", page=1),
            DocumentBlock(index=1, text="Hello from page two which has words.", kind="page", page=2),
        ],
        page_count=2,
    )
    pipe = ReadAheadPipeline(FakeEngine())
    pipe.load(doc, FakeProfile())
    kinds = [c.kind for c in pipe.chunks]
    assert "page-scan" in kinds
    assert any(c.kind == "page" for c in pipe.chunks)
    pipe.stop()


if __name__ == "__main__":
    test_speakable()
    test_hard_wrap_cjk()
    test_chunks_english()
    test_from_text_pipeline()
    test_empty_pdf_pages_become_placeholders()
    print("desktop structural tests OK")
