# MooRead

Local reader + audiobook engine for Windows and Android. The cow in the lab coat is the app icon.

MooRead is a traditional document reader that also speaks whatever it can display. Text comes from the file itself or from on-device OCR. Speech is a **bundled Kokoro-82M neural voice** running in ONNX Runtime on your CPU. Fifty-four speakers ship inside `engine/kokoro/`. Nothing is sent to a hosted voice API. Windows Speech API is not used.

## What it reads

| Type | How text is obtained |
| --- | --- |
| `.epub` | Spine HTML extracted locally |
| `.pdf` | Embedded text; scanned pages go through local OCR |
| `.txt` `.md` `.html` | Direct |
| `.rtf` | RTF stripped to text |
| `.docx` | Paragraphs (Windows app) |
| Images `.png` `.jpg` `.jpeg` `.webp` `.bmp` `.tif` `.gif` | Local OCR, then spoken |

## How the voice pipeline works

Speaking a whole book as one blob would stall the engine and bloat memory. MooRead keeps a short moving window:

1. **COOL** — next-after-next block: text + a tiny prosody hint (emotion, rate, pitch). A few kilobytes.
2. **WARM** — next block: already synthesized to a WAV, ready to play.
3. **HOT** — current block: the WAV being spoken.

When HOT finishes:

- its WAV is deleted
- WARM is promoted to HOT
- the following block is analyzed and synthesized into WARM
- continuity state (last emotion, rate, pitch, whether we were inside dialogue) is kept so diction does not reset at every boundary

Two PCM buffers is the default. A third *cool* slot is only structured text, not audio. That is enough to hide synthesis latency without holding a chapter of samples.

Chunk size targets ~720 characters (roughly 20–25 seconds at 160 wpm), snapped to sentence boundaries so the voice does not hitch mid-clause.

## Voice engine (this is the AI voice)

The reader does **not** use SAPI, eSpeak, or the phone's robotic system voice as its speaking engine.

It ships **Kokoro-82M** (int8 ONNX, ~88 MB) plus a 54-speaker style pack (~27 MB) under `engine/kokoro/`. That is a StyleTTS2-class neural vocoder small enough for CPU and good enough for long-form narration. Inference stays in-process via `onnxruntime`. Grapheme-to-phoneme is on-device (Misaki + espeak-ng loader bundled by the Python package — still local, still offline).

A voice profile JSON picks:

- which bundled speaker (`kokoro_voice`, e.g. `af_heart`, `am_michael`, `bm_george`)
- or a **mix** of two speakers (`style_mix`)
- or a custom style vector file (`voice_vector` → `.npy`)
- rate, pauses, lexicon, emotion bias

The read-ahead pipeline still keeps only HOT + WARM PCM. Kokoro synthesizes the WARM block while HOT plays.

### Neural voices (optional extra)

You can still point a profile at a Piper `.onnx` later. You do not need Piper for MooRead to sound like a person — Kokoro is already inside the tree.

## Windows app

### Run

1. Install [Python 3.10+](https://www.python.org/downloads/) and tick **Add python.exe to PATH**.
2. For image/PDF OCR install [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) and leave it on PATH.
3. Double-click `start_windows.bat`, or:

```bat
cd MooRead
python -m pip install -r requirements.txt
python run.py
```

The app opens at `http://127.0.0.1:8741/`. Use it like a reader: drop a file, change theme and type size, press play. The bottom bar is the audiobook transport.

### Windows voice

The neural model is already in the zip. After `pip install -r requirements.txt` once, speech is fully offline.

### Android

The Android UI and document/OCR pipeline are in `android/`. On-device neural speech on a phone needs the same Kokoro weights plus an ONNX runtime (sherpa-onnx is the usual Android packaging). Copy `engine/kokoro/` into `android/app/src/main/assets/kokoro/` before you build the APK so the model travels with the app instead of downloading later. Until that runtime is linked, the Kotlin project will still fall back to Android's TTS engine — that fallback is a build-gap, not the intended voice. The Windows app is the complete neural product today.

## Android app

The Android project is in `android/`. This environment cannot emit a signed APK (no Android SDK here). On a Windows or Linux machine with Android Studio:

1. Open the `android` folder in Android Studio.
2. Let Gradle sync. Android Studio will generate the Gradle wrapper if needed.
3. Run on a phone/tablet or **Build > Build Bundle(s) / APK(s) > Build APK(s)**.
4. The APK appears under `android/app/build/outputs/apk/`.

Android uses:

- on-device **ML Kit** text recognition for images and PDF page bitmaps
- the system **TextToSpeech** engine with the same hot/warm file cache
- imported JSON voice profiles (`android_voice`, rate, pitch, lexicon)

Min SDK 26, target 35. Tablets and phones share the same activity; the reader pane scrolls, the transport stays docked.

## Project layout

```
MooRead/
  run.py                 Windows / desktop launcher
  start_windows.bat
  requirements.txt
  assets/icon.ico        Windows icon (the cow)
  assets/voices/         Example profiles
  engine/kokoro/         Bundled Kokoro-82M ONNX + 54 speaker pack
  mooread/               Engine: documents, OCR, Kokoro voice, pipeline, HTTP UI
  web/                   Reader UI
  android/               Kotlin app + launcher mipmaps from the same cow art
```

## Performance notes

- Documents are chunked once; only two WAVs exist at a time.
- OCR results are cached by file fingerprint under the user data dir.
- PDF OCR renders at 2×, not 4× — enough for body text, far cheaper.
- The HTTP server is threaded so the UI stays responsive while the prefetch thread synthesizes.
- Completed HOT audio is unlinked from disk immediately.

Data directory:

- Windows: `%APPDATA%\MooRead`
- Linux: `~/.local/share/MooRead`

## Scope that is local-only by design

MooRead will not call a hosted TTS or OCR API. The speaking voice is the Kokoro model sitting in `engine/kokoro/`. If Tesseract is missing, documents still open and you lose only image/scan OCR.
