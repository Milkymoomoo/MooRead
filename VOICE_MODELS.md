# Voice models (not stored in this repo)

These files are too large for GitHub. Download them yourself and drop them in the paths below.
**Do not mix the two packs.** Windows `voices-v1.0.bin` is a numpy archive for kokoro-onnx. Android `voices.bin` is a raw float dump for sherpa-onnx. Swapping them crashes the APK.

Voice names (`af_bella`, `jf_alpha`, …): [hexgrad/Kokoro-82M VOICES.md](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md)

## Windows / Linux desktop — kokoro-onnx

Put both files in `MooRead/engine/kokoro/`:

| File | What it is |
|---|---|
| `kokoro-v1.0.int8.onnx` | Quantized Kokoro-82M network. Turns phonemes into 24 kHz speech. |
| `voices-v1.0.bin` | 54 speaker embeddings (style vectors) for that ONNX graph. Includes English + `jf_alpha` Japanese, etc. |

Download (official kokoro-onnx release):

- Release page: https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0
- Model: https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx
- Voices: https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin

Upstream voice research model: https://huggingface.co/hexgrad/Kokoro-82M

## Android — sherpa-onnx Kokoro multi-lang

Unpack into `MooReadAndroid/app/src/main/assets/kokoro/` so these names exist:

| File / folder | What it is |
|---|---|
| `model.int8.onnx` | Sherpa export of Kokoro multi-lang (EN + JA + others). |
| `voices.bin` | Sherpa speaker table (raw floats, ~28,200,960 bytes). Not the Windows npz file. |
| `tokens.txt` | Token id map for the model. |
| `lexicon-us-en.txt` | US English pronunciations. |
| `lexicon-zh.txt` | Chinese pronunciations (used by the multi-lang graph). |
| `espeak-ng-data/` | Grapheme-to-phoneme data (needed for English and Japanese). |

Download the official sherpa pack (extract, then copy/rename `model.onnx` → `model.int8.onnx` if the tarball uses that name):

- Multi-lang v1.0 tarball: https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/kokoro-multi-lang-v1_0.tar.bz2
- Sherpa TTS model list: https://k2-fsa.github.io/sherpa/onnx/tts/all/print.html
- Sherpa Android AAR (same version the Gradle file pins, 1.13.8): https://github.com/k2-fsa/sherpa-onnx/releases

`jf_alpha` is speaker id 37 in the multi-lang table (Japanese female). That is why the Android pack must be multi-lang, not the English-only `kokoro-en-v0_19` zip.
