"""HTTP server and route dispatch for the local frontend."""

import json
import mimetypes
import os
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from app.api.common import json_default
from app.api.heatmap import get_progress_date_heatmap_payload
from app.api.high_energy import get_high_energy_payload
from app.api.parallel import get_video_parallel_stats_payload
from app.api.similarity import get_video_similarity_matrix_payload, get_video_similarity_payload
from app.api.videos import get_video_detail_payload, get_videos_payload
from app.api.word_cloud import get_trend_payload, get_word_cloud_payload
from app.paths import FRONTEND_DIR


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = int(os.environ.get("PORT", "8080"))
COVER_ALLOWED_HOSTS = {"i0.hdslb.com", "i1.hdslb.com", "i2.hdslb.com", "archive.biliimg.com"}
MAX_COVER_BYTES = 8 * 1024 * 1024


class ApiHandler(BaseHTTPRequestHandler):
    def send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False, default=json_default).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, message, status=400):
        self.send_json({"error": message}, status=status)

    def do_GET(self):
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/videos":
                self.send_json(get_videos_payload())
                return
            if parsed.path == "/api/video-detail":
                self.send_json(get_video_detail_payload(parse_qs(parsed.query)))
                return
            if parsed.path == "/api/danmaku-trend":
                self.send_json(get_trend_payload(parse_qs(parsed.query)))
                return
            if parsed.path == "/api/word-cloud":
                self.send_json(get_word_cloud_payload(parse_qs(parsed.query)))
                return
            if parsed.path == "/api/video-similarity":
                self.send_json(get_video_similarity_payload(parse_qs(parsed.query)))
                return
            if parsed.path == "/api/video-similarity-matrix":
                self.send_json(get_video_similarity_matrix_payload(parse_qs(parsed.query)))
                return
            if parsed.path == "/api/video-parallel-stats":
                self.send_json(get_video_parallel_stats_payload(parse_qs(parsed.query)))
                return
            if parsed.path == "/api/progress-date-heatmap":
                self.send_json(get_progress_date_heatmap_payload(parse_qs(parsed.query)))
                return
            if parsed.path == "/api/high-energy":
                self.send_json(get_high_energy_payload(parse_qs(parsed.query)))
                return
            if parsed.path == "/api/cover":
                self.serve_cover(parse_qs(parsed.query))
                return
            self.serve_static(parsed.path)
        except Exception as exc:
            traceback.print_exc()
            self.send_error_json(str(exc), status=500)

    def serve_cover(self, query):
        url = query.get("url", [""])[0]
        if not url:
            self.send_error(400)
            return
        if url.startswith("http://"):
            url = "https://" + url[len("http://"):]

        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in COVER_ALLOWED_HOSTS:
            self.send_error(400)
            return

        request = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www.bilibili.com/",
            },
        )
        with urlopen(request, timeout=15) as response:
            content_type = response.headers.get("Content-Type") or "image/jpeg"
            body = response.read(MAX_COVER_BYTES + 1)
        if len(body) > MAX_COVER_BYTES:
            self.send_error(502)
            return
        if not content_type.startswith("image/"):
            self.send_error(502)
            return

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "public, max-age=86400")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_static(self, request_path):
        path = request_path.lstrip("/") or "index.html"
        frontend_root = FRONTEND_DIR.resolve()
        file_path = (frontend_root / path).resolve()
        try:
            file_path.relative_to(frontend_root)
        except ValueError:
            self.send_error(403)
            return
        if file_path.is_dir():
            file_path = file_path / "index.html"
        if not file_path.exists():
            self.send_error(404)
            return

        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    server = ThreadingHTTPServer((DEFAULT_HOST, DEFAULT_PORT), ApiHandler)
    print(f"API + frontend server: http://{DEFAULT_HOST}:{DEFAULT_PORT}")
    server.serve_forever()
