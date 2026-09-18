# Weights not fully in this zip (too large)

Windows Kokoro:
  /workspace/artifacts/MooRead/engine/kokoro/kokoro-v1.0.int8.onnx
  /workspace/artifacts/MooRead/engine/kokoro/voices-v1.0.bin
  also /tmp/MooReadWin/engine/kokoro/

Android Kokoro (sherpa):
  /tmp/MooReadAndroid/app/src/main/assets/kokoro/model.int8.onnx   (~128MB)
  voices.bin in this zip is the SAFE 5.5MB sherpa bank. Do not replace with voices-v1.0.bin.

Copy models into the matching folders before building a runnable APK/EXE.
