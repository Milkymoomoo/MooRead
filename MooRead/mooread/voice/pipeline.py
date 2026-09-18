from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from mooread.config import AUDIO_CACHE
from mooread.documents import LoadedDocument, iter_speech_chunks
from mooread.voice.analyzer import ContinuityState, ProsodyHint, advance_continuity, analyze_block
from mooread.voice.engine import SynthesisError, VoiceEngine, wav_duration_seconds
from mooread.voice.profiles import VoiceProfile
import re


def _speakable(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    t = re.sub(r"\[?\s*page\s+\d+\s*\]?", " ", t, flags=re.I).strip()
    letters = sum(ch.isalpha() for ch in t)
    cjk = sum(1 for ch in t if "\u3040" <= ch <= "\u30ff" or "\u3400" <= ch <= "\u9fff")
    return (letters + cjk) >= 2


@dataclass
class PreparedChunk:
    id: str
    index: int
    text: str
    kind: str
    hint: ProsodyHint
    wav_path: Optional[str] = None
    duration: float = 0.0
    error: str = ""
    state: str = "cool"  # cool | warming | warm | hot | done | error
    page: Optional[int] = None


class ReadAheadPipeline:
    """Keeps at most one HOT audio buffer and one WARM audio buffer.

    COOL slots hold only text + prosody hints (a few KB).
    When a chunk finishes, its WAV is deleted immediately so token/audio
    memory cannot accumulate across a long book.
    """

    def __init__(self, engine: VoiceEngine) -> None:
        self.engine = engine
        self.lock = threading.Lock()
        self.cv = threading.Condition(self.lock)
        self.document: Optional[LoadedDocument] = None
        self.profile: Optional[VoiceProfile] = None
        self.chunks: list[PreparedChunk] = []
        self.cursor = 0
        self.continuity = ContinuityState()
        self.playing = False
        self.worker: Optional[threading.Thread] = None
        self.stop_flag = False
        self.session_id = ""
        self.rate = 1.0
        self.pitch = 1.0
        self.volume = 1.0
        self.last_error = ""
        self._session_dir: Optional[Path] = None
        self.looping = False

    def load(
        self,
        document: LoadedDocument,
        profile: VoiceProfile,
        start_index: int = 0,
        rate: float = 1.0,
        pitch: float = 1.0,
        volume: float = 1.0,
    ) -> None:
        self.stop()
        texts: list[tuple[str, str, Optional[int]]] = []
        if document.blocks:
            for b in document.blocks:
                pieces = list(iter_speech_chunks(b.text))
                if pieces:
                    for piece in pieces:
                        texts.append((piece, b.kind, b.page))
                elif b.kind in {"page-scan", "page"}:
                    texts.append((b.text or "", "page-scan", b.page))
        else:
            for piece in iter_speech_chunks(document.text):
                texts.append((piece, "text", None))

        chunks: list[PreparedChunk] = []
        state = ContinuityState()
        for i, (text, kind, page) in enumerate(texts):
            hint = analyze_block(text or " ", kind, state)
            chunks.append(
                PreparedChunk(
                    id=f"c{i:05d}",
                    index=i,
                    text=text,
                    kind=kind,
                    hint=hint,
                    page=page,
                    state="cool",
                )
            )
            state = advance_continuity(state, text or "", hint)

        self.document = document
        self.profile = profile
        self.chunks = chunks
        self.cursor = max(0, min(start_index, max(0, len(chunks) - 1)))
        self.continuity = ContinuityState()
        self.rate = rate
        self.pitch = pitch
        self.volume = volume
        self.last_error = ""
        self.session_id = uuid.uuid4().hex[:10]
        self._session_dir = AUDIO_CACHE / self.session_id
        self._session_dir.mkdir(parents=True, exist_ok=True)
        self.stop_flag = False
        if self.worker is None or not self.worker.is_alive():
            self.worker = threading.Thread(target=self._loop, name="mooread-prefetch", daemon=True)
            self.worker.start()

    def start(self) -> dict:
        if not self.chunks:
            raise RuntimeError("No readable text in this document")
        self.playing = True
        self.stop_flag = False
        if self.worker is None or not self.worker.is_alive():
            self.worker = threading.Thread(target=self._loop, name="mooread-prefetch", daemon=True)
            self.worker.start()
        return self.status()

    def pause(self) -> dict:
        self.playing = False
        return self.status()

    def resume(self) -> dict:
        self.playing = True
        self.stop_flag = False
        if self.worker is None or not self.worker.is_alive():
            self.worker = threading.Thread(target=self._loop, name="mooread-prefetch", daemon=True)
            self.worker.start()
        return self.status()

    def seek(self, index: int) -> dict:
        with self.lock:
            self._discard_audio_except(keep=set())
            self.cursor = max(0, min(index, max(0, len(self.chunks) - 1)))
            for ch in self.chunks:
                if ch.state != "cool":
                    ch.state = "cool"
                    ch.wav_path = None
                    ch.duration = 0.0
        return self.status()

    def stop(self) -> None:
        self.stop_flag = True
        self.playing = False
        worker = self.worker
        if worker and worker.is_alive() and threading.current_thread() is not worker:
            worker.join(timeout=2.0)
        self.worker = None
        with self.lock:
            self._discard_audio_except(keep=set())
        self._purge_session_dir()

    def mark_played(self, chunk_id: str) -> dict:
        """Client finished a HOT chunk. Drop its PCM and advance."""
        with self.lock:
            for ch in self.chunks:
                if ch.id == chunk_id:
                    self._delete_wav(ch)
                    ch.state = "done"
                    self.cursor = ch.index + 1
                    if self.cursor >= len(self.chunks) and self.looping and self.chunks:
                        self.cursor = 0
                        for other in self.chunks:
                            if other.state == "done":
                                other.state = "cool"
                    else:
                        self.cursor = min(self.cursor, len(self.chunks))
                    break
            self._discard_audio_except(keep=self._allowed_ids())
            self.cv.notify_all()
        return self.status()

    def status(self) -> dict:
        with self.lock:
            current = self.chunks[self.cursor] if 0 <= self.cursor < len(self.chunks) else None
            nxt = self.chunks[self.cursor + 1] if self.cursor + 1 < len(self.chunks) else None
            hot = [c.id for c in self.chunks if c.state == "hot"]
            warm = [c.id for c in self.chunks if c.state == "warm"]
            return {
                "session": self.session_id,
                "playing": self.playing,
                "cursor": self.cursor,
                "total": len(self.chunks),
                "current": self._public_chunk(current),
                "next": self._public_chunk(nxt),
                "hot": hot,
                "warm": warm,
                "error": self.last_error,
                "document_title": self.document.title if self.document else "",
            }

    def chunk_wav(self, chunk_id: str) -> Optional[Path]:
        with self.lock:
            for ch in self.chunks:
                if ch.id == chunk_id and ch.wav_path:
                    return Path(ch.wav_path)
        return None

    def _public_chunk(self, ch: Optional[PreparedChunk]) -> Optional[dict]:
        if not ch:
            return None
        return {
            "id": ch.id,
            "index": ch.index,
            "text": ch.text,
            "kind": ch.kind,
            "state": ch.state,
            "duration": ch.duration,
            "emotion": ch.hint.emotion,
            "error": ch.error,
            "audio": f"/api/audio/{ch.id}" if ch.wav_path else None,
        }

    def _loop(self) -> None:
        while not self.stop_flag:
            target = self._next_to_synth()
            if target is None:
                time.sleep(0.05)
                continue
            self._synthesize(target)

    def _next_to_synth(self) -> Optional[PreparedChunk]:
        with self.lock:
            needed = []
            for off in range(0, 6):
                idx = self.cursor + off
                if idx < len(self.chunks):
                    needed.append(self.chunks[idx])
            for ch in needed:
                if ch.state in ("cool", "error"):
                    ch.state = "warming"
                    return ch
            return None

    def _materialize_text(self, ch: PreparedChunk) -> str:
        text = (ch.text or "").strip()
        if ch.kind != "page-scan" and text:
            return text
        doc = self.document
        page = ch.page
        if page is None and doc and doc.blocks:
            for b in doc.blocks:
                if b.index == ch.index or (b.kind == "page-scan" and b.text == ch.text):
                    page = b.page
                    break
        if page is None:
            page = ch.index + 1
        try:
            from mooread.ocr import LocalOcrEngine
            ocr = LocalOcrEngine()
            rendered = ocr.recognize_pdf_page(doc.path, page - 1) if doc and doc.path else ""
            if rendered and _speakable(rendered):
                ch.text = rendered.strip()
                ch.kind = "page"
                return ch.text
        except Exception:
            return text
        return text

    def _synthesize(self, ch: PreparedChunk) -> None:
        if not self.profile or self.stop_flag:
            return
        assert self._session_dir is not None
        dest = self._session_dir / f"{ch.id}.wav"
        try:
            text = self._materialize_text(ch)
            if not _speakable(text):
                with self.lock:
                    ch.state = "done"
                    ch.error = "no speakable text"
                return
            self.engine.synthesize(
                text,
                dest,
                self.profile,
                hint=ch.hint,
                rate_user=self.rate,
                pitch_user=self.pitch,
                volume_user=self.volume,
            )
            duration = wav_duration_seconds(dest)
            with self.lock:
                if self.stop_flag:
                    self._delete_path(dest)
                    return
                ch.wav_path = str(dest)
                ch.duration = duration
                ch.state = "hot" if ch.index == self.cursor else "warm"
                ch.error = ""
                self.last_error = ""
                self._discard_audio_except(keep=self._allowed_ids())
        except SynthesisError as exc:
            with self.lock:
                ch.state = "error"
                ch.error = str(exc)
                self.last_error = str(exc)
        except Exception as exc:
            with self.lock:
                ch.state = "error"
                ch.error = str(exc)
                self.last_error = str(exc)

    def _allowed_ids(self) -> set[str]:
        keep: set[str] = set()
        for idx in range(self.cursor, self.cursor + 6):
            if 0 <= idx < len(self.chunks):
                keep.add(self.chunks[idx].id)
        return keep

    def _discard_audio_except(self, keep: set[str]) -> None:
        for ch in self.chunks:
            if ch.id in keep:
                continue
            if ch.wav_path:
                self._delete_wav(ch)
            if ch.state in ("hot", "warm", "warming") and ch.state != "done":
                if ch.index < self.cursor:
                    ch.state = "done"
                else:
                    ch.state = "cool"

    def _delete_wav(self, ch: PreparedChunk) -> None:
        if ch.wav_path:
            self._delete_path(Path(ch.wav_path))
            ch.wav_path = None
            ch.duration = 0.0

    @staticmethod
    def _delete_path(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    def _purge_session_dir(self) -> None:
        if not self._session_dir:
            return
        try:
            for p in self._session_dir.glob("*"):
                p.unlink(missing_ok=True)
            self._session_dir.rmdir()
        except OSError:
            pass
        self._session_dir = None
