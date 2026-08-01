#!/usr/bin/env python3
"""Update Jellyfin's encoding configuration for the detected PlaneLab host."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class JellyfinClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> Any:
        data = None
        headers = {"Accept": "application/json", "X-Emby-Token": self.api_key}
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        request = Request(
            f"{self.base_url}{path}", data=data, headers=headers, method=method
        )
        with urlopen(request, timeout=self.timeout) as response:
            payload = response.read()
            return json.loads(payload) if payload else None


def desired_encoding_config(
    current: dict[str, Any], backend: str, device: str
) -> dict[str, Any]:
    updated = dict(current)
    if backend == "none":
        updated["HardwareAccelerationType"] = "none"
        updated["EnableHardwareEncoding"] = False
    else:
        updated["HardwareAccelerationType"] = backend
        updated["EnableHardwareEncoding"] = True
        updated["VaapiDevice"] = device
    return updated


def wait_for_jellyfin(client: JellyfinClient, seconds: int) -> None:
    deadline = time.monotonic() + seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            client.request("GET", "/System/Info/Public")
            return
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            last_error = error
            time.sleep(2)
    raise RuntimeError(f"Jellyfin did not become ready: {last_error}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("backend", choices=("none", "qsv", "vaapi"))
    parser.add_argument("--device", default="/dev/dri/renderD128")
    parser.add_argument(
        "--url", default=os.environ.get("JELLYFIN_URL", "http://localhost:8096")
    )
    parser.add_argument("--api-key", default=os.environ.get("JELLYFIN_API_KEY", ""))
    parser.add_argument("--wait", type=int, default=60)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.api_key:
        print("Hardware configuration skipped: Jellyfin API key is not set.")
        return 0
    client = JellyfinClient(args.url, args.api_key)
    try:
        wait_for_jellyfin(client, args.wait)
        current = client.request("GET", "/System/Configuration/encoding")
        if not isinstance(current, dict):
            raise RuntimeError("Unexpected Jellyfin encoding configuration response")
        updated = desired_encoding_config(current, args.backend, args.device)
        client.request("POST", "/System/Configuration/encoding", updated)
    except (HTTPError, URLError, TimeoutError, RuntimeError) as error:
        print(f"Error: unable to update Jellyfin transcoding: {error}", file=sys.stderr)
        return 1

    if args.backend == "none":
        print("Jellyfin hardware transcoding: disabled")
    else:
        print(f"Jellyfin hardware transcoding: {args.backend} via {args.device}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
