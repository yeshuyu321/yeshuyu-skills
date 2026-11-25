#!/usr/bin/env python3
"""Local media -> temporary single-audio URL -> durable quota pool."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import volc_auc
import volc_pool

class _Limited:
    def __init__(self, fh, remaining: int) -> None:
        self.fh = fh
        self.remaining = remaining

    def read(self, amt: int = -1) -> bytes:
        if self.remaining <= 0:
            return b""
        if amt < 0 or amt > self.remaining:
            amt = self.remaining
        data = self.fh.read(amt)
        self.remaining -= len(data)
        return data

    def close(self) -> None:
        self.fh.close()


def make_handler(root: str, allowed_name: str):
    class RangeHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=root, **kwargs)

        def log_message(self, *args):
            pass

        def send_head(self):
            if urllib.parse.unquote(urllib.parse.urlsplit(self.path).path) != "/" + allowed_name:
                self.send_error(404)
                return None
            path = self.translate_path(self.path)
            if os.path.isdir(path):
                return super().send_head()
            try:
                fh = open(path, "rb")
            except OSError:
                self.send_error(404, "File not found")
                return None
            size = os.fstat(fh.fileno()).st_size
            ctype = self.guess_type(path)
            match = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range") or "")
            if match and (match.group(1) or match.group(2)):
                start = int(match.group(1)) if match.group(1) else 0
                end = int(match.group(2)) if match.group(2) else size - 1
                end = min(end, size - 1)
                if start > end or start >= size:
                    self.send_error(416, "Requested Range Not Satisfiable")
                    fh.close()
                    return None
                self.send_response(206)
                self.send_header("Content-Type", ctype)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.send_header("Content-Length", str(end - start + 1))
                self.end_headers()
                fh.seek(start)
                return _Limited(fh, end - start + 1)
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(size))
            self.end_headers()
            return fh

    return RangeHandler


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--file', required=True, type=Path)
    ap.add_argument('--out-dir', required=True, type=Path)
    ap.add_argument('--uid', default='shengjiang-local')
    ap.add_argument('--profile')
    ap.add_argument('--stem', default='')
    ap.add_argument('--timeout', type=int, default=3600)
    ap.add_argument('--poll', type=int, default=5)
    ap.add_argument('--port', type=int, default=0)
    args = ap.parse_args()
    cloudflared = os.environ.get('CLOUDFLARED') or shutil.which('cloudflared')
    if not cloudflared:
        ap.exit(1, 'cloudflared missing; set CLOUDFLARED to its executable path\n')
    media = args.file.expanduser().resolve()
    if not media.is_file():
        ap.error('media file does not exist')
    digest = hashlib.sha256()
    with media.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(chunk)
    with tempfile.TemporaryDirectory(prefix='volc-single-audio-') as temporary:
        temp = Path(temporary)
        audio = temp / (uuid.uuid4().hex + '.mp3')
        subprocess.run(['ffmpeg', '-v', 'error', '-i', str(media), '-vn', '-ac', '1',
                        '-ar', '16000', '-b:a', '64k', str(audio)], check=True,
                       capture_output=True)
        duration = volc_auc.probe_duration(audio)
        server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(str(temp), audio.name))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        proc = None
        try:
            with (temp / 'tunnel.log').open('wb') as log:
                proc = subprocess.Popen([cloudflared, 'tunnel', '--url',
                    f'http://127.0.0.1:{server.server_port}', '--no-autoupdate'],
                    stdout=log, stderr=subprocess.STDOUT)
                deadline = time.monotonic() + 75
                tunnel = None
                while time.monotonic() < deadline:
                    output = (temp / 'tunnel.log').read_text(errors='replace')
                    found = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', output)
                    if found and 'Registered tunnel connection' in output:
                        tunnel = found.group(0)
                        break
                    if proc.poll() is not None:
                        break
                    time.sleep(1)
                if not tunnel:
                    raise RuntimeError('Temporary audio tunnel failed; nothing submitted')
                public_url = tunnel + '/' + audio.name
                ready = False
                reachability_error = ''
                for _ in range(5):
                    try:
                        req = urllib.request.Request(public_url, headers={'Range':'bytes=0-99'})
                        with urllib.request.urlopen(req, timeout=10) as response:
                            ready = response.status == 206 and len(response.read()) == 100
                        if ready:
                            break
                    except Exception as exc:
                        reachability_error = type(exc).__name__ + ": " + str(exc)
                    time.sleep(2)
                if not ready:
                    raise RuntimeError('Temporary audio URL is not reachable; nothing submitted: ' + reachability_error)
                result, route = volc_pool.transcribe(public_url,
                    audio_format='mp3', uid=args.uid, duration_seconds=duration,
                    input_key='sha256:' + digest.hexdigest(), profile_id=args.profile,
                    timeout_seconds=args.timeout, poll_interval=args.poll)
                files = volc_auc.write_transcript_files(result, args.out_dir,
                    title=args.stem or media.stem, source='火山 ASR ' + route)
                print(json.dumps({'route': route, 'files': files}, ensure_ascii=False))
        except Exception as exc:
            ap.exit(1, volc_pool.clean_error(exc, volc_pool.load()) + '\n')
        finally:
            if proc is not None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    main()
