from __future__ import annotations

import json
import mimetypes
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ui.platform import TicketingPlatform


def _make_handler(platform: TicketingPlatform, static_dir: Path) -> type[BaseHTTPRequestHandler]:
    class TicketingHandler(BaseHTTPRequestHandler):
        server_version = "TicketingPlatform/1.0"

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._serve_static_file(static_dir / "index.html")
                return
            if parsed.path == "/api/dashboard":
                query = parse_qs(parsed.query)
                event_id = query.get("event", [None])[0]
                show_id = query.get("show", [None])[0]
                self._send_json(platform.get_dashboard(event_id=event_id, show_id=show_id))
                return
            if parsed.path in {"/styles.css", "/app.js"}:
                self._serve_static_file(static_dir / parsed.path.lstrip("/"))
                return
            if parsed.path == "/favicon.ico":
                self.send_response(HTTPStatus.NO_CONTENT)
                self.end_headers()
                return
            self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != "/api/orders":
                self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
                return

            try:
                payload = self._read_json_body()
                order = platform.create_order(
                    customer_name=str(payload.get("customer_name", "")),
                    email=str(payload.get("email", "")),
                    event_id=str(payload.get("event_id", "")),
                    show_id=str(payload.get("show_id", "")),
                    seat_ids=[str(seat_id) for seat_id in payload.get("seat_ids", [])],
                )
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except json.JSONDecodeError:
                self._send_json({"error": "The request body must be valid JSON."}, status=HTTPStatus.BAD_REQUEST)
                return

            confirmed = len(order["confirmed_seats"])
            requested = len(order["requested_seats"])
            if confirmed == requested:
                message = f"{confirmed} seat(s) booked successfully."
            elif confirmed > 0:
                message = f"{confirmed} of {requested} seat(s) were booked. The rest were already taken."
            else:
                message = "Those seats were taken before checkout completed. Please choose another set."

            self._send_json({"message": message, "order": order}, status=HTTPStatus.CREATED)

        def log_message(self, format: str, *args: object) -> None:
            return

        def _read_json_body(self) -> dict[str, object]:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(content_length) if content_length else b"{}"
            return json.loads(raw.decode("utf-8"))

        def _serve_static_file(self, path: Path) -> None:
            if not path.exists():
                self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
                return
            mime_type, _ = mimetypes.guess_type(path.name)
            if mime_type and (mime_type.startswith("text/") or mime_type in {"application/javascript", "application/json"}):
                mime_type = f"{mime_type}; charset=utf-8"
            body = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mime_type or "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, payload: dict[str, object] | list[object], status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return TicketingHandler


def run_server(host: str = "127.0.0.1", port: int = 8000, open_browser: bool = True) -> None:
    platform = TicketingPlatform()
    platform.start()

    static_dir = Path(__file__).resolve().parent / "static"
    handler = _make_handler(platform, static_dir)
    try:
        try:
            httpd = ThreadingHTTPServer((host, port), handler)
        except OSError:
            httpd = ThreadingHTTPServer((host, 0), handler)

        actual_port = int(httpd.server_address[1])
        browser_host = "127.0.0.1" if host in {"0.0.0.0", ""} else host
        url = f"http://{browser_host}:{actual_port}"
        print(f"Ticketing platform UI running at {url}")
        print("Press Ctrl+C to stop the server.")

        if open_browser:
            threading.Timer(0.6, lambda: webbrowser.open(url)).start()

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            httpd.shutdown()
            httpd.server_close()
    finally:
        platform.stop()
