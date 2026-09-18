from __future__ import annotations

import json
import mimetypes
import shutil
import threading
import webbrowser
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from mooread import APP_NAME, __version__
from mooread.config import (
    FIRST_RUN_MESSAGE,
    FONTS_DIR,
    HOST,
    LIBRARY_DIR,
    PORT,
    ROOT,
    load_settings,
    reset_settings,
    save_settings,
)
from mooread.documents import SUPPORTED_EXTS, document_from_text, load_document
from mooread.ocr import LocalOcrEngine
from mooread.voice.engine import VoiceEngine
from mooread.voice.pipeline import ReadAheadPipeline
from mooread.voice.profiles import ProfileStore


WEB_DIR = ROOT / "web"


class AppState:
    def __init__(self) -> None:
        self.settings = load_settings()
        self.ocr = LocalOcrEngine()
        self.engine = VoiceEngine()
        self.profiles = ProfileStore()
        self.pipeline = ReadAheadPipeline(self.engine)
        self.document = None
        self.lock = threading.Lock()

    def open_path(self, path: str):
        doc = load_document(path, ocr_engine=self.ocr)
        profile = self.profiles.load(self.settings.get("voice_profile", "storyteller"))
        self.document = doc
        self.pipeline.load(
            doc,
            profile,
            rate=float(self.settings.get("rate", 1.0)),
            pitch=float(self.settings.get("pitch", 1.0)),
            volume=float(self.settings.get("volume", 1.0)),
        )
        return doc

    def open_text(self, text: str, title: str = "Camera", kind: str = "camera"):
        doc = document_from_text(text, title=title, kind=kind)
        profile = self.profiles.load(self.settings.get("voice_profile", "storyteller"))
        self.document = doc
        self.pipeline.load(
            doc,
            profile,
            rate=float(self.settings.get("rate", 1.0)),
            pitch=float(self.settings.get("pitch", 1.0)),
            volume=float(self.settings.get("volume", 1.0)),
        )
        return doc


STATE = AppState()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        # Keep the console readable.
        sys_print = print
        sys_print(f"[MooRead] {fmt % args}")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/health":
            return self._json(
                {
                    "app": APP_NAME,
                    "version": __version__,
                    "ocr": {"available": STATE.ocr.available, "status": STATE.ocr.status},
                    "voice": STATE.engine.info(),
                    "profiles": [p.to_dict() for p in STATE.profiles.list_profiles()],
                    "settings": STATE.settings,
                    "first_run_message": FIRST_RUN_MESSAGE,
                }
            )
        if path == "/api/settings":
            return self._json(STATE.settings)
        if path == "/api/library":
            items = []
            for p in sorted(LIBRARY_DIR.iterdir()):
                if p.is_file():
                    items.append({"name": p.name, "path": str(p), "size": p.stat().st_size})
            return self._json({"items": items})
        if path == "/api/document":
            doc = STATE.document
            if not doc:
                return self._json({"open": False})
            return self._json(
                {
                    "open": True,
                    "title": doc.title,
                    "kind": doc.kind,
                    "path": doc.path,
                    "text": doc.text,
                    "toc": [t.__dict__ for t in doc.toc],
                    "page_count": doc.page_count,
                    "ocr_used": doc.ocr_used,
                    "warnings": doc.warnings,
                    "char_count": doc.char_count,
                    "blocks": [{"index": b.index, "kind": b.kind, "text": b.text, "page": b.page} for b in doc.blocks],
                }
            )
        if path == "/api/session":
            return self._json(STATE.pipeline.status())
        if path.startswith("/api/audio/"):
            chunk_id = path.rsplit("/", 1)[-1]
            wav = STATE.pipeline.chunk_wav(chunk_id)
            if not wav or not wav.exists():
                return self._error("audio not ready", HTTPStatus.NOT_FOUND)
            data = wav.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/api/font":
            font = next(FONTS_DIR.glob("custom.*"), None)
            if not font or not font.exists():
                return self._error("no custom font", HTTPStatus.NOT_FOUND)
            data = font.read_bytes()
            mime = "font/ttf"
            if font.suffix.lower() == ".otf":
                mime = "font/otf"
            elif font.suffix.lower() == ".woff":
                mime = "font/woff"
            elif font.suffix.lower() == ".woff2":
                mime = "font/woff2"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
            return
        if path.startswith("/api/"):
            return self._error("not found", HTTPStatus.NOT_FOUND)
        return super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/open":
            return self._open()
        if path == "/api/settings":
            body = self._read_json()
            if body.get("reset"):
                STATE.settings = reset_settings()
                return self._json(STATE.settings)
            STATE.settings.update(body)
            save_settings(STATE.settings)
            return self._json(STATE.settings)
        if path == "/api/open-folder":
            return self._open_folder()
        if path == "/api/open-path":
            body = self._read_json()
            path_on_disk = body.get("path")
            if not path_on_disk:
                return self._error("missing path")
            try:
                doc = STATE.open_path(path_on_disk)
            except Exception as exc:
                return self._error(str(exc))
            return self._json({"ok": True, "title": doc.title, "kind": doc.kind})
        if path == "/api/font":
            return self._import_font()
        if path == "/api/voices/import":
            return self._import_voice()
        if path == "/api/session/start":
            body = self._read_json()
            if STATE.document is None:
                return self._error("open a document first")
            profile_id = body.get("profile") or STATE.settings.get("voice_profile")
            profile = STATE.profiles.load(profile_id)
            if body.get("kokoro_voice"):
                profile.kokoro_voice = body["kokoro_voice"]
            STATE.pipeline.profile = profile
            STATE.pipeline.rate = float(body.get("rate", STATE.settings.get("rate", 1.0)))
            STATE.pipeline.pitch = float(body.get("pitch", STATE.settings.get("pitch", 1.0)))
            STATE.pipeline.volume = float(body.get("volume", STATE.settings.get("volume", 1.0)))
            if "cursor" in body:
                STATE.pipeline.seek(int(body["cursor"]))
            return self._json(STATE.pipeline.start())
        if path == "/api/session/pause":
            return self._json(STATE.pipeline.pause())
        if path == "/api/session/resume":
            return self._json(STATE.pipeline.resume())
        if path == "/api/session/stop":
            STATE.pipeline.stop()
            return self._json({"ok": True})
        if path == "/api/session/seek":
            body = self._read_json()
            return self._json(STATE.pipeline.seek(int(body.get("index", 0))))
        if path == "/api/session/played":
            body = self._read_json()
            return self._json(STATE.pipeline.mark_played(body.get("id", "")))
        return self._error("not found", HTTPStatus.NOT_FOUND)

    def _open(self) -> None:
        ctype = self.headers.get("Content-Type", "")
        if "multipart/form-data" in ctype:
            path = self._save_multipart()
        else:
            body = self._read_json()
            path = body.get("path")
        if not path:
            return self._error("missing file")
        suffix = Path(path).suffix.lower()
        if suffix not in SUPPORTED_EXTS:
            return self._error(f"unsupported type: {suffix or 'unknown'}")
        try:
            doc = STATE.open_path(path)
        except Exception as exc:
            return self._error(str(exc))
        return self._json(
            {
                "ok": True,
                "title": doc.title,
                "kind": doc.kind,
                "char_count": doc.char_count,
                "page_count": doc.page_count,
                "ocr_used": doc.ocr_used,
                "warnings": doc.warnings,
            }
        )

    def _import_font(self) -> None:
        path = self._save_multipart(dest_dir=FONTS_DIR)
        src = Path(path)
        dest = FONTS_DIR / f"custom{src.suffix.lower() or '.ttf'}"
        if dest.exists() and dest != src:
            dest.unlink()
        if src != dest:
            src.replace(dest)
        STATE.settings["font_file"] = dest.name
        STATE.settings["font_family"] = "MooReadCustom, Georgia, serif"
        save_settings(STATE.settings)
        return self._json({"ok": True, "font": dest.name})

    def _import_voice(self) -> None:
        ctype = self.headers.get("Content-Type", "")
        if "multipart/form-data" in ctype:
            path = self._save_multipart(dest_dir=None)
        else:
            path = self._read_json().get("path")
        if not path:
            return self._error("missing voice profile")
        try:
            profile = STATE.profiles.import_file(path)
        except Exception as exc:
            return self._error(str(exc))
        return self._json({"ok": True, "profile": profile.to_dict()})

    def _open_folder(self) -> None:
        body = self._read_json()
        folder = body.get("path")
        if not folder:
            return self._error("missing folder")
        root = Path(folder)
        if not root.is_dir():
            return self._error("not a directory")
        items = []
        for p in sorted(root.rglob("*")):
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
                items.append({"name": p.name, "path": str(p), "size": p.stat().st_size})
            if len(items) >= 400:
                break
        return self._json({"ok": True, "items": items, "folder": str(root)})

    def _save_multipart(self, dest_dir=LIBRARY_DIR) -> str:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        content_type = self.headers.get("Content-Type", "")
        boundary = None
        for part in content_type.split(";"):
            part = part.strip()
            if part.startswith("boundary="):
                boundary = part.split("=", 1)[1].strip().strip('"').encode("utf-8")
        if not boundary:
            raise RuntimeError("bad multipart")
        chunks = body.split(b"--" + boundary)
        for chunk in chunks:
            if b"filename=" not in chunk:
                continue
            header, _, data = chunk.partition(b"\r\n\r\n")
            data = data.rstrip(b"\r\n")
            if data.endswith(b"--"):
                data = data[:-2]
            header_text = header.decode("utf-8", errors="ignore")
            filename = "upload.bin"
            for token in header_text.split(";"):
                token = token.strip()
                if token.startswith("filename="):
                    filename = token.split("=", 1)[1].strip().strip('"')
            target_dir = dest_dir if dest_dir is not None else LIBRARY_DIR
            target_dir.mkdir(parents=True, exist_ok=True)
            dest = Path(target_dir) / Path(filename).name
            dest.write_bytes(data)
            return str(dest)
        raise RuntimeError("no file in upload")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def _json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _error(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST) -> None:
        self._json({"ok": False, "error": message}, status=status)

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def main() -> None:
    print(f"MooRead {__version__} native UI (no WebView)")
    print("Local OCR:", STATE.ocr.status)
    print("Voice backend:", STATE.engine.info())
    from mooread.ui_native import MooReadApp

    app = MooReadApp(STATE)
    app.run()
    STATE.pipeline.stop()


if __name__ == "__main__":
    main()
