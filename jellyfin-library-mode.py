#!/usr/bin/env python3
"""Switch configured Jellyfin library visibility without deleting libraries."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


VALID_MODES = {"home", "prepare", "travel"}


def normalize_path(path: str) -> str:
    normalized = path.rstrip("/")
    return normalized or "/"


def load_library_config(path: str) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as config_file:
        document = json.load(config_file)
    libraries = document.get("libraries")
    if not isinstance(libraries, list) or not libraries:
        raise ValueError("Config must contain a non-empty libraries list")

    seen_keys: set[str] = set()
    seen_paths: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for entry in libraries:
        if not isinstance(entry, dict):
            raise ValueError("Every configured library must be an object")
        key = str(entry.get("key") or "").strip()
        library_path = normalize_path(str(entry.get("path") or "").strip())
        modes = entry.get("modes")
        if not key or library_path == "/" or not isinstance(modes, list):
            raise ValueError("Every library needs a key, path and modes list")
        mode_set = {str(mode) for mode in modes}
        if not mode_set or not mode_set <= VALID_MODES:
            raise ValueError(f"Invalid modes for configured library {key}")
        if key in seen_keys or library_path in seen_paths:
            raise ValueError(f"Duplicate library key or path: {key}")
        seen_keys.add(key)
        seen_paths.add(library_path)
        normalized.append({"key": key, "path": library_path, "modes": mode_set})
    return normalized


def classify_libraries(
    virtual_folders: list[dict[str, Any]],
    configured_libraries: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, str], list[str]]:
    managed: dict[str, str] = {}
    names: dict[str, str] = {}
    all_ids: list[str] = []
    expected = {
        entry["path"]: entry["key"] for entry in configured_libraries
    }
    paths_by_key = {
        entry["key"]: entry["path"] for entry in configured_libraries
    }

    for folder in virtual_folders:
        item_id = str(folder.get("ItemId") or "")
        if not item_id:
            continue
        all_ids.append(item_id)
        names[item_id] = str(folder.get("Name") or item_id)
        for location in folder.get("Locations") or []:
            key = expected.get(normalize_path(str(location)))
            if key:
                if key in managed and managed[key] != item_id:
                    raise ValueError(
                        f"Multiple libraries use managed path {paths_by_key[key]}"
                    )
                managed[key] = item_id

    return managed, names, all_ids


def enabled_folders_for_mode(
    mode: str,
    managed: dict[str, str],
    all_ids: list[str],
    configured_libraries: list[dict[str, Any]],
) -> list[str]:
    required = {entry["key"] for entry in configured_libraries}
    missing = sorted(required - set(managed))
    if missing:
        paths_by_key = {
            entry["key"]: entry["path"] for entry in configured_libraries
        }
        paths = ", ".join(paths_by_key[key] for key in missing)
        raise ValueError(f"Missing Jellyfin libraries for: {paths}")
    if mode not in VALID_MODES:
        raise ValueError(f"Unknown mode: {mode}")

    managed_ids = set(managed.values())
    unmanaged_ids = [item_id for item_id in all_ids if item_id not in managed_ids]
    selected = [
        managed[entry["key"]]
        for entry in configured_libraries
        if mode in entry["modes"]
    ]
    return list(dict.fromkeys(unmanaged_ids + selected))


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


def wait_for_jellyfin(client: JellyfinClient, seconds: int) -> None:
    deadline = time.monotonic() + seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            client.request("GET", "/System/Info/Public")
            return
        except (
            HTTPError,
            URLError,
            TimeoutError,
            OSError,
            json.JSONDecodeError,
        ) as error:
            last_error = error
            time.sleep(2)
    raise RuntimeError(f"Jellyfin did not become ready: {last_error}")


def apply_mode(
    client: JellyfinClient,
    mode: str,
    excluded_users: set[str],
    configured_libraries: list[dict[str, Any]],
) -> tuple[list[str], list[str]]:
    folders = client.request("GET", "/Library/VirtualFolders")
    users = client.request("GET", "/Users")
    if not isinstance(folders, list) or not isinstance(users, list):
        raise RuntimeError("Unexpected Jellyfin API response")

    managed, names, all_ids = classify_libraries(folders, configured_libraries)
    enabled = enabled_folders_for_mode(
        mode, managed, all_ids, configured_libraries
    )
    changed_users: list[str] = []
    enabled_names = [names[item_id] for item_id in enabled]

    for user in users:
        username = str(user.get("Name") or "")
        user_id = str(user.get("Id") or "")
        if not username or not user_id or username in excluded_users:
            continue
        policy = user.get("Policy")
        if not isinstance(policy, dict):
            user_details = client.request("GET", f"/Users/{quote(user_id)}")
            policy = user_details.get("Policy") if isinstance(user_details, dict) else None
        if not isinstance(policy, dict):
            raise RuntimeError(f"No policy returned for Jellyfin user {username}")

        updated_policy = dict(policy)
        updated_policy["EnableAllFolders"] = False
        updated_policy["EnabledFolders"] = enabled
        client.request("POST", f"/Users/{quote(user_id)}/Policy", updated_policy)
        changed_users.append(username)

    if not changed_users:
        raise RuntimeError("No Jellyfin users were updated")
    return changed_users, enabled_names


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=sorted(VALID_MODES))
    parser.add_argument(
        "--url", default=os.environ.get("JELLYFIN_URL", "http://localhost:8096")
    )
    parser.add_argument("--api-key", default=os.environ.get("JELLYFIN_API_KEY", ""))
    parser.add_argument(
        "--config",
        default=os.environ.get(
            "PLANELAB_LIBRARY_MODES_FILE",
            os.path.join(os.path.dirname(__file__), "library-modes.json"),
        ),
    )
    parser.add_argument("--wait", type=int, default=60)
    parser.add_argument(
        "--exclude-users",
        default=os.environ.get("JELLYFIN_EXCLUDED_USERS", ""),
        help="Comma-separated Jellyfin usernames whose policies must not change",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.api_key:
        print("Error: JELLYFIN_API_KEY is not configured.", file=sys.stderr)
        return 2
    client = JellyfinClient(args.url, args.api_key)
    excluded = {
        value.strip() for value in args.exclude_users.split(",") if value.strip()
    }
    try:
        configured_libraries = load_library_config(args.config)
        wait_for_jellyfin(client, args.wait)
        users, libraries = apply_mode(
            client, args.mode, excluded, configured_libraries
        )
    except (
        HTTPError,
        URLError,
        TimeoutError,
        RuntimeError,
        ValueError,
        OSError,
        json.JSONDecodeError,
    ) as error:
        print(f"Error: unable to apply Jellyfin mode: {error}", file=sys.stderr)
        return 1

    print(f"Jellyfin mode: {args.mode}")
    print(f"Updated users: {', '.join(users)}")
    print(f"Visible libraries: {', '.join(libraries)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
