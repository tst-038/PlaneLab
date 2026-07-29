import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).with_name("jellyfin-library-mode.py")
SPEC = importlib.util.spec_from_file_location("jellyfin_library_mode", MODULE_PATH)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(module)


class LibraryModeTests(unittest.TestCase):
    def setUp(self):
        self.folders = [
            {
                "Name": "Offline films",
                "ItemId": "off-m",
                "Locations": ["/media/offline/movies"],
            },
            {
                "Name": "Offline series",
                "ItemId": "off-s",
                "Locations": ["/media/offline/shows/"],
            },
            {
                "Name": "Online films",
                "ItemId": "on-m",
                "Locations": ["/media/gelato/movies"],
            },
            {
                "Name": "Online series",
                "ItemId": "on-s",
                "Locations": ["/media/gelato/shows"],
            },
            {
                "Name": "YouTube",
                "ItemId": "youtube",
                "Locations": ["/media/YouTube"],
            },
        ]

    def classification(self):
        return module.classify_libraries(self.folders)

    def test_home_keeps_unmanaged_and_online_libraries(self):
        managed, _, all_ids = self.classification()
        enabled = module.enabled_folders_for_mode("home", managed, all_ids)
        self.assertEqual(enabled, ["youtube", "on-m", "on-s"])

    def test_prepare_enables_all_libraries(self):
        managed, _, all_ids = self.classification()
        enabled = module.enabled_folders_for_mode("prepare", managed, all_ids)
        self.assertEqual(set(enabled), set(all_ids))

    def test_travel_keeps_unmanaged_and_offline_libraries(self):
        managed, _, all_ids = self.classification()
        enabled = module.enabled_folders_for_mode("travel", managed, all_ids)
        self.assertEqual(enabled, ["youtube", "off-m", "off-s"])

    def test_missing_managed_library_fails(self):
        managed, _, all_ids = module.classify_libraries(self.folders[:-1])
        del managed["online_shows"]
        with self.assertRaisesRegex(ValueError, "/media/gelato/shows"):
            module.enabled_folders_for_mode("home", managed, all_ids)

    def test_duplicate_managed_path_fails(self):
        duplicate = dict(self.folders[0])
        duplicate["ItemId"] = "duplicate"
        with self.assertRaisesRegex(ValueError, "Multiple libraries"):
            module.classify_libraries(self.folders + [duplicate])

    def test_apply_mode_preserves_other_policy_fields_and_exclusions(self):
        class FakeClient:
            def __init__(self, folders):
                self.folders = folders
                self.updates = {}

            def request(self, method, path, body=None):
                if method == "GET" and path == "/Library/VirtualFolders":
                    return self.folders
                if method == "GET" and path == "/Users":
                    return [
                        {
                            "Id": "1",
                            "Name": "Passenger",
                            "Policy": {
                                "IsAdministrator": False,
                                "EnableAllFolders": True,
                            },
                        },
                        {
                            "Id": "2",
                            "Name": "DoNotTouch",
                            "Policy": {"EnableAllFolders": True},
                        },
                    ]
                if method == "POST":
                    self.updates[path] = body
                    return None
                raise AssertionError((method, path))

        client = FakeClient(self.folders)
        users, _ = module.apply_mode(client, "travel", {"DoNotTouch"})

        self.assertEqual(users, ["Passenger"])
        policy = client.updates["/Users/1/Policy"]
        self.assertFalse(policy["IsAdministrator"])
        self.assertFalse(policy["EnableAllFolders"])
        self.assertEqual(policy["EnabledFolders"], ["youtube", "off-m", "off-s"])
        self.assertNotIn("/Users/2/Policy", client.updates)


if __name__ == "__main__":
    unittest.main()
