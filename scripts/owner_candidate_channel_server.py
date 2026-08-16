#!/usr/bin/env python3
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
from pathlib import Path
from typing import List, Optional, Tuple, Type
from urllib.parse import unquote, urlsplit


class CandidateChannel:
    def __init__(self, root: Path, allowed_networks: List[str]) -> None:
        self.root = root.resolve()
        self.allowed_networks = tuple(ipaddress.ip_network(value) for value in allowed_networks)

    def client_allowed(self, address: str) -> bool:
        candidate = ipaddress.ip_address(address)
        return any(candidate in network for network in self.allowed_networks)

    def manifest(self) -> dict[str, object]:
        value = json.loads((self.root / "latest.json").read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("candidate manifest must be a JSON object")
        return value

    def resolve_request(self, path: str) -> Optional[Tuple[Path, str, str]]:
        request_path = unquote(urlsplit(path).path)
        if request_path == "/latest.json":
            return self.root / "latest.json", "application/json; charset=utf-8", "no-store"
        if request_path == "/health.json":
            return self.root / "channel-state.json", "application/json; charset=utf-8", "no-store"

        manifest = self.manifest()
        artifact_name = str(manifest.get("filename") or "").strip()
        if artifact_name and request_path == f"/artifacts/{artifact_name}":
            return (
                self.root / "artifacts" / artifact_name,
                "application/zip",
                "public, max-age=31536000, immutable",
            )
        return None


def handler_factory(channel: CandidateChannel) -> Type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "FedorinovOwnerCandidate/1"

        def do_GET(self) -> None:  # noqa: N802
            self._serve(include_body=True)

        def do_HEAD(self) -> None:  # noqa: N802
            self._serve(include_body=False)

        def _serve(self, *, include_body: bool) -> None:
            if not channel.client_allowed(self.client_address[0]):
                self.send_error(403)
                return
            try:
                resolved = channel.resolve_request(self.path)
            except (OSError, ValueError, json.JSONDecodeError):
                self.send_error(503)
                return
            if resolved is None:
                self.send_error(404)
                return

            path, content_type, cache_control = resolved
            try:
                payload = path.read_bytes()
            except OSError:
                self.send_error(503)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", cache_control)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if include_body:
                self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            super().log_message(format, *args)

    return Handler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve the LAN-only Owner candidate channel.")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=18387)
    parser.add_argument(
        "--allowed-network",
        action="append",
        default=[],
        help="IPv4/IPv6 network allowed to fetch the channel; may be repeated.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    networks = args.allowed_network or ["127.0.0.0/8"]
    channel = CandidateChannel(args.root, networks)
    server = ThreadingHTTPServer((args.bind, args.port), handler_factory(channel))
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
