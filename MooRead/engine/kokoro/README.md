# Bundled neural voice (Kokoro-82M)

These two files **are** the voice engine. They stay inside the app.

| File | What it is |
| --- | --- |
| `kokoro-v1.0.int8.onnx` | Quantized Kokoro-82M acoustic model (~88 MB). Apache-2.0. |
| `voices-v1.0.bin` | 54 speaker style vectors (~27 MB). |

Inference is local ONNX Runtime. Phonemes are produced on-device by Misaki + the bundled espeak-ng loader. No cloud, no Windows SAPI, no Android system voice for the desktop app.

Swap in a full-precision `kokoro-v1.0.onnx` later if you want; keep the same `voices-v1.0.bin`. Custom identities are JSON voice profiles that name a speaker, mix two speakers, or point `voice_vector` at a `.npy` style file.
