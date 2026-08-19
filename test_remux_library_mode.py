import importlib.util
import pathlib
import unittest
from unittest import mock


SCRIPT = pathlib.Path(__file__).with_name("remux-library-mode.py")
SPEC = importlib.util.spec_from_file_location("remux_library_mode", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class RemuxLibraryModeTests(unittest.TestCase):
    def test_mode_selects_local_or_online_catalogs(self):
        catalogs = [
            {"collection_id": "local", "local": True},
            {"collection_id": "online", "local": False},
        ]
        self.assertEqual(MODULE.hidden_catalog_ids("home", catalogs), ["local"])
        self.assertEqual(MODULE.hidden_catalog_ids("prepare", catalogs), [])
        self.assertEqual(MODULE.hidden_catalog_ids("travel", catalogs), ["online"])

    def test_replaces_catalog_rules_and_preserves_other_filters(self):
        existing = {
            "match_mode": "all",
            "groups": [
                {
                    "match_mode": "all",
                    "rules": [
                        {"field": "genre", "op": "is_not", "values": ["Horror"]},
                        {"field": "catalog", "op": "not_in", "catalog_ids": ["old"]},
                    ],
                }
            ],
        }
        result = MODULE.merge_catalog_filter(existing, ["new"])
        self.assertEqual(result["groups"][0]["rules"][0]["field"], "genre")
        self.assertEqual(
            result["groups"][1]["rules"][0],
            {"field": "catalog", "op": "not_in", "catalog_ids": ["new"]},
        )

    def test_prepare_removes_only_catalog_rules(self):
        existing = {
            "match_mode": "all",
            "groups": [
                {
                    "match_mode": "all",
                    "rules": [
                        {"field": "catalog", "op": "not_in", "catalog_ids": ["old"]}
                    ],
                }
            ],
        }
        self.assertIsNone(MODULE.merge_catalog_filter(existing, []))

    def test_refuses_unsafe_any_filter(self):
        existing = {
            "match_mode": "any",
            "groups": [
                {
                    "match_mode": "all",
                    "rules": [{"field": "genre", "op": "is", "values": ["Drama"]}],
                }
            ],
        }
        with self.assertRaises(MODULE.ModeError):
            MODULE.merge_catalog_filter(existing, ["hidden"])

    def test_apply_mode_updates_every_user(self):
        users = [
            {"Id": "user-1", "Name": "One", "Policy": {"FilterRules": None}},
            {"Id": "user-2", "Name": "Two", "Policy": {"FilterRules": None}},
        ]
        addons = [
            {"id": "local-addon", "name": "Local", "kind": "opendal-local", "enabled": True},
            {"id": "online-addon", "name": "Online", "kind": "stremio", "enabled": True},
        ]
        catalog_map = {
            "/addons/local-addon/catalogs": [
                {"enabled": True, "collectionId": "local-catalog", "name": "Local"}
            ],
            "/addons/online-addon/catalogs": [
                {"enabled": True, "collectionId": "online-catalog", "name": "Online"}
            ],
        }
        posts = []

        def request(_url, _key, path, method="GET", payload=None, **_kwargs):
            if method == "POST":
                posts.append((path, payload))
                return None
            if path == "/users":
                return users
            if path == "/addons":
                return addons
            return catalog_map[path]

        with mock.patch.object(MODULE, "api_request", side_effect=request):
            changed, hidden = MODULE.apply_mode(
                "travel", "http://remux", "key", {"opendal-local"}, 0
            )

        self.assertEqual((changed, hidden), (2, 1))
        self.assertEqual(len(posts), 2)
        for path, policy in posts:
            self.assertRegex(path, r"^/users/user-[12]/policy$")
            rule = policy["FilterRules"]["groups"][0]["rules"][0]
            self.assertEqual(rule["catalog_ids"], ["online-catalog"])


if __name__ == "__main__":
    unittest.main()
