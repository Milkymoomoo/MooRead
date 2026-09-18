# MooRead

Desktop (Windows/Linux) and Android reader with offline Kokoro TTS.

**Live Android tree is `MooReadAndroid/`, not `MooRead/android/`.**

## Android screenshot

See [docs/ANDROID.md](docs/ANDROID.md). Three panels from a real device: theme picker, Amber CRT chrome, Amber CRT while speaking.

Amber CRT keeps phosphor + scanlines + flicker. **Barrel / curved-screen warp was removed** so controls stay reachable.

Book files are not bundled. The *Tides of War* PDF used in testing is **not** in this repository.

## Voice models

Weights are **not** in git. See **[VOICE_MODELS.md](VOICE_MODELS.md)**.

- Desktop → [kokoro-onnx model-files-v1.0](https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0)  
  `kokoro-v1.0.int8.onnx` + `voices-v1.0.bin` → `MooRead/engine/kokoro/`
- Android → [sherpa kokoro-multi-lang-v1_0](https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/kokoro-multi-lang-v1_0.tar.bz2)  
  → `MooReadAndroid/app/src/main/assets/kokoro/`

Do **not** copy Windows `voices-v1.0.bin` onto the APK.

Speaker list: [Kokoro-82M VOICES.md](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md)

## Layout

- `MooReadAndroid/` — Kotlin app
- `MooRead/` — Python desktop app

## Android build

```
cd MooReadAndroid
./gradlew :app:assembleDebug
apksigner sign --ks debug.keystore app/build/outputs/apk/debug/app-debug.apk
```

## Desktop

```
cd MooRead
python -m pip install -r requirements.txt
python run.py
```
