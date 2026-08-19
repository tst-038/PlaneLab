#!/usr/bin/env python3
"""Apply PlaneLab catalog visibility to every Remux user."""

from __future__ import annotations

import copy
import http.client
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any


MODES = {"home", "prepare", "travel"}
NETWORK_ERRORS = (
    ConnectionError,
    TimeoutError,
    http.client.RemoteDisconnected,
    urllib.error.URLError,
)


class ModeError(RuntimeError):
    pass


def api_request(
    base_url: str,
    api_key: str,
    path: str,
    method: str = "GET",
    payload: Any | None = None,
    timeout: int = 10,
    startup_timeout: int = 60,
) -> Any:
    url = f"{base_url.rstrip('/')}{path}"
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    deadline = time.monotonic() + startup_timeout
    while True:
        request = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Emby-Token": api_key,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = response.read()
                return json.loads(data) if data else None
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace").strip()
            suffix = f": {detail}" if detail else ""
            raise ModeError(f"Remux returned HTTP {exc.code} for {path}{suffix}") from exc
        except NETWORK_ERRORS as exc:
            if time.monotonic() >= deadline:
                raise ModeError(
                    f"Remux did not become reachable at {base_url} within "
                    f"{startup_timeout} seconds: {exc}"
                ) from exc
            time.sleep(1)


def discover_catalogs(
    base_url: str, api_key: str, local_kinds: set[str], startup_timeout: int
) -> list[dict[str, Any]]:
    addons = api_request(
        base_url, api_key, "/addons", startup_timeout=startup_timeout
    )
    if not isinstance(addons, list):
        raise ModeError("Remux returned an invalid addon list")

    inventory: list[dict[str, Any]] = []
    for addon in addons:
        if not isinstance(addon, dict) or not addon.get("enabled", False):
            continue
        addon_id = addon.get("id")
        if not addon_id:
            continue
        catalogs = api_request(
            base_url,
            api_key,
            f"/addons/{addon_id}/catalogs",
            startup_timeout=startup_timeout,
        )
        if not isinstance(catalogs, list):
            raise ModeError(f"Remux returned invalid catalogs for addon {addon_id}")
        for catalog in catalogs:
            collection_id = catalog.get("collectionId")
            if not catalog.get("enabled", False) or not collection_id:
                continue
            inventory.append(
                {
                    "collection_id": collection_id,
                    "catalog": catalog.get("name", catalog.get("catalogId", "unknown")),
                    "addon": addon.get("name", addon_id),
                    "kind": str(addon.get("kind", "")).lower(),
                    "local": str(addon.get("kind", "")).lower() in local_kinds,
                }
            )
    return inventory


def hidden_catalog_ids(mode: str, catalogs: list[dict[str, Any]]) -> list[str]:
    if mode == "prepare":
        return []
    if mode == "home":
        return sorted(c["collection_id"] for c in catalogs if c["local"])
    if mode == "travel":
        return sorted(c["collection_id"] for c in catalogs if not c["local"])
    raise ModeError(f"Unknown PlaneLab mode: {mode}")


def merge_catalog_filter(existing: Any, hidden_ids: list[str]) -> dict[str, Any] | None:
    """Replace catalog rules while preserving compatible non-catalog rules."""
    if existing is None:
        existing = {"match_mode": "all", "groups": []}
    if not isinstance(existing, dict):
        raise ModeError("A user has an invalid Remux FilterRules value")

    top_mode = existing.get("match_mode", "all")
    groups = existing.get("groups", [])
    if not isinstance(groups, list):
        raise ModeError("A user has invalid Remux filter groups")

    preserved: list[dict[str, Any]] = []
    for group in groups:
        if not isinstance(group, dict):
            raise ModeError("A user has an invalid Remux filter group")
        rules = group.get("rules", [])
        if not isinstance(rules, list):
            raise ModeError("A user has invalid Remux filter rules")
        remaining = [
            copy.deepcopy(rule)
            for rule in rules
            if not isinstance(rule, dict) or rule.get("field") != "catalog"
        ]
        if remaining:
            updated_group = copy.deepcopy(group)
            updated_group["rules"] = remaining
            preserved.append(updated_group)

    if preserved and top_mode != "all":
        raise ModeError(
            "PlaneLab cannot safely combine catalog hiding with an existing "
            "top-level 'any' filter; change that user filter to 'all' in Remux"
        )

    if hidden_ids:
        preserved.append(
            {
                "match_mode": "all",
                "rules": [
                    {
                        "field": "catalog",
                        "op": "not_in",
                        "catalog_ids": hidden_ids,
                    }
                ],
            }
        )

    if not preserved:
        return None
    return {"match_mode": "all", "groups": preserved}


def apply_mode(
    mode: str,
    base_url: str,
    api_key: str,
    local_kinds: set[str],
    startup_timeout: int,
) -> tuple[int, int]:
    users = api_request(base_url, api_key, "/users", startup_timeout=startup_timeout)
    if not isinstance(users, list):
        raise ModeError("Remux returned an invalid user list")

    catalogs = discover_catalogs(base_url, api_key, local_kinds, startup_timeout)
    if not catalogs:
        raise ModeError("Remux has no enabled catalogs with collection IDs")
    hidden_ids = hidden_catalog_ids(mode, catalogs)

    planned: list[tuple[str, str, dict[str, Any], dict[str, Any]]] = []
    for user in users:
        if not isinstance(user, dict) or not user.get("Id"):
            raise ModeError("Remux returned an invalid user")
        policy = user.get("Policy")
        if not isinstance(policy, dict):
            raise ModeError(f"Remux user {user.get('Name', user['Id'])} has no policy")
        original = copy.deepcopy(policy)
        updated = copy.deepcopy(policy)
        updated["FilterRules"] = merge_catalog_filter(
            policy.get("FilterRules"), hidden_ids
        )
        planned.append((user["Id"], user.get("Name", user["Id"]), original, updated))

    updated_users: list[tuple[str, dict[str, Any]]] = []
    try:
        for user_id, _name, original, updated in planned:
            api_request(
                base_url,
                api_key,
                f"/users/{user_id}/policy",
                method="POST",
                payload=updated,
                startup_timeout=startup_timeout,
            )
            updated_users.append((user_id, original))
    except Exception:
        for user_id, original in reversed(updated_users):
            try:
                api_request(
                    base_url,
                    api_key,
                    f"/users/{user_id}/policy",
                    method="POST",
                    payload=original,
                    startup_timeout=0,
                )
            except Exception:
                pass
        raise

    return len(planned), len(hidden_ids)


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in MODES:
        print("Usage: remux-library-mode.py <home|prepare|travel>", file=sys.stderr)
        return 2
    api_key = os.environ.get("REMUX_API_KEY", "").strip()
    if not api_key:
        print("Error: REMUX_API_KEY is empty", file=sys.stderr)
        return 1
    base_url = os.environ.get("REMUX_URL", "http://localhost:8096").strip()
    local_kinds = {
        kind.strip().lower()
        for kind in os.environ.get("REMUX_LOCAL_ADDON_KINDS", "opendal-local").split(",")
        if kind.strip()
    }
    try:
        startup_timeout = int(os.environ.get("REMUX_STARTUP_TIMEOUT", "60"))
        users, hidden = apply_mode(
            sys.argv[1], base_url, api_key, local_kinds, startup_timeout
        )
    except (ModeError, ValueError) as exc:
        print(f"Error: unable to apply Remux mode: {exc}", file=sys.stderr)
        return 1
    print(
        f"Applied Remux mode '{sys.argv[1]}' to {users} users; "
        f"hiding {hidden} catalogs."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
