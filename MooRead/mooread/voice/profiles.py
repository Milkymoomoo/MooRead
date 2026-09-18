from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from mooread.config import BUNDLED_VOICES, PROFILES_DIR


PROFILE_FORMAT = "mooread-voice-profile/v1"


@dataclass
class VoiceStyle:
    rate: float = 1.0
    pitch: float = 1.0
    volume: float = 1.0
    emotion_bias: str = "neutral"  # neutral | warm | bright | grave | hush
    diction: str = "narrative"  # narrative | documentary | dialogue | lecture
    pause_sentence_ms: int = 260
    pause_paragraph_ms: int = 480
    dialogue_pitch_shift: float = 0.07
    heading_rate_scale: float = 0.92
    emphasis_rate_scale: float = 0.96


@dataclass
class VoiceProfile:
    format: str = PROFILE_FORMAT
    id: str = "storyteller"
    name: str = "Storyteller"
    engine: str = "kokoro"  # kokoro | piper (optional extra model)
    kokoro_voice: str = "af_heart"
    voice_vector: str = ""
    style_mix: dict[str, float] = field(default_factory=dict)
    sapi_voice: str = ""
    android_voice: str = ""
    piper_onnx: str = ""
    piper_config: str = ""
    locale: str = "en-US"
    notes: str = ""
    style: VoiceStyle = field(default_factory=VoiceStyle)
    lexicon: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any], fallback_id: str = "custom") -> "VoiceProfile":
        style_raw = data.get("style") or {}
        style = VoiceStyle(
            **{k: v for k, v in style_raw.items() if k in VoiceStyle.__dataclass_fields__}
        )
        lexicon = data.get("lexicon") or {}
        piper = data.get("piper") or {}
        return cls(
            format=data.get("format", PROFILE_FORMAT),
            id=data.get("id") or fallback_id,
            name=data.get("name") or fallback_id,
            engine=data.get("engine", "kokoro"),
            kokoro_voice=data.get("kokoro_voice") or data.get("voice") or "af_heart",
            voice_vector=data.get("voice_vector", ""),
            style_mix=dict(data.get("style_mix") or {}),
            sapi_voice=data.get("sapi_voice", ""),
            android_voice=data.get("android_voice", ""),
            piper_onnx=data.get("piper_onnx") or piper.get("onnx", ""),
            piper_config=data.get("piper_config") or piper.get("config", ""),
            locale=data.get("locale", "en-US"),
            notes=data.get("notes", ""),
            style=style,
            lexicon=dict(lexicon),
        )


def _safe_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "voice"


class ProfileStore:
    def __init__(self) -> None:
        self.ensure_bundled()

    def ensure_bundled(self) -> None:
        if BUNDLED_VOICES.exists():
            for src in BUNDLED_VOICES.glob("*.json"):
                dest = PROFILES_DIR / src.name
                if not dest.exists():
                    shutil.copy2(src, dest)

    def list_profiles(self) -> list[VoiceProfile]:
        profiles = []
        for path in sorted(PROFILES_DIR.glob("*.json")):
            try:
                profiles.append(self.load_file(path))
            except Exception:
                continue
        if not profiles:
            profiles.append(VoiceProfile())
        return profiles

    def load(self, profile_id: str) -> VoiceProfile:
        path = PROFILES_DIR / f"{profile_id}.json"
        if path.exists():
            return self.load_file(path)
        for p in self.list_profiles():
            if p.id == profile_id or p.name.lower() == profile_id.lower():
                return p
        return VoiceProfile()

    def load_file(self, path: Path) -> VoiceProfile:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return VoiceProfile.from_dict(data, fallback_id=path.stem)

    def import_file(self, path: str | Path) -> VoiceProfile:
        src = Path(path)
        profile = self.load_file(src)
        if not profile.id:
            profile.id = _safe_id(profile.name or src.stem)
        dest = PROFILES_DIR / f"{profile.id}.json"
        dest.write_text(json.dumps(profile.to_dict(), indent=2), encoding="utf-8")
        # Copy sibling piper models if the profile points at relative files.
        self._copy_sidecar_models(src, profile)
        return profile

    def save(self, profile: VoiceProfile) -> Path:
        dest = PROFILES_DIR / f"{profile.id}.json"
        dest.write_text(json.dumps(profile.to_dict(), indent=2), encoding="utf-8")
        return dest

    def _copy_sidecar_models(self, src: Path, profile: VoiceProfile) -> None:
        folder = PROFILES_DIR / profile.id
        for rel in (profile.piper_onnx, profile.piper_config):
            if not rel:
                continue
            candidate = (src.parent / rel).resolve() if not Path(rel).is_absolute() else Path(rel)
            if candidate.exists() and candidate.is_file():
                folder.mkdir(parents=True, exist_ok=True)
                target = folder / candidate.name
                if not target.exists():
                    shutil.copy2(candidate, target)


def apply_lexicon(text: str, lexicon: dict[str, str]) -> str:
    if not lexicon:
        return text
    out = text
    for src, dest in lexicon.items():
        out = re.sub(rf"\b{re.escape(src)}\b", dest, out)
    return out
