#!/usr/bin/env python3
"""Switch PlaneLab Jellyfin library visibility without deleting libraries."""

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


MANAGED_PATHS = {
    "offline_movies": "/media/offline/movies",
    "offline_shows": "/media/offline/shows",
    "online_movies": "/media/gelato/movies",
    "online_shows": "/media/gelato/shows",
}


def normalize_path(path: str) -> str:
    normalized = path.rstrip("/")
    return normalized or "/"


def classify_libraries(
    virtual_folders: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, str], list[str]]:
    managed: dict[str, str] = {}
    names: dict[str, str] = {}
    all_ids: list[str] = []
    expected = {normalize_path(path): key for key, path in MANAGED_PATHS.items()}

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
                        f"Multiple libraries use managed path {MANAGED_PATHS[key]}"
                    )
                managed[key] = item_id

    return managed, names, all_ids


def enabled_folders_for_mode(
    mode: str, managed: dict[str, str], all_ids: list[str]
) -> list[str]:
    required = set(MANAGED_PATHS)
    missing = sorted(required - set(managed))
    if missing:
        paths = ", ".join(MANAGED_PATHS[key] for key in missing)
        raise ValueError(f"Missing Jellyfin libraries for: {paths}")

    managed_ids = set(managed.values())
    unmanaged_ids = [item_id for item_id in all_ids if item_id not in managed_ids]
    if mode == "home":
        selected = [managed["online_movies"], managed["online_shows"]]
    elif mode == "prepare":
        selected = [managed[key] for key in MANAGED_PATHS]
    elif mode == "travel":
        selected = [managed["offline_movies"], managed["offline_shows"]]
    else:
        raise ValueError(f"Unknown mode: {mode}")
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
        headers = {
            "Accept": "application/json",
            "X-Emby-Token": self.api_key,
        }
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        request = Request(
            f"{self.base_url}{path}", data=data, headers=headers, method=method
        )
        with urlopen(request, timeout=self.timeout) as response:
            payload = response.read()
            if not payload:
                return None
            return json.loads(payload)


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


def apply_mode(
    client: JellyfinClient, mode: str, excluded_users: set[str]
) -> tuple[list[str], list[str]]:
    folders = client.request("GET", "/Library/VirtualFolders")
    users = client.request("GET", "/Users")
    if not isinstance(folders, list) or not isinstance(users, list):
        raise RuntimeError("Unexpected Jellyfin API response")

    managed, names, all_ids = classify_libraries(folders)
    enabled = enabled_folders_for_mode(mode, managed, all_ids)
    changed_users: list[str] = []
    enabled_names = [names[item_id] for item_id in enabled]

    for user in users:
        username = str(user.get("Name") or "")
        user_id = str(user.get("Id") or "")
        if not username or not user_id or username in excluded_users:
            continue
        policy = user.get("Policy")
        if not isinstance(policy, dict):
            policy = client.request("GET", f"/Users/{quote(user_id)}").get("Policy")
        if not isinstance(policy, dict):
            raise RuntimeError(f"No policy returned for Jellyfin user {username}")

        updated_policy = dict(policy)
        updated_policy["EnableAllFolders"] = False
        updated_policy["EnabledFolders"] = enabled
        client.request(
            "POST", f"/Users/{quote(user_id)}/Policy", updated_policy
        )
        changed_users.append(username)

    if not changed_users:
        raise RuntimeError("No Jellyfin users were updated")
    return changed_users, enabled_names


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("home", "prepare", "travel"))
    parser.add_argument(
        "--url", default=os.environ.get("JELLYFIN_URL", "http://localhost:8096")
    )
    parser.add_argument("--api-key", default=os.environ.get("JELLYFIN_API_KEY", ""))
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
        wait_for_jellyfin(client, args.wait)
        users, libraries = apply_mode(client, args.mode, excluded)
    except (HTTPError, URLError, TimeoutError, RuntimeError, ValueError) as error:
        print(f"Error: unable to apply Jellyfin mode: {error}", file=sys.stderr)
        return 1

    print(f"Jellyfin mode: {args.mode}")
    print(f"Updated users: {', '.join(users)}")
    print(f"Visible libraries: {', '.join(libraries)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
