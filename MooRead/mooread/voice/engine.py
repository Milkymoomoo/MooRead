from __future__ import annotations

import threading
import wave
from pathlib import Path
from typing import Optional

import numpy as np

from mooread.config import ROOT
from mooread.voice.analyzer import ProsodyHint
from mooread.voice.profiles import VoiceProfile, apply_lexicon


class SynthesisError(RuntimeError):
    pass


KOKORO_DIR = ROOT / "engine" / "kokoro"
KOKORO_MODEL = KOKORO_DIR / "kokoro-v1.0.int8.onnx"
KOKORO_VOICES = KOKORO_DIR / "voices-v1.0.bin"

# Human-facing names for the bundled Kokoro-82M speakers.
KOKORO_LABELS = {
    "af_heart": "Heart — warm American narrator",
    "af_bella": "Bella — clear American storyteller",
    "af_nicole": "Nicole — even documentary",
    "af_sarah": "Sarah — bright American",
    "af_sky": "Sky — soft / hush",
    "af_alloy": "Alloy — steady American",
    "af_aoede": "Aoede — lyrical American",
    "af_jessica": "Jessica — conversational American",
    "af_kore": "Kore — grounded American",
    "af_nova": "Nova — modern American",
    "af_river": "River — calm American",
    "am_adam": "Adam — American male",
    "am_michael": "Michael — lecture / nonfiction",
    "am_eric": "Eric — American male",
    "am_fenrir": "Fenrir — darker American male",
    "am_liam": "Liam — American male",
    "am_onyx": "Onyx — low American male",
    "am_puck": "Puck — lighter American male",
    "am_echo": "Echo — American male",
    "am_santa": "Santa — character American male",
    "bf_emma": "Emma — British narrator",
    "bf_isabella": "Isabella — British female",
    "bf_alice": "Alice — British female",
    "bf_lily": "Lily — British female",
    "bm_george": "George — British documentary",
    "bm_lewis": "Lewis — British male",
    "bm_daniel": "Daniel — British male",
    "bm_fable": "Fable — British male",
    "jf_alpha": "Alpha — Japanese female narrator",
    "jf_gongitsune": "Gongitsune — Japanese female",
    "jf_nezumi": "Nezumi — Japanese female",
    "jf_tebukuro": "Tebukuro — Japanese female",
    "jm_kumo": "Kumo — Japanese male",
}


class VoiceEngine:
    """Bundled Kokoro-82M neural TTS. Runs entirely on-device via ONNX.

    System SAPI is not used. A profile may still point at a custom Kokoro
    style vector file so you can drop in a new speaking identity.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._kokoro = None
        self._voices: list[str] = []
        self._error = ""
        self._load()

    def _load(self) -> None:
        self._voices = list(KOKORO_LABELS.keys())
        if not KOKORO_MODEL.exists() or not KOKORO_VOICES.exists():
            self._error = f"Kokoro model missing under {KOKORO_DIR}"
            return
        try:
            from kokoro_onnx import Kokoro

            self._kokoro = Kokoro(str(KOKORO_MODEL), str(KOKORO_VOICES))
            found = list(self._kokoro.get_voices())
            if found:
                self._voices = found
        except Exception as exc:
            self._error = f"Kokoro failed to load: {exc}"
            self._kokoro = None

    def info(self) -> dict:
        ready = self._kokoro is not None
        return {
            "backend": "kokoro-82m" if ready else "unavailable",
            "detail": (
                "Bundled Kokoro-82M int8 neural voice, on-device ONNX"
                if ready
                else self._error
            ),
            "neural": ready,
            "model": str(KOKORO_MODEL.name) if ready else "",
            "voice_count": len(self._voices) or len(KOKORO_LABELS),
            "voices": [
                {"id": v, "label": KOKORO_LABELS.get(v, v)}
                for v in (self._voices or list(KOKORO_LABELS.keys()))
            ],
        }

    def synthesize(
        self,
        text: str,
        dest_wav: Path,
        profile: VoiceProfile,
        hint: Optional[ProsodyHint] = None,
        rate_user: float = 1.0,
        pitch_user: float = 1.0,
        volume_user: float = 1.0,
    ) -> Path:
        if self._kokoro is None:
            raise SynthesisError(self._error or "Kokoro neural engine is not loaded")
        hint = hint or ProsodyHint()
        spoken = apply_lexicon(text, profile.lexicon)
        speed = max(0.6, min(1.6, profile.style.rate * hint.rate_scale * rate_user))
        # Kokoro has no separate pitch input; map a little of pitch into speed
        # so a "brighter" request does not get swallowed, without chipmunking.
        if pitch_user != 1.0:
            speed *= 1.0 + (pitch_user - 1.0) * 0.15
        voice = self._resolve_voice(profile, spoken)
        sentence_pause = max(0.05, (hint.pause_after_ms or profile.style.pause_sentence_ms) / 1000.0)
        dest_wav = Path(dest_wav)
        dest_wav.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            try:
                audio, sr = self._kokoro.create(
                    spoken,
                    voice=voice,
                    speed=float(speed),
                    lang=_lang(profile.locale, spoken),
                    trim=True,
                    sentence_pause=sentence_pause,
                )
            except Exception as exc:
                raise SynthesisError(f"Kokoro synthesis failed: {exc}") from exc
        audio = np.asarray(audio, dtype=np.float32)
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        gain = max(0.2, min(1.0, profile.style.volume * hint.volume_scale * volume_user))
        if peak > 0:
            audio = audio * (gain / max(peak, 1.0) * 0.95)
        _write_wav(dest_wav, audio, sr)
        return dest_wav

    def _resolve_voice(self, profile: VoiceProfile, text: str = ""):
        vector = profile.voice_vector
        if vector:
            path = Path(vector)
            if path.exists():
                arr = np.load(str(path)) if path.suffix == ".npy" else None
                if arr is None:
                    blob = np.load(str(path), allow_pickle=True)
                    arr = blob[profile.kokoro_voice] if hasattr(blob, "files") else blob
                return np.asarray(arr, dtype=np.float32)
        mix = profile.style_mix
        if mix and self._kokoro is not None and not _looks_japanese(text):
            acc = None
            total = 0.0
            for name, weight in mix.items():
                try:
                    style = self._kokoro.get_voice_style(name)
                except Exception:
                    continue
                w = float(weight)
                acc = style * w if acc is None else acc + style * w
                total += w
            if acc is not None and total > 0:
                return acc / total
        name = profile.kokoro_voice or "af_heart"
        if _looks_japanese(text) and not name.startswith(("jf_", "jm_")):
            name = "jf_alpha" if "jf_alpha" in self._voices else name
        if not _looks_japanese(text) and name.startswith(("jf_", "jm_")):
            name = profile.kokoro_voice if not str(profile.kokoro_voice).startswith(("jf_", "jm_")) else "af_heart"
        if name not in self._voices and self._voices:
            name = self._voices[0]
        return name


def _looks_japanese(text: str) -> bool:
    return bool(text) and any("\u3040" <= ch <= "\u30ff" or "\u3400" <= ch <= "\u9fff" for ch in text)


def _lang(locale: str, text: str = "") -> str:
    if _looks_japanese(text):
        return "ja"
    loc = (locale or "en-US").lower().replace("_", "-")
    if loc.startswith("ja"):
        return "ja"
    if loc.startswith("en-gb") or loc.startswith("en-uk"):
        return "en-gb"
    return "en-us"


def _write_wav(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    pcm = np.clip(audio, -1.0, 1.0)
    pcm16 = (pcm * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate))
        wf.writeframes(pcm16.tobytes())


def wav_duration_seconds(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate() or 1
            return frames / float(rate)
    except Exception:
        return 0.0
