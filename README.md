# MooRead

Desktop (Windows/Linux) and Android reader with offline Kokoro TTS.

**Live Android tree is `MooReadAndroid/`, not `MooRead/android/`.**

## Voice models

Weights are **not** in git. See **[VOICE_MODELS.md](VOICE_MODELS.md)** for what each file does and the official download links.

Short version:

- Desktop → [kokoro-onnx model-files-v1.0](https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0)  
  `kokoro-v1.0.int8.onnx` + `voices-v1.0.bin` → `MooRead/engine/kokoro/`
- Android → [sherpa kokoro-multi-lang-v1_0](https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/kokoro-multi-lang-v1_0.tar.bz2)  
  `model.int8.onnx` + `voices.bin` + lexicons + `espeak-ng-data/` → `MooReadAndroid/app/src/main/assets/kokoro/`

Do **not** copy Windows `voices-v1.0.bin` onto the APK.

Speaker list: [Kokoro-82M VOICES.md](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md)

## Layout

- `MooReadAndroid/` — Kotlin app (PdfTextSource, SpeechSource, TtsPipeline, ThemeFx)
- `MooRead/` — Python desktop app (`run.py`, `ui_native.py`, `voice/player.py`)

## Android

```
cd MooReadAndroid
# set sdk.dir in local.properties
./gradlew :app:assembleDebug
apksigner sign --ks debug.keystore app/build/outputs/apk/debug/app-debug.apk
```

Unsigned APKs will not install.

## Desktop

```
cd MooRead
python -m pip install -r requirements.txt
python run.py          # or ./run-linux.sh
```
