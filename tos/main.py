from __future__ import annotations

import argparse

from ui.server import run_server


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch the ticketing platform UI.")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind to.")
    parser.add_argument("--port", default=8000, type=int, help="Preferred port for the local server.")
    parser.add_argument("--no-browser", action="store_true", help="Start the server without opening a browser tab.")
    args = parser.parse_args()
    run_server(host=args.host, port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()

