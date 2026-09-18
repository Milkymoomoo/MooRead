# MooRead — handoff for the NEXT session

Read this file first. Then open the source tree. Do not invent a new layout.

**Yes: you can pass this `HANDOFF.md` plus the split packs below and nothing else.** Join the source zip first. Optionally also pass the already-built APK / Windows / Linux splits so the next agent does not have to rebuild to inspect.

Date of this handoff: 2026-09-17 ~23:20 UTC.

---

## What you pass the next session

Required:

1. This file: `HANDOFF.md`
2. `join_source.bat` + `MooRead-source.zip.part00` … `part09`  
   Join on Windows: run `join_source.bat`.  
   Join on Linux/mac: `cat MooRead-source.zip.part* > MooRead-source.zip` (parts must be in numeric order).

Optional but useful:

- Android APK: `join_apk.bat` + `MooRead.apk.part00` … `part07`
- Windows app: `join_windows.bat` + `MooRead-Windows.zip.part00` … `part03`
- Linux app: `join_linux.bat` + `MooRead-Linux.zip.part00` … `part03`

Ignore if the user still has them (stale):

- Original `MooRead-handoff-source.zip.part00/01` from the morning of 2026-09-17
- Old `handoff.md` / `START_HERE.md` that say Android `voices.bin` is the **5.5MB English** sherpa bank
- Anything that points at `MooRead/android/` as the live Android tree
- `/workspace/artifacts/MooRead-continue.zip`

---

## What MooRead is

Offline EPUB / PDF / TXT / RTF / DOCX / HTML / image reader + **local** Kokoro neural TTS.

No WebView2, no Edge, no `INTERNET` permission, no phone-home.

Targets:

- **Windows / Linux:** Python + Tk (`MooRead/mooread/ui_native.py`), launched by `run.py` / `MooRead.bat` / `run-linux.sh`
- **Android:** Kotlin in **`MooReadAndroid/`** — this is the live app. **`MooRead/android/` is dead. Do not edit it.**

---

## Hard rules (the last session burned these)

1. Live Android is `MooReadAndroid/`. Never `MooRead/android/`.
2. **Never** copy Windows `engine/kokoro/voices-v1.0.bin` onto the APK. That file is the kokoro-onnx voice bank. Putting it in Android `assets/kokoro/voices.bin` **SIGSEGVs** on launch.
3. Android `voices.bin` is the **sherpa-onnx multi-lang raw-float bank**:
   - size **exactly 28,200,960 bytes**
   - first two bytes are **not** `PK` (0x50 0x4B)
   - pairs with `assets/kokoro/model.int8.onnx` size **exactly 114,203,756 bytes**
   - `tokens.txt` size **687 bytes**
   - also required: `lexicon-us-en.txt`, `lexicon-zh.txt`, `espeak-ng-data/`
4. The old 5.5MB English-only sherpa bank is **wrong** for the current multi-lang model. Japanese (`jf_alpha`, sid 37) needs the 28MB multi-lang bank.
5. Android AAR in use: `app/libs/sherpa-onnx-1.13.8.aar` (1.12.14 is also in `libs/` — do not switch the Gradle dep back without a reason).
6. Theme shaders must **not** barrel / pincushion / bend the screen. Buttons have to stay hittable.
7. Do not start `ThreadingHTTPServer` for the desktop UI.
8. Do not add INTERNET permission.
9. Do not change the user’s scope. They will tell you when something is out of scope.

`TtsPipeline.assetFileStale()` already rejects a too-small bank, a PK/NPZ header, or a wrong-sized model when copying assets → `filesDir/kokoro`. Leave that guard in.

---

## Tree after you join `MooRead-source.zip`

```
HANDOFF.md                  (replace with THIS file if the zip still has an older one)
START_HERE.md
MODELS.md
MooRead/                    Python desktop app (Windows + Linux)
  run.py
  run-linux.sh              Xorg + Wayland (Tk via X11 / XWayland)
  MooRead.bat
  README-LINUX.txt
  README-WINDOWS.txt
  mooread/
    app.py                  AppState → ui_native
    ui_native.py            Tk UI
    config.py
    themes.py
    theme_fx.py             CRT / Platinum / DMG look, no barrel
    wallpaper.py            image/gif/video + Wallpaper Engine project.json / scene.pkg
    translate.py            JA→EN toggle (needs engine/translate ONNX if present)
    documents/              loaders; PDF OCR is deferred / page-at-a-time where possible
    ocr/
    voice/
      pipeline.py           lookahead: cursor + next 5 chunks
      engine.py             kokoro-onnx
      profiles.py
  assets/mascots/
  assets/voices/            includes japanese.json
  engine/kokoro/
    kokoro-v1.0.int8.onnx   ~89MB  WINDOWS/LINUX ONLY
    voices-v1.0.bin         ~27MB  WINDOWS/LINUX ONLY
MooReadAndroid/             LIVE Android Gradle project
  app/src/main/java/com/mooread/app/
    MainActivity.kt
    TtsPipeline.kt          sherpa OfflineTts + 5-ahead warmer + 16-bit AudioTrack
    SpeechSource.kt         PDF page-on-demand OCR
    ThemeFx.kt / ThemeFxController (if split)
    WallpaperPlayer.kt
    DocumentLoader.kt
    OcrHelper.kt
    VoiceProfiles.kt        jf_alpha among builtins
    …
  app/src/main/assets/kokoro/
    model.int8.onnx         114,203,756  ANDROID ONLY
    voices.bin              28,200,960   ANDROID sherpa bank ONLY
    tokens.txt              687
    lexicon-us-en.txt
    lexicon-zh.txt
    espeak-ng-data/
  app/libs/sherpa-onnx-1.13.8.aar
```

---

## Voice / read-ahead (current intended behavior)

- Chunk the document. Play one chunk at a time.
- A **warmer thread** keeps **the current chunk + the next 5** synthesized in memory.
- Play must **not** sit in a 20-second wait loop for the cache. If the current chunk is not ready, synthesize it now and speak. The warmer fills 1…5 behind that.
- After open, warmer starts even before Play so the first five can be ready.
- Status line should look like `Speaking 3/40 — 5 prepped`.
- First utterance of a brand-new file still costs one Kokoro pass. After that, gaps should be small.
- PDF: do **not** OCR the whole book into RAM. `SpeechSource` OCRs a page when the voice queue needs more speakable text. Skip page-number stubs (`[Page N]`).
- EPUB/TXT load through `DocumentLoader` then `pipeline.load(chunks)`.
- Android audio: **PCM 16-bit**, small `AudioTrack` buffer, write in frames. A track sized to the entire utterance fails on phones and kills the speak loop.
- One speak worker. Do not spawn a new play thread per chunk (that caused repeats, jumps, and “shot to the bottom”).
- Japanese: text with hiragana/katakana/kanji uses speaker `jf_alpha` (sid 37) when `numSpeakers` is large enough.

Desktop `mooread/voice/pipeline.py` uses the same “cursor + next 5” rule (`range(0, 6)` and `_allowed_ids`).

---

## Themes / background (do not regress)

- Themes are more than a color swap: scanlines, phosphor, vignette, flicker, DMG quantization, Platinum bevel.
- **No screen bending.** Barrel / pincushion was removed because it moved button hitboxes.
- “Normal — no shader” and **Reset** must return the default dark UI **and** detach the shader overlay. Use a generation counter on attach/detach. Persist prefs with `commit()` not a racy `apply()` if you touch SharedPreferences from the UI thread and immediately re-read them.
- Background menu is its own dropdown:
  - pick image/video
  - Wallpaper Engine file/folder (`project.json` / `scene.pkg`)
  - translucency slider: **100% opaque → 95% translucent** (alpha 1.0 → 0.05)
  - gyro / tilt aggressiveness (Android)
  - fit modes
  - mute
- Video wallpaper **loops**. That is unrelated to the reader Loop button.

Wallpaper Engine import (tell the user this, don’t invent a new format):

- Workshop folder with `project.json` + a video/image
- or `scene.pkg` / `.mpkg` (best-effort PKGV unpack in `wallpaper.py` / Android equivalent)
- Point the picker at the file or the folder. There is no Steam Workshop download inside the app (no internet).

---

## Build — Android (this sandbox)

```bash
export ANDROID_HOME=/opt/android-sdk
export ANDROID_SDK_ROOT=/opt/android-sdk
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export GRADLE_USER_HOME=/tmp/gradle-home2
export PATH="/tmp/android-dl/gradle-8.7/bin:$PATH"

cd MooReadAndroid
gradle :app:assembleDebug --no-daemon

cp app/build/outputs/apk/debug/app-debug.apk /workspace/artifacts/MooRead.apk
cd /workspace/artifacts
rm -f MooRead.apk.part*
split -b 30M -d -a 2 MooRead.apk MooRead.apk.part
# rewrite join_apk.bat copy /b list to match the part count
```

If Gradle/SDK are missing, they were previously at `/opt/android-sdk` and `/tmp/android-dl/gradle-8.7`.

After every APK, **unzip and check** before telling the user it is good:

```
assets/kokoro/model.int8.onnx   == 114203756
assets/kokoro/voices.bin        == 28200960 and not starting with PK
assets/kokoro/tokens.txt        == 687
assets/kokoro/lexicon-us-en.txt exists
assets/kokoro/lexicon-zh.txt    exists
```

---

## Build — Windows

Needs Python 3.11+ with Tk, then:

```bash
python -m pip install pillow pypdf striprtf python-docx ebooklib pypdfium2 numpy soundfile onnxruntime kokoro-onnx
```

Run `MooRead.bat` or `py -3 run.py` from `MooRead/`.

Models (desktop only):

- `MooRead/engine/kokoro/kokoro-v1.0.int8.onnx`
- `MooRead/engine/kokoro/voices-v1.0.bin`

---

## Build — Linux (Xorg and Wayland)

Tk talks X11. On Wayland it runs through XWayland. `run-linux.sh` sets `DISPLAY` if needed and `GDK_BACKEND=x11`.

```bash
sudo apt install python3 python3-tk python3-pip ffmpeg \
  tesseract-ocr tesseract-ocr-eng tesseract-ocr-jpn libportaudio2
python3 -m pip install --user pillow pypdf striprtf python-docx ebooklib \
  pypdfium2 numpy soundfile onnxruntime kokoro-onnx
chmod +x run-linux.sh
./run-linux.sh
```

Same desktop models as Windows. Same “do not use Android sherpa voices.bin here.”

---

## Feature status

| Feature | Desktop | Android | Notes |
|---|---|---|---|
| Native UI, dark default | Tk | Kotlin | no WebView |
| Kokoro local TTS | kokoro-onnx | sherpa 1.13.8 + multi-lang int8 | different voice banks |
| Japanese speaker | jf_alpha in voices-v1.0.bin | jf_alpha sid 37 + lexicons | do not mix banks |
| Lookahead 5 sections | yes | yes | warmer + play must not deadlock |
| Loop document | yes | yes | not the wallpaper loop |
| LTR / RTL order | yes | yes | |
| Camera / image OCR | file picker | TakePicture | |
| Progressive PDF OCR | deferred page OCR | SpeechSource | skip `[Page N]` stubs |
| Theme FX, no barrel | theme_fx.py | AGSL + overlay | Reset / Normal must fully detach |
| Background + opacity 100→5 | yes | yes | dedicated Background menu |
| Wallpaper Engine unpack | yes | yes | local files only |
| Video wallpaper loops | ffmpeg frames / player | MediaPlayer isLooping | |
| Gyro tilt + aggressiveness | n/a / mouse unused | yes | under Background |
| JA→EN translate | stub unless ONNX present | stub | do not pretend it is done |

---

## Bugs this session already hit (do not reintroduce)

- APK crash on launch: Windows or English voice bank paired with multi-lang model.
- “Shader is just a recolor”: overlay skipped on API 33+; AGSL `input` is reserved — use another uniform name.
- Barrel warp: buttons unreachable.
- Reset / Normal left the color theme stuck: stale layout listener + async prefs.
- Silent PDF: loaded `[Page N]` stubs only; also PCM_FLOAT AudioTrack rejected on device.
- “Stores 8 sections, never speaks”: full-document OCR + unspeakable stubs + play thread dying.
- Repeats / jumps / skip to bottom: **new play thread per chunk** + PdfRenderer used from two threads + replacing the whole TextView and scrolling.
- “Never starts reading”: speakable filter too strict (≥8 letters) + content URIs with no `.pdf` suffix + `AudioTrack` buffer = entire utterance + Play waited 20s per chunk for cache.
- Putting Windows files into the APK because the trees sit next to each other.

PDF detection on Android must use mime `*pdf*`, name containing `.pdf`, **or** `%PDF` magic bytes. `content://` last path segments often have no extension.

---

## How to work in the next session

1. Join `MooRead-source.zip`. Put this `HANDOFF.md` on top of whatever is inside if they differ.
2. Confirm Android assets sizes before any voice change.
3. Change one subsystem at a time. Build the APK. Tell the user what to look at on the status line.
4. Deliverables the user expects: updated APK splits + join bat, and if desktop changed, Windows / Linux / source splits too.
5. Split size is 30MB (`split -b 30M -d -a 2`). Rewrite the join bat every time the part count changes.
6. If the user says you broke playback, **read the speak loop and the warmer**. Do not guess. The status callbacks exist so the UI can show `generate failed: …` / `Playing N samples`.

---

## What is still unfinished / fragile

- Mixed-language documents: JP routing is “if this chunk looks Japanese use jf_alpha”, not a real translator.
- `translate.py` / on-device JA→EN ONNX may be absent.
- Very large scanned PDFs: OCR is page-at-a-time but ML Kit + Kokoro on device is still slow; first page can be silent if it is blank.
- Linux pack does **not** bundle an embed Python; user needs system `python3-tk`.
- Windows pack in these splits also expects system Python unless someone drops an embed `python/` next to `MooRead.bat`.
- Shader quality varies by Android GPU. Overlay fallback exists when RuntimeShader fails.

Do not “fix” those by ripping out Japanese, shaders, or lookahead unless the user asks.
