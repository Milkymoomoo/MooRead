from __future__ import annotations

import sys
import time
import wave
from pathlib import Path
from threading import Event


def play_wav(path: str | Path, stop_event: Event | None = None) -> None:
    """Play a WAV on Windows or Linux without a web server.

    Blocking. stop_event.set() cuts the current file short.
    """
    path = Path(path)
    if not path.exists():
        return
    stop_event = stop_event or Event()
    if _play_sounddevice(path, stop_event):
        return
    if sys.platform == "win32" and _play_winsound(path, stop_event):
        return
    _play_cli(path, stop_event)


def _play_sounddevice(path: Path, stop_event: Event) -> bool:
    try:
        import numpy as np
        import sounddevice as sd
    except Exception:
        return False
    try:
        with wave.open(str(path), "rb") as wf:
            sr = wf.getframerate()
            nch = wf.getnchannels()
            sw = wf.getsampwidth()
            raw = wf.readframes(wf.getnframes())
        if sw == 2:
            audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        else:
            audio = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
            audio = (audio - 128.0) / 128.0
        if nch > 1:
            audio = audio.reshape(-1, nch)
        sd.play(audio, sr, blocking=False)
        while stop_event is None or not stop_event.is_set():
            time.sleep(0.05)
            try:
                if not sd.get_stream().active:
                    break
            except Exception:
                break
        sd.stop()
        return True
    except Exception:
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass
        return False


def _play_winsound(path: Path, stop_event: Event) -> bool:
    try:
        import winsound
    except Exception:
        return False
    try:
        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        dur = _duration(path)
        start = time.time()
        while time.time() - start < dur:
            if stop_event.is_set():
                break
            time.sleep(0.05)
        winsound.PlaySound(None, winsound.SND_PURGE)
        return True
    except Exception:
        return False


def _play_cli(path: Path, stop_event: Event) -> bool:
    import shutil
    import subprocess

    for cmd in (
        ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)],
        ["paplay", str(path)],
        ["aplay", "-q", str(path)],
    ):
        if not shutil.which(cmd[0]):
            continue
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            while proc.poll() is None:
                if stop_event.is_set():
                    proc.terminate()
                    break
                time.sleep(0.05)
            return True
        except Exception:
            continue
    return False


def _duration(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as wf:
            return wf.getnframes() / float(wf.getframerate() or 1)
    except Exception:
        return 0.0
