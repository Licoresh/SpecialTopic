"""Anonymous upload endpoint for the approved shared research engine."""

from http.server import BaseHTTPRequestHandler
import json
from urllib.parse import unquote

from src.public_engine import ClassifierUnavailable, analyze_request, health


MAX_RESPONSE_BYTES = 4_300_000


class handler(BaseHTTPRequestHandler):
    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._json(200, health(hosted=True))

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json(400, {"error": "Invalid upload length."})
            return
        if length < 1:
            self._json(400, {"error": "Choose a nonempty CSV file."})
            return
        if length > health(hosted=True)["maxUploadBytes"]:
            self._json(413, {"error": "Hosted analysis accepts CSV files up to 4 MB. Use the localhost analyzer for larger files."})
            return
        try:
            mapping = json.loads(unquote(self.headers.get("X-Column-Mapping", "")))
            if not isinstance(mapping, dict):
                raise ValueError("Review the column mapping and try again.")
            filename = unquote(self.headers.get("X-Filename", "job-ads.csv"))
            result = analyze_request(self.rfile.read(length), filename, mapping)
            body = json.dumps({"result": result}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            if len(body) > MAX_RESPONSE_BYTES:
                self._json(413, {"error": "This dataset produces too much chart detail for hosted analysis. Split it into smaller CSV files."})
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except ClassifierUnavailable as exc:
            self._json(503, {"error": str(exc)})
        except (ValueError, OSError, KeyError) as exc:
            self._json(400, {"error": str(exc)})
        except Exception:
            self._json(500, {"error": "The research engine could not complete this file. Verify the CSV and try again."})
