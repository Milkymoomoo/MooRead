MooRead on Linux (Xorg and Wayland)
==================================

This is the same Python app as Windows. The window toolkit is Tk,
which talks X11. On Wayland it runs through XWayland (normal on
GNOME, KDE, Sway, etc.).

Install (Debian/Ubuntu):
  sudo apt install python3 python3-tk python3-pip python3-venv \
    ffmpeg tesseract-ocr tesseract-ocr-eng tesseract-ocr-jpn \
    libportaudio2

  python3 -m pip install --user pillow pypdf striprtf python-docx \
    ebooklib pypdfium2 numpy soundfile onnxruntime kokoro-onnx

Run:
  chmod +x run-linux.sh
  ./run-linux.sh

Kokoro models belong in engine/kokoro/:
  kokoro-v1.0.int8.onnx
  voices-v1.0.bin

Do not copy Android sherpa voices.bin here.
