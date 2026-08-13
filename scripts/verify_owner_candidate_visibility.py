from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import socket
import struct
import time
from typing import Any
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


def new_target(endpoint: str, url: str) -> dict[str, Any]:
    request = Request(f"{endpoint}/json/new?{quote(url, safe=':/?=')}", method="PUT")
    with urlopen(request, timeout=10) as response:
        value = json.loads(response.read().decode("utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("CDP target response is not an object")
    return value


class CdpClient:
    def __init__(self, websocket_url: str) -> None:
        parsed = urlparse(websocket_url)
        self.socket = socket.create_connection((parsed.hostname or "127.0.0.1", parsed.port or 80), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {parsed.path} HTTP/1.1\r\n"
            f"Host: {parsed.hostname}:{parsed.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.socket.sendall(request.encode("ascii"))
        response = self._read_headers()
        if " 101 " not in response.splitlines()[0]:
            raise RuntimeError(f"CDP websocket handshake failed: {response.splitlines()[0]}")
        self.next_id = 1

    def _read_headers(self) -> str:
        data = bytearray()
        while b"\r\n\r\n" not in data:
            part = self.socket.recv(4096)
            if not part:
                raise RuntimeError("CDP websocket closed during handshake")
            data.extend(part)
        return data.decode("latin1")

    def _send_text(self, text: str) -> None:
        payload = text.encode("utf-8")
        header = bytearray([0x81])
        if len(payload) < 126:
            header.append(0x80 | len(payload))
        elif len(payload) < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", len(payload)))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", len(payload)))
        mask = os.urandom(4)
        header.extend(mask)
        header.extend(value ^ mask[index % 4] for index, value in enumerate(payload))
        self.socket.sendall(header)

    def _read_exact(self, count: int) -> bytes:
        data = bytearray()
        while len(data) < count:
            part = self.socket.recv(count - len(data))
            if not part:
                raise RuntimeError("CDP websocket closed")
            data.extend(part)
        return bytes(data)

    def _recv_text(self) -> str:
        first, second = self._read_exact(2)
        opcode = first & 0x0F
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._read_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._read_exact(8))[0]
        if second & 0x80:
            mask = self._read_exact(4)
            payload = bytes(value ^ mask[index % 4] for index, value in enumerate(self._read_exact(length)))
        else:
            payload = self._read_exact(length)
        if opcode == 0x8:
            raise RuntimeError("CDP websocket closed by browser")
        if opcode == 0x9:
            self.socket.sendall(b"\x8a\x00")
            return self._recv_text()
        if opcode != 0x1:
            return self._recv_text()
        return payload.decode("utf-8")

    def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        identifier = self.next_id
        self.next_id += 1
        self._send_text(json.dumps({"id": identifier, "method": method, "params": params}))
        while True:
            message = json.loads(self._recv_text())
            if message.get("id") == identifier:
                if "error" in message:
                    raise RuntimeError(json.dumps(message["error"], ensure_ascii=False))
                return message["result"]

    def evaluate(self, expression: str) -> Any:
        result = self.call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "userGesture": True},
        )
        if result.get("exceptionDetails"):
            raise RuntimeError(json.dumps(result["exceptionDetails"], ensure_ascii=False))
        return result.get("result", {}).get("value")

    def close(self) -> None:
        self.socket.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify candidate visibility without applying the update.")
    parser.add_argument("--endpoint", default="http://127.0.0.1:9237")
    parser.add_argument("--app-url", default="http://127.0.0.1:8080")
    parser.add_argument("--current-version", required=True)
    parser.add_argument("--candidate-version", required=True)
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--screenshot", type=Path)
    args = parser.parse_args()

    target = new_target(args.endpoint, args.app_url + "/legacy?tab=about")
    client = CdpClient(str(target["webSocketDebuggerUrl"]))
    try:
        client.call("Runtime.enable", {})
        client.call("Page.enable", {})
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if client.evaluate(
                "document.readyState === 'complete' && location.href.includes('tab=about') && [...document.querySelectorAll('a.button')].some(a=>a.textContent.includes('Проверить обновления'))"
            ):
                break
            time.sleep(0.2)
        else:
            raise RuntimeError("About page did not become interactive")
        clicked = client.evaluate(
            "(()=>{const link=[...document.querySelectorAll('a.button')].find(a=>a.textContent.includes('Проверить обновления'));if(!link)return false;link.click();return true})()"
        )
        if not clicked:
            raise RuntimeError("Check updates control was not found")

        result: dict[str, Any] | None = None
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            value = client.evaluate(
                "(()=>({url:location.href,text:document.body.innerText,domText:document.body.textContent||'',updateForm:Boolean(document.querySelector('[data-update-form]')),progressVisible:Boolean(document.querySelector('[data-update-progress]:not([hidden])'))}))()"
            )
            if "check_updates=1" in value["url"] and (
                args.candidate_version in value["text"] or "Не удалось проверить" in value["text"]
            ):
                result = value
                break
            time.sleep(0.25)
        if result is None:
            raise RuntimeError("Update check did not finish")

        text = str(result["text"])
        evidence = {
            "current_version_visible": args.current_version in text,
            "candidate_version_visible": f"Доступно обновление {args.candidate_version}" in text,
            "candidate_sha_visible": args.candidate_sha256 in str(result["domText"]),
            "update_form_visible": bool(result["updateForm"]),
            "update_progress_started": bool(result["progressVisible"]),
            "update_not_applied": args.current_version in text and not result["progressVisible"],
            "url": result["url"],
        }
        if args.screenshot:
            screenshot = client.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            args.screenshot.write_bytes(base64.b64decode(screenshot["data"]))
        print(json.dumps(evidence, ensure_ascii=False))
        if not all(
            evidence[key]
            for key in (
                "current_version_visible",
                "candidate_version_visible",
                "candidate_sha_visible",
                "update_form_visible",
                "update_not_applied",
            )
        ):
            return 1
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
