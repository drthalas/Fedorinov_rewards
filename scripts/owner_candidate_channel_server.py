from __future__ import annotations

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import urlparse


class CandidateChannelHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        if urlparse(self.path).path == "/healthz":
            manifest_path = Path(self.directory) / "latest.json"
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
                payload = json.dumps(
                    {
                        "status": "ok",
                        "version": manifest.get("version"),
                        "sha256": manifest.get("sha256"),
                    }
                ).encode("utf-8")
            except (OSError, ValueError) as exc:
                self.send_error(503, str(exc))
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        super().do_GET()

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the isolated Owner candidate channel on loopback.")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--port", type=int, default=18387)
    args = parser.parse_args()

    root = args.root.resolve(strict=True)
    if not (root / "latest.json").is_file():
        raise SystemExit(f"Candidate manifest is missing: {root / 'latest.json'}")
    server = ThreadingHTTPServer(
        ("127.0.0.1", args.port),
        lambda *handler_args, **kwargs: CandidateChannelHandler(
            *handler_args,
            directory=str(root),
            **kwargs,
        ),
    )
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
