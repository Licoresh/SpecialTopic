"""Health and capability information for the public analysis function."""

from http.server import BaseHTTPRequestHandler
import json

from src.public_engine import health


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps(health(hosted=True), separators=(",", ":")).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
