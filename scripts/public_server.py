"""Serve the public analyzer and its research-engine API on localhost."""

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "public-web/site"
sys.path.insert(0, str(ROOT))

from src.public_engine import ClassifierUnavailable, analyze_upload, health


class PublicHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SITE), **kwargs)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; connect-src 'self'; worker-src 'self'; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        super().end_headers()

    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if urlsplit(self.path).path == "/api/health":
            self._json(200, health())
            return
        super().do_GET()

    def do_POST(self):
        if urlsplit(self.path).path != "/api/analyze":
            self._json(404, {"error": "Not found."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json(400, {"error": "Invalid upload length."})
            return
        if length < 1:
            self._json(400, {"error": "Choose a nonempty CSV file."})
            return
        if length > health()["maxUploadBytes"]:
            self._json(413, {"error": "This analysis server accepts CSV files up to 64 MB."})
            return
        try:
            mapping = json.loads(unquote(self.headers.get("X-Column-Mapping", "")))
            if not isinstance(mapping, dict):
                raise ValueError("Review the column mapping and try again.")
            filename = unquote(self.headers.get("X-Filename", "job-ads.csv"))
            content = self.rfile.read(length)
            if len(content) != length:
                raise ValueError("The upload ended before the complete CSV was received.")
            result = analyze_upload(content, filename, mapping)
            self._json(200, {"result": result})
        except ClassifierUnavailable as exc:
            self._json(503, {"error": str(exc)})
        except (ValueError, OSError, KeyError) as exc:
            self._json(400, {"error": str(exc)})
        except Exception:
            self._json(500, {"error": "The research engine could not complete this file. Verify the CSV and try again."})


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8502)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), PublicHandler)
    print(f"Public analyzer listening at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
