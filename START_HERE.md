# START HERE

You are continuing **MooRead**.

1. Read `HANDOFF.md` in this folder. It is the source of truth.
2. Join `MooRead-source.zip` (`join_source.bat` or `cat MooRead-source.zip.part00 … part09`).
3. Live code is:
   - `MooRead/` — Windows / Linux Python + Tk
   - `MooReadAndroid/` — Android Gradle (**not** `MooRead/android/`)
4. Android `assets/kokoro/voices.bin` is the **28,200,960-byte sherpa multi-lang** bank.
   Do **not** use Windows `voices-v1.0.bin` and do **not** use the old 5.5MB English bank.
5. Voice lookahead is current + next 5 sections. Do not barrel-distort the theme shader.
