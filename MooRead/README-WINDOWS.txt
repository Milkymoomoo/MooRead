MooRead for Windows

1. Install Python 3.11+ from python.org (check "tcl/tk" and "Add python.exe to PATH").
2. Open this folder in cmd and run:
     python -m pip install -r requirements.txt
3. Double-click MooRead.exe  (or MooRead.bat).

MooRead.exe only starts MooRead.bat in this folder. The voice engine is the
Python app plus engine\kokoro\kokoro-v1.0.int8.onnx and voices-v1.0.bin.

Do not copy voices-v1.0.bin onto the Android APK.
