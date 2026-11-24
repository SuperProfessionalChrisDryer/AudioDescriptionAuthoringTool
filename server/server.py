#!/usr/bin/env python3
"""AD scan server v1 — local scan service for the AD authoring prototype.

Standard library only (http.server). Listens on 127.0.0.1:8765 by default;
override with AD_HOST / AD_PORT.

Endpoints:
  GET  /health   -> {"ok": true, "version": 1}
  GET  /         -> this help page
  POST /scan     -> multipart/form-data, file field "file" (video or audio),
                    optional form field "provider" ("none" default;
                    "claude" / "openai" / "kavi"). Returns the scan JSON.

v1 is scan only. There is no TTS and no /export yet — those are phase 2
(see README.md). Long scans run in the request thread; a 14-minute clip
takes a few minutes to transcribe on CPU, so the client must wait (or poll
nothing — v1 has no progress endpoint, the connection simply stays open).
"""

import json
import os
import re
import sys
import tempfile
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

VERSION = 1
HOST = os.environ.get("AD_HOST", "127.0.0.1")
PORT = int(os.environ.get("AD_PORT", "8765"))
MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB
PROVIDERS = ("none", "claude", "openai", "kavi")

HELP_HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>AD scan server v1</title></head><body style="font-family:sans-serif;max-width:640px;margin:2em auto">
<h1>AD scan server v1</h1>
<p>Local scan service for the AD authoring prototype. Scan only — no TTS, no audio export yet.</p>
<h2>Endpoints</h2>
<ul>
<li><code>GET /health</code> — <code>{"ok": true, "version": 1}</code></li>
<li><code>POST /scan</code> — multipart/form-data, file field <code>file</code> (a video or audio file),
optional form field <code>provider</code> (<code>none</code> default, <code>claude</code>, <code>openai</code>, <code>kavi</code>).
Returns <code>{"spots": [...], "transcript": [...], "wave": {...}, "meta": {...}}</code>.</li>
</ul>
<h2>Try it</h2>
<pre>curl -F file=@clip.mp4 -F provider=none http://127.0.0.1:8765/scan</pre>
<p>Providers <code>claude</code>/<code>openai</code> need <code>ANTHROPIC_API_KEY</code> /
<code>OPENAI_API_KEY</code> set before starting the server. <code>kavi</code> is not
available from the server — drafting with Kavi stays the chat flow.</p>
</body></html>"""


def log(msg):
    print("[%s] %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg), flush=True)


def parse_multipart(body, boundary):
    """Minimal multipart/form-data parser (stdlib only).

    Returns (fields, files): fields maps name -> str, files maps name ->
    (filename, bytes). Only the parts we need; anything else is ignored.
    """
    fields, files = {}, {}
    for part in body.split(b"--" + boundary):
        if not part or part in (b"--", b"--\r\n"):
            continue
        if part.startswith(b"\r\n"):
            part = part[2:]
        if part.endswith(b"\r\n"):
            part = part[:-2]
        if part.endswith(b"--"):
            part = part[:-2]
        if b"\r\n\r\n" not in part:
            continue
        head, data = part.split(b"\r\n\r\n", 1)
        headers = {}
        for line in head.decode("utf-8", "replace").split("\r\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()
        disp = headers.get("content-disposition", "")
        m = re.search(r'name="([^"]*)"', disp)
        if not m:
            continue
        name = m.group(1)
        fm = re.search(r'filename="([^"]*)"', disp)
        if fm:
            files[name] = (fm.group(1), data)
        else:
            fields[name] = data.decode("utf-8", "replace")
    return fields, files


def safe_filename(name):
    name = os.path.basename(name or "upload")
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name) or "upload"
    return name[:120]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass  # we log ourselves, in log()

    def _send(self, status, body, content_type="application/json"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        # CORS: the published prototype page calls this local server
        # cross-origin, and Chrome's Private Network Access check needs
        # the Allow-Private-Network header on the reply.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status, obj):
        self._send(status, json.dumps(obj))

    def _error(self, status, message):
        self._json(status, {"error": message})

    def do_OPTIONS(self):
        # Browser preflight for the published page calling this local
        # server: allow cross-origin POSTs, including Private Network Access.
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Max-Age", "86400")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            self._json(200, {"ok": True, "version": VERSION})
        elif path == "/":
            self._send(200, HELP_HTML, "text/html; charset=utf-8")
        else:
            self._error(404, "unknown path: %s" % path)

    def do_POST(self):
        from scan import ScanError, run_scan

        path = urlparse(self.path).path
        if path != "/scan":
            self._error(404, "unknown path: %s" % path)
            return

        ctype = self.headers.get("Content-Type", "")
        m = re.search(r"multipart/form-data;\s*boundary=(.+)", ctype)
        if not m:
            self._error(400, "POST /scan needs multipart/form-data with a "
                             "file field named 'file'")
            return
        boundary = m.group(1).strip().strip('"').encode("ascii")

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0:
            self._error(400, "empty request body — send a file")
            return
        if length > MAX_UPLOAD_BYTES:
            self._error(413, "file too large (limit 2 GB)")
            return
        try:
            body = self.rfile.read(length)
        except Exception as e:
            self._error(400, "could not read request body: %s" % e)
            return

        fields, files = parse_multipart(body, boundary)
        if "file" not in files:
            self._error(400, "missing file field 'file' — send the video or "
                             "audio as multipart field 'file'")
            return
        filename, data = files["file"]
        if not data:
            self._error(400, "the uploaded file is empty")
            return
        provider = fields.get("provider", "none").strip().lower() or "none"
        if provider not in PROVIDERS:
            self._error(400, "unknown provider %r (use none, claude, openai, "
                             "kavi)" % provider)
            return

        log("scan: %s (%d bytes, provider=%s)"
            % (filename or "upload", len(data), provider))
        started = time.time()
        try:
            with tempfile.TemporaryDirectory(prefix="adscan-") as td:
                upload_path = os.path.join(td, safe_filename(filename))
                with open(upload_path, "wb") as f:
                    f.write(data)
                result = run_scan(upload_path, provider)
        except ScanError as e:
            log("scan failed (%s): %s" % (filename, e))
            self._error(getattr(e, "status", 400), str(e))
            return
        except Exception:
            log("scan crashed (%s):\n%s" % (filename, traceback.format_exc()))
            self._error(500, "internal error while scanning — see the "
                             "server log")
            return
        elapsed = time.time() - started
        log("scan done: %s in %.1fs — %d spots (%d pause, %d scene), "
            "provider=%s"
            % (filename, elapsed, len(result["spots"]),
               sum(1 for s in result["spots"] if s["type"] == "pause"),
               sum(1 for s in result["spots"] if s["type"] == "scene"),
               provider))
        self._json(200, result)


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    log("AD scan server v1 listening on http://%s:%d (Ctrl-C to stop)"
        % (HOST, PORT))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("stopping")
        server.shutdown()


if __name__ == "__main__":
    main()
