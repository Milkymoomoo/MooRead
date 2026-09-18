from __future__ import annotations

import re
from dataclasses import dataclass, replace


DIALOGUE_RE = re.compile(r"[“\"]([^”\"]+)[”\"]")
EXCLAIM_RE = re.compile(r"!")
QUESTION_RE = re.compile(r"\?")
EMPHASIS_WORDS = {
    "suddenly", "whispered", "whisper", "shouted", "screamed", "quietly",
    "softly", "roared", "cried", "murmured", "urgent", "danger", "love",
}


@dataclass
class ProsodyHint:
    emotion: str = "neutral"
    rate_scale: float = 1.0
    pitch_scale: float = 1.0
    volume_scale: float = 1.0
    pause_after_ms: int = 260
    is_dialogue: bool = False
    is_heading: bool = False


@dataclass
class ContinuityState:
    """Tiny state carried across blocks so diction does not reset cold.

    Intentionally small. Never stores PCM, phonemes, or full chapter text.
    """

    last_emotion: str = "neutral"
    last_ended_with: str = "."
    in_dialogue: bool = False
    last_rate_scale: float = 1.0
    last_pitch_scale: float = 1.0
    blocks_spoken: int = 0


def analyze_block(text: str, kind: str, prev: ContinuityState) -> ProsodyHint:
    hint = ProsodyHint()
    stripped = text.strip()
    if kind == "heading" or (len(stripped) < 70 and not stripped.endswith((".", "!", "?"))):
        hint.is_heading = True
        hint.rate_scale = 0.92
        hint.pitch_scale = 1.04
        hint.pause_after_ms = 420
        hint.emotion = "bright"
        return _blend(hint, prev)

    if DIALOGUE_RE.search(stripped) or stripped.startswith(("\"", "“", "'")):
        hint.is_dialogue = True
        hint.pitch_scale = 1.06
        hint.emotion = "warm"

    bangs = stripped.count("!")
    qs = stripped.count("?")
    if bangs >= 1:
        hint.emotion = "bright"
        hint.rate_scale = 1.06
        hint.volume_scale = 1.05
    elif qs >= 1:
        hint.emotion = "warm"
        hint.pitch_scale *= 1.04
        hint.rate_scale = 0.98

    low = stripped.lower()
    if any(w in low for w in ("whisper", "quietly", "softly", "murmur")):
        hint.emotion = "hush"
        hint.rate_scale = 0.92
        hint.volume_scale = 0.88
        hint.pitch_scale = 0.97
    elif any(w in low for w in ("shout", "scream", "roar", "bang")):
        hint.emotion = "bright"
        hint.rate_scale = 1.08
        hint.volume_scale = 1.08

    if stripped.endswith("..."):
        hint.pause_after_ms = 520
        hint.rate_scale *= 0.96
    elif stripped.endswith("?"):
        hint.pause_after_ms = 340
    elif stripped.endswith("!"):
        hint.pause_after_ms = 300

    return _blend(hint, prev)


def _blend(hint: ProsodyHint, prev: ContinuityState) -> ProsodyHint:
    """Ease into a new emotion instead of snapping, unless the text is a heading."""
    if hint.is_heading:
        return hint
    # 70% new, 30% previous keeps adjacent blocks in the same register.
    hint = replace(
        hint,
        rate_scale=hint.rate_scale * 0.7 + prev.last_rate_scale * 0.3,
        pitch_scale=hint.pitch_scale * 0.7 + prev.last_pitch_scale * 0.3,
    )
    if hint.emotion == "neutral":
        hint.emotion = prev.last_emotion
    return hint


def advance_continuity(state: ContinuityState, text: str, hint: ProsodyHint) -> ContinuityState:
    ended = text.strip()[-1:] if text.strip() else "."
    return ContinuityState(
        last_emotion=hint.emotion,
        last_ended_with=ended,
        in_dialogue=hint.is_dialogue,
        last_rate_scale=hint.rate_scale,
        last_pitch_scale=hint.pitch_scale,
        blocks_spoken=state.blocks_spoken + 1,
    )
