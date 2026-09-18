# MooRead

Desktop (Windows/Linux) and Android reader with offline Kokoro TTS.

**Live Android tree is `MooReadAndroid/`, not `MooRead/android/`.**

Do not copy Windows `engine/kokoro/voices-v1.0.bin` onto the APK.
Android uses sherpa-onnx multi-lang assets. Desktop uses kokoro-onnx.

## Layout

- `MooReadAndroid/` — Kotlin app (PdfTextSource, SpeechSource, TtsPipeline, ThemeFx)
- `MooRead/` — Python desktop app (`run.py`, `ui_native.py`, `voice/player.py`)
- Windows pack ships a real `MooRead.exe` that launches bundled `python/pythonw.exe run.py`

## Android

```
cd MooReadAndroid
# set sdk.dir in local.properties
./gradlew :app:assembleDebug
apksigner sign --ks debug.keystore app/build/outputs/apk/debug/app-debug.apk
```

Unsigned APKs will not install. Voice models (`*.onnx`, `voices.bin`, lexicons) are not in this git repo (too large). Copy them from a previous APK `assets/kokoro/` or a release zip.

## Desktop

```
cd MooRead
python -m pip install -r requirements.txt
python run.py          # or ./run-linux.sh
```

Kokoro weights belong in `MooRead/engine/kokoro/` (`kokoro-v1.0.int8.onnx`, `voices-v1.0.bin`).
